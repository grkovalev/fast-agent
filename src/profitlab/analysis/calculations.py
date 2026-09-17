"""Deterministic selected-fact arithmetic; never bridge missing annual periods."""

import itertools
import json
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext
from uuid import uuid4

from profitlab.analysis.reconciliation import MAIN_METRICS, ReconciliationService, stable_id
from profitlab.contracts.facts import FactCandidate, Metric
from profitlab.contracts.reports import Calculation
from profitlab.providers.extraction import ExtractionService
from profitlab.storage import Repository
from profitlab.trace import TraceRecorder

VERSION = "growth-v1"


def display(value):
    with localcontext() as ctx:
        ctx.prec = max(60, len(value.as_tuple().digits) + 5)
        return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def incompatibility(facts, observations):
    if any(not f.value.is_finite() for f in facts):
        return "nonfinite_input"
    if len({(f.currency, f.unit) for f in facts}) > 1:
        return "currency_unit_mismatch"
    if len({f.share_class for f in facts}) > 1:
        return "share_class_mismatch"
    if len({(f.metric, f.attribution, f.scope, f.basis, f.annuality) for f in facts}) > 1:
        return "context_mismatch"
    if any(f.annuality != "annual" or f.basis != "gaap" for f in facts):
        return "incompatible_periods"
    durations = [(f.period.end - f.period.start).days + 1 for f in facts]
    # Ordinary leap years and 52/53-week calendars are comparable. Larger
    # changes or fiscal transition intervals are suppressed conservatively.
    if any(not 330 <= d <= 381 for d in durations) or max(durations) - min(durations) > 7:
        return "incompatible_periods"
    for a, b in itertools.pairwise(facts):
        if (
            b.period.fiscal_year != a.period.fiscal_year + 1
            or b.period.start != a.period.end + timedelta(days=1)
        ):
            return "incompatible_periods"
    if facts[0].metric in (Metric.EPS_DILUTED, Metric.SHARES_DILUTED):
        bases = {
            flag
            for o in observations
            for flag in o.comparability_flags
            if flag.startswith("per_share_basis:")
        }
        if len(bases) > 1 or any(
            "Mixed original" in flag for o in observations for flag in o.comparability_flags
        ):
            return "per_share_basis_mismatch"
    return ""


def calculate(metric, years, facts, observations=(), cagr=False, missing_reason="missing_inputs"):
    """facts are ordered oldest first; None explicitly represents unavailable input."""
    present = [f for f in facts if f is not None]
    result, label, reason = {}, "", ""
    formula = (
        "((last / first) ** (1 / intervals) - 1) * 100"
        if cagr
        else "absolute_change = current - previous; yoy_percent = (current - previous) / previous * 100"
    )
    if len(present) != len(years) or len(years) < 2:
        reason = missing_reason
    else:
        reason = incompatibility(present, observations)
        if any(
            f.period.fiscal_year != year or f.metric != metric
            for year, f in zip(years, present, strict=True)
        ):
            reason = "incompatible_periods"
    status = (
        "conflicting"
        if reason == "conflicting_inputs"
        else "missing"
        if reason == "missing_inputs"
        else "not_applicable"
        if reason
        else "applicable"
    )
    with localcontext() as ctx:
        ctx.prec = 60
        if not reason:
            previous, current = present[0].value, present[-1].value
            if cagr:
                if any(f.value <= 0 for f in present):
                    reason, status = "nonpositive_series", "not_applicable"
                else:
                    result["cagr_percent"] = (
                        (current / previous) ** (Decimal(1) / Decimal(len(years) - 1)) - 1
                    ) * 100
            else:
                result["absolute_change"] = current - previous
                if previous <= 0 or current < 0:
                    status = "not_applicable"
                    reason = (
                        "zero_base"
                        if previous == 0
                        else "negative_base"
                        if previous < 0
                        else "profit_to_loss"
                    )
                    label = (
                        "turned profitable"
                        if previous <= 0 < current
                        else "moved to a loss"
                        if previous >= 0 > current
                        else "loss narrowed"
                        if previous < current <= 0
                        else "loss widened"
                        if current < previous < 0
                        else "loss unchanged"
                        if previous == current < 0
                        else "zero base"
                    )
                else:
                    result["yoy_percent"] = (current - previous) / previous * 100
    data = {
        "formula": formula,
        "formula_version": VERSION,
        "metric": str(metric),
        "years": years,
        "input_ids": [f.candidate_id for f in present],
        "input_values": [f.value for f in present],
        "evidence_ids": sorted({e for f in present for e in f.evidence_ids}),
        "results": result,
        "status": status,
        "reason": reason,
        "label": label,
        "rounding_policy": "Decimal precision 60; half-up to 2 decimal places for display only.",
        "display_policy": "Exact source inputs; absolute change in base units; percentages to 2 decimals.",
    }
    return Calculation(calculation_id=stable_id("calc", data), **data)


