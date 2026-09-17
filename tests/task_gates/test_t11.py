"""Selected-input Decimal arithmetic and offline, restart-persistent UI gate."""

import socket
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from profitlab.analysis.calculations import CalculationService, calculate
from profitlab.cli import app
from profitlab.contracts.facts import FactCandidate, Metric
from profitlab.demo import DemoService
from profitlab.settings import Settings
from profitlab.web.app import create_app


def fact(year, value, **changes):
    return FactCandidate.model_validate(
        dict(
            candidate_id=f"fact-{year}",
            metric="eps_diluted",
            raw_label="Diluted EPS",
            raw_numeric_text=str(value),
            value=str(value),
            currency="USD",
            unit="currency_per_share",
            period={"start": f"{year}-01-01", "end": f"{year}-12-31", "fiscal_year": year},
            annuality="annual",
            basis="gaap",
            scope="consolidated",
            attribution="common",
            extraction_method="table",
            evidence_ids=[f"evidence-{year}"],
            **changes,
        )
    )


def test_exact_arithmetic_and_three_interval_cagr():
    a, b = fact(2024, "1.60"), fact(2025, "2.00")
    c = calculate(Metric.EPS_DILUTED, [2024, 2025], [a, b])
    assert c.results == {"absolute_change": Decimal("0.40"), "yoy_percent": Decimal(25)}
    assert c.input_values == [Decimal("1.60"), Decimal("2.00")]
    assert c.input_ids == [a.candidate_id, b.candidate_id]
    c = calculate(
        Metric.EPS_DILUTED,
        [2022, 2023, 2024, 2025],
        [fact(2022, 1), fact(2023, 2), fact(2024, 4), fact(2025, 8)],
        cagr=True,
    )
    assert abs(c.results["cagr_percent"] - Decimal(100)) < Decimal("1e-55")


@pytest.mark.parametrize(
    "previous,current,reason,label",
    [
        ("0", "2", "zero_base", "turned profitable"),
        ("-2", "-1", "negative_base", "loss narrowed"),
        ("-1", "-2", "negative_base", "loss widened"),
        ("-2", "1", "negative_base", "turned profitable"),
        ("2", "-1", "profit_to_loss", "moved to a loss"),
        ("-2", "0", "negative_base", "loss narrowed"),
    ],
)
def test_loss_zero_status(previous, current, reason, label):
    c = calculate(Metric.EPS_DILUTED, [2024, 2025], [fact(2024, previous), fact(2025, current)])
    assert c.reason == reason and c.label == label and c.status == "not_applicable"
    assert c.results == {"absolute_change": Decimal(current) - Decimal(previous)}
    assert (
        calculate(Metric.EPS_DILUTED, [2024, 2025], [fact(2024, 2), fact(2025, 0)]).results[
            "yoy_percent"
        ]
        == -100
    )


def test_missing_incompatible_and_cagr_loss_policy():
    a, b = fact(2024, 1), fact(2025, 2)
    assert calculate(Metric.EPS_DILUTED, [2024, 2025], [a, None]).reason == "missing_inputs"
    assert (
        calculate(Metric.EPS_DILUTED, [2023, 2025], [fact(2023, 1), b]).reason
        == "incompatible_periods"
    )
    for changes, reason in [
        ({"currency": "EUR"}, "currency_unit_mismatch"),
        ({"share_class": "B"}, "share_class_mismatch"),
        (
            {"period": a.period.model_copy(update={"start": date(2024, 7, 1)})},
            "incompatible_periods",
        ),
    ]:
        c = calculate(Metric.EPS_DILUTED, [2024, 2025], [a.model_copy(update=changes), b])
        assert c.reason == reason and not c.results
    c = calculate(
        Metric.EPS_DILUTED,
        [2023, 2024, 2025],
        [fact(2023, 1), fact(2024, -1), fact(2025, 2)],
        cagr=True,
    )
    assert c.reason == "nonpositive_series" and not c.results


@pytest.mark.parametrize(
    "scenario", ["normal", "losses", "conflict", "two-years", "split-adjusted"]
)
def test_offline_pipeline_ui_immutability_and_stale_inputs(tmp_path, monkeypatch, scenario):
    monkeypatch.setenv("PROFITLAB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: pytest.fail("Network forbidden"))
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    run = DemoService(tmp_path).create("t11-test", "T11", scenario)
    assert run.stage == "calculate"
    service = CalculationService(settings)
    _index, items, _observations, facts = service.latest(run.run_id)
    assert len(items) == (6 if scenario == "two-years" else 12)
    eps = [c for c in items if c.metric == "eps_diluted" and "absolute_change" in c.formula]
    assert len(eps) == (1 if scenario == "two-years" else 3)
    if scenario == "normal":
        assert eps[-1].results["yoy_percent"] == Decimal(25)
    if scenario == "losses":
        assert all("yoy_percent" not in c.results for c in eps)
        assert [c.label for c in eps] == ["loss narrowed", "loss narrowed", "turned profitable"]
    if scenario == "conflict":
        assert eps[-1].reason == "conflicting_inputs" and not eps[-1].results
    for c in items:
        assert all(cid in facts for cid in c.input_ids)
    with TestClient(create_app(settings)) as client:
        for page in ["report", "calculations"]:
            response = client.get(f"/runs/{run.run_id}/{page}")
            assert (
                response.status_code == 200
                and "Data table; narrative not generated." in response.text
            )
            assert "Unrounded Decimal" in response.text
        page = client.get(f"/runs/{run.run_id}/candidates").text
        assert all(f'id="{cid}"' in page for c in items for cid in c.input_ids)
    result = CliRunner().invoke(app, ["stage", run.run_id, "calculate"])
    assert result.exit_code == 0, result.output
    assert CalculationService(settings).latest(run.run_id)[1] == items
    from profitlab.analysis.reconciliation import ReconciliationService

    ReconciliationService(settings).progress(run.run_id)
    assert service.latest(run.run_id)[0] is None
    with TestClient(create_app(settings)) as client:
        assert "Calculations unavailable" in client.get(f"/runs/{run.run_id}/report").text


def test_changed_fiscal_lengths_and_mixed_per_share_basis():
    from profitlab.contracts.facts import AnnualObservation

    a, b = fact(2024, 1), fact(2025, 2)
    changed = a.model_copy(update={'period': a.period.model_copy(update={'start': date(2024, 1, 15)})})
    assert calculate(Metric.EPS_DILUTED, [2024, 2025], [changed, b]).reason == 'incompatible_periods'
    observations = [AnnualObservation(observation_id=f'obs-{year}', period=f.period,
        selected_facts={Metric.EPS_DILUTED: f.candidate_id},
        missingness={m: 'missing' for m in Metric if m != Metric.EPS_DILUTED},
        comparability_flags=[basis]) for year, f, basis in
        [(2024, a, 'per_share_basis:reported'), (2025, b, 'per_share_basis:split-adjusted:new')]]
    c = calculate(Metric.EPS_DILUTED, [2024, 2025], [a, b], observations)
    assert c.reason == 'per_share_basis_mismatch' and not c.results
    # 52/53-week-compatible annual duration variation is allowed.
    c = calculate(Metric.EPS_DILUTED, [2024, 2025], [a, b.model_copy(update={
        'period': b.period.model_copy(update={'end': date(2025, 12, 30)})})])
    assert c.status == 'applicable'