class CalculationService:
    def __init__(self, settings):
        self.settings = settings
        self.repo = Repository(settings.data_dir)

    def inputs(self, run_id):
        index, _, observations = ReconciliationService(self.settings).latest(run_id)
        extraction, _ = ExtractionService(self.settings).latest(run_id)
        if (
            not index
            or not extraction
            or index["extraction_created_at"] != extraction["created_at"]
        ):
            raise ValueError("Run reconciliation against the latest extraction before calculating.")
        facts = {
            cid: FactCandidate.model_validate_json(self.repo.read(run_id, cid))
            for o in observations
            for cid in o.selected_facts.values()
        }
        return index, observations, facts

    def latest(self, run_id):
        indexes = [
            json.loads(self.repo.read(run_id, a["artifact_id"]))
            for a in self.repo.artifacts(run_id)
            if a["artifact_id"].startswith("calculate-index-")
        ]
        if not indexes:
            return None, [], [], {}
        index = max(indexes, key=lambda i: i["created_at"])
        try:
            reconciliation, observations, facts = self.inputs(run_id)
        except ValueError:
            return None, [], [], {}
        if index["reconciliation_created_at"] != reconciliation["created_at"]:
            return None, [], [], {}
        return (
            index,
            [
                Calculation.model_validate_json(self.repo.read(run_id, cid))
                for cid in index["calculation_ids"]
            ],
            observations,
            facts,
        )

    def progress(self, run_id):
        run = self.repo.manifest(run_id)
        if run.mode == "replay":
            raise ValueError("Replay calculations are read-only.")
        reconciliation, observations, facts = self.inputs(run_id)
        covered = sorted(row["fiscal_year"] for row in reconciliation["coverage"])
        if not covered:
            raise ValueError("No fiscal years available for calculations.")
        years = list(range(covered[0], covered[-1] + 1))
        by_year = {o.period.fiscal_year: o for o in observations}
        calculations = []
        trace = TraceRecorder(self.repo, run_id, self.settings.redactor())
        with trace.operation(
            "Calculate selected annual metrics",
            {"version": VERSION, "reconciliation": reconciliation},
            stage="calculate",
        ) as out:
            for metric in MAIN_METRICS:
                intervals = [(years[i : i + 2], False) for i in range(len(years) - 1)]
                if len(years) > 1:
                    intervals.append((years, True))
                for interval, cagr in intervals:
                    obs = [by_year[y] for y in interval if y in by_year]
                    inputs = [
                        facts.get(by_year[y].selected_facts.get(metric)) if y in by_year else None
                        for y in interval
                    ]
                    missing = (
                        "conflicting_inputs"
                        if any(o.missingness.get(metric) == "conflicting" for o in obs)
                        else "missing_inputs"
                    )
                    calc = calculate(metric, interval, inputs, obs, cagr, missing)
                    self.repo.save_contract(run_id, calc.calculation_id, calc)
                    calculations.append(calc)
                    out[calc.calculation_id] = calc.model_dump(mode="json")
        now = datetime.now(UTC)
        index = {
            "version": VERSION,
            "created_at": now.isoformat(),
            "reconciliation_created_at": reconciliation["created_at"],
            "calculation_ids": [c.calculation_id for c in calculations],
            "years": years,
            "coverage": reconciliation["coverage"],
        }
        self.repo.put(run_id, "calculate-index-" + uuid4().hex, json.dumps(index).encode())
        snapshot = run.model_copy(
            update={
                "stage": "calculate",
                "updated_at": now,
                "versions": {**run.versions, "calculations": VERSION},
                "limitation": "Data table; narrative not generated. Unavailable comparisons have explicit reasons; upstream limitations remain in evidence coverage.",
            }
        )
        self.repo.save_contract(run_id, "manifest-calculate-" + uuid4().hex, snapshot)
        return snapshot
