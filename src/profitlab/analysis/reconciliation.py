"""Ordered, conservative selection of source-validated annual facts.

Reported precision explains rounding differences only; repeated presentations never
count as independent votes. Adjustment labels must belong to the cited table/row
or year headers, rather than merely occur elsewhere in the filing.
"""
import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from uuid import uuid4

from profitlab.contracts.facts import AnnualObservation, CandidateGroup, Metric
from profitlab.contracts.sources import EvidenceRef, FilingRecord, SourceBlock, TableCell
from profitlab.providers.extraction import ExtractionService
from profitlab.storage import Repository
from profitlab.trace import TraceRecorder

VERSION = 'reconcile-v1'
KEY_FIELDS = ('metric', 'period', 'unit', 'currency', 'scope', 'attribution',
              'basis', 'share_class', 'annuality')
MAIN_METRICS = (Metric.NET_INCOME_COMMON, Metric.EPS_DILUTED, Metric.SHARES_DILUTED)
REQUIRED_CHECKS = ('source', 'numeric', 'period', 'unit', 'scope', 'basis')


def stable_id(prefix, value):
    return prefix + '-' + hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:24]


def comparison_key(candidate):
    data = candidate.model_dump(mode='json')
    return json.dumps({k: data[k] for k in KEY_FIELDS}, sort_keys=True)


def quantum(candidate):
    # Preserve reported trailing zeroes; parentheses and Unicode signs don't
    # affect precision. Unsupported numeric formats never establish tolerance.
    raw = candidate.raw_numeric_text.strip().strip('()').replace(',', '').replace('\u2212', '-')
    if not re.fullmatch(r'-?\d+(?:\.\d+)?', raw):
        return None
    return Decimal(10) ** Decimal(raw).as_tuple().exponent * candidate.scale


def precision_matches(a, b):
    if a.value == b.value:
        return True
    qa, qb = quantum(a), quantum(b)
    if qa is None or qb is None or qa == qb:
        return False
    coarse, fine, step = (a, b, qa) if qa > qb else (b, a, qb)
    with localcontext() as ctx:
        ctx.prec = 60
        rounded = (fine.value / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step
    return rounded == coarse.value


def select_group(candidates, context):
    """Return typed group plus per-candidate decisions; no model or gold input."""
    if not candidates or len({comparison_key(c) for c in candidates}) != 1:
        raise ValueError('Selection requires one nonempty comparable group.')
    candidates = sorted(candidates, key=lambda c: c.candidate_id)
    first = candidates[0]
    decisions, eligible = {}, []
    def decision(c, status, code, reason):
        decisions[c.candidate_id] = {'status': status, 'reason_code': code, 'reason': reason,
                                    **context[c.candidate_id]}
    for c in candidates:
        if not all(c.validation_results.get(k) is True for k in REQUIRED_CHECKS) or not all(c.validation_results.values()):
            decision(c, 'rejected', 'R1_INVALID', 'Required source/context validation failed or is unavailable.')
        elif c.annuality != 'annual' or c.basis != 'gaap' or c.scope != 'consolidated' or c.attribution in ('', 'unknown'):
            decision(c, 'rejected', 'R2_CONTEXT', 'Main series requires annual GAAP whole-company facts with explicit attribution.')
        elif context[c.candidate_id].get('crosscheck_conflict'):
            decision(c, 'conflicting', 'R1_CROSSCHECK', 'Company Facts disagrees with the cited filing; unresolved cross-check.')
        else:
            eligible.append(c)
    duplicate_values = defaultdict(list)
    for c in eligible:
        duplicate_values[c.value].append(c.candidate_id)
    duplicates = [ids for ids in duplicate_values.values() if len(ids) > 1]
    chosen = None
    conflicts, reasons = [], []
    latest = None
    if any(d['status'] == 'conflicting' for d in decisions.values()):
        conflicts.append('Unresolved Company Facts cross-check.')
    if eligible:
        latest = max(eligible, key=lambda c: (context[c.candidate_id]['filing_date'], c.candidate_id))
        tier = max(context[c.candidate_id]['clarity'] for c in eligible)
        pool = [c for c in eligible if context[c.candidate_id]['clarity'] == tier]
        for c in eligible:
            if c not in pool:
                decision(c, 'alternative', 'R3_PRESENTATION', 'Prefer the complete statement/EPS-note presentation over an isolated mention.')
        # Only an explicit label on the newest presentation can supersede older
        # differing values. Same-date contradictory presentations remain conflicts.
        newest_date = max(context[c.candidate_id]['filing_date'] for c in pool)
        newest = [c for c in pool if context[c.candidate_id]['filing_date'] == newest_date]
        adjusted = [c for c in newest if context[c.candidate_id]['adjustment']]
        if adjusted:
            replacement = adjusted[0]
            # Latest unlabelled repetitions of the adjusted value are acceptable;
            # disagreeing cells in that same filing/date are not silently discarded.
            if all(precision_matches(replacement, c) for c in newest):
                for c in pool:
                    if c not in newest:
                        decision(c, 'alternative', 'R4_DOCUMENTED_COMPARATIVE',
                                 'Superseded by a newer explicitly restated/recast/split-adjusted presentation.')
                pool = newest
                reasons.append('R4_DOCUMENTED_COMPARATIVE: Newest presentation explicitly labels the adjustment; original sources retained.')
        # Pairwise agreement avoids chaining through a low-precision bridge.
        if any(not precision_matches(a, b) for i, a in enumerate(pool) for b in pool[i + 1:]):
            conflicts.append('R4_UNEXPLAINED_DISAGREEMENT: Comparable values disagree beyond reported rounding; no documented replacement.')
        if conflicts:
            reasons.append('R4_CONFLICT: Unresolved disagreement; no comparable value selected.')
            for c in pool:
                decision(c, 'conflicting', 'R4_CONFLICT', 'Unresolved disagreement; no value selected.')
        else:
            chosen = max(pool, key=lambda c: (context[c.candidate_id]['filing_date'],
                bool(context[c.candidate_id]['adjustment']),
                -(quantum(c) or Decimal('1E30')), context[c.candidate_id]['visible_labels'], c.candidate_id))
            for c in pool:
                if c == chosen:
                    decision(c, 'selected', 'R6_CITATION', 'Latest valid comparable presentation; reported precision and visible labels break ties.')
                else:
                    code = 'R6_DUPLICATE' if c.value == chosen.value else 'R6_PRECISION'
                    decision(c, 'alternative', code, 'Equivalent repeated value; not independent support.' if c.value == chosen.value
                             else 'Difference explained by reported rounding precision; original value retained.')
            reasons.append('R6_CITATION: Latest valid comparable presentation selected; repeated evidence is not independent corroboration.')
    data = first.model_dump(mode='json')
    group_reasons = reasons or ['R4_CONFLICT: Unresolved cross-check.' if conflicts
                                else 'R1_R2: No eligible comparable candidate.']
    group_data = {**{k: data[k] for k in KEY_FIELDS},
        'candidate_ids': [c.candidate_id for c in candidates],
        'selected_id': chosen.candidate_id if chosen else None,
        'duplicate_groups': duplicates,
        'selection_reasons': group_reasons,
        'unresolved_conflicts': conflicts,
        'latest_comparative_id': latest.candidate_id if latest else None}
    group = CandidateGroup(group_id=stable_id('group', {'version': VERSION, 'group': group_data, 'decisions': decisions}),
                           **group_data)
    return group, decisions


class ReconciliationService:
    def __init__(self, settings):
        self.settings = settings
        self.repo = Repository(settings.data_dir)
        self._documents = {}

    def latest(self, run_id):
        indexes = [json.loads(self.repo.read(run_id, a['artifact_id'])) for a in self.repo.artifacts(run_id)
                   if a['artifact_id'].startswith('reconcile-index-')]
        if not indexes:
            return None, [], []
        index = max(indexes, key=lambda i: i['created_at'])
        return (index, [CandidateGroup.model_validate_json(self.repo.read(run_id, gid)) for gid in index['group_ids']],
                [AnnualObservation.model_validate_json(self.repo.read(run_id, oid)) for oid in index['observation_ids']])

    def context(self, run_id, candidate, checks):
        refs = [EvidenceRef.model_validate_json(self.repo.read(run_id, eid)) for eid in candidate.evidence_ids]
        filings = [FilingRecord.model_validate_json(self.repo.read(run_id, e.filing_id)) for e in refs]
        # Multi-source proposals must not borrow a newer filing's date or an
        # unrelated source's adjustment label. Choose one actual presentation.
        ref = refs[max(range(len(refs)), key=lambda i: filings[i].filing_date)]
        filing = FilingRecord.model_validate_json(self.repo.read(run_id, ref.filing_id))
        block = SourceBlock.model_validate_json(self.repo.read(run_id, ref.block_id))
        cells = [TableCell.model_validate_json(self.repo.read(run_id, cid)) for cid in ref.cell_ids]
        headers = [TableCell.model_validate_json(self.repo.read(run_id, hid)) for c in cells
                   for hid in c.header_cell_ids + c.year_cell_ids]
        label_text = candidate.raw_label + ' ' + ' '.join(h.normalized_text for h in headers)
        # A table-wide caption can label all its columns; free-form body text
        # cannot establish a replacement relationship.
        if block.table_id:
            from profitlab.documents.service import SourceService
            key = (run_id, ref.filing_id)
            if key not in self._documents:
                self._documents[key] = SourceService(self.settings).document(run_id, ref.filing_id)[1]
            doc = self._documents[key]
            label_text += ' ' + doc['index']['tables'][block.table_id]['caption']
        match = re.search(r'\b(restated|recast|split[- ]adjusted)\b', label_text, re.IGNORECASE)
        label_context = ' '.join(block.heading_path).lower()
        clarity = 2 if block.kind == 'table' and re.search(r'income statement|operations|eps|diluted.share', label_context) else 1 if block.kind == 'table' else 0
        return {'filing_date': filing.filing_date.isoformat(), 'filing_id': filing.filing_id,
            'accession': filing.accession, 'report_date': filing.report_date.isoformat(),
            'clarity': clarity, 'visible_labels': sum(bool(c.year_cell_ids) for c in cells),
            'adjustment': match.group(0).lower() if match else None,
            'adjustment_source': ref.evidence_id if match else None,
            'evidence_ids': candidate.evidence_ids, 'reported_quantum': str(quantum(candidate)),
            'source_count': len({(e.filing_id, e.block_id, tuple(e.cell_ids)) for e in refs}),
            'crosscheck_conflict': isinstance(checks, dict) and checks.get(candidate.candidate_id, {}).get('status') == 'conflict'}

    def progress(self, run_id):
        self._documents = {}
        run = self.repo.manifest(run_id)
        if run.mode == 'replay':
            raise ValueError('Replay reconciliation is read-only.')
        extraction, attempts = ExtractionService(self.settings).latest(run_id)
        if not extraction:
            raise ValueError('Run extraction before reconciliation.')
        facts = {a.candidate.candidate_id: a.candidate for a in attempts if a.candidate and a.status == 'accepted'}
        context = {cid: self.context(run_id, c, extraction.get('company_facts')) for cid, c in facts.items()}
        trace = TraceRecorder(self.repo, run_id, self.settings.redactor())
        groups, decisions = [], {}
        with trace.operation('Reconcile candidates', {'version': VERSION, 'extraction': extraction,
                              'candidate_ids': sorted(facts)}, stage='reconcile') as out:
            buckets = defaultdict(list)
            for c in facts.values():
                buckets[comparison_key(c)].append(c)
            for key in sorted(buckets):
                group, resolved = select_group(buckets[key], context)
                self.repo.save_contract(run_id, group.group_id, group)
                groups.append(group)
                decisions.update(resolved)
                trace.emit(kind='selection', span_id=group.group_id, stage='reconcile', summary='Comparable group selection',
                           result={'group': group.model_dump(mode='json'), 'decisions': resolved})
            observations, coverage = self.coverage(run, facts, groups, context)
            for obs in observations:
                self.repo.save_contract(run_id, obs.observation_id, obs)
            passages = self.passages(run_id, attempts)
            out.update(groups=len(groups), selected=sum(g.selected_id is not None for g in groups),
                       conflicts=sum(bool(g.unresolved_conflicts) for g in groups), coverage=coverage)
        now = datetime.now(UTC)
        index = {'created_at': now.isoformat(), 'version': VERSION, 'synthetic': run.mode == 'demo',
            'extraction_created_at': extraction['created_at'], 'group_ids': [g.group_id for g in groups],
            'observation_ids': [o.observation_id for o in observations], 'decisions': decisions,
            'coverage': coverage, 'passages': passages,
            'support_policy': 'Repeated/overlapping presentations do not add independent support; all source references retained.'}
        self.repo.put(run_id, 'reconcile-index-' + uuid4().hex, json.dumps(index).encode())
        partial = len(coverage) < run.requested_years or any(row['metrics'][m.value]['status'] != 'selected' for row in coverage for m in MAIN_METRICS)
        snapshot = run.model_copy(update={'stage': 'reconcile', 'updated_at': now,
            'covered_years': [row['fiscal_year'] for row in coverage], 'status': 'partial' if partial or run.status == 'partial' else 'completed',
            'versions': {**run.versions, 'reconciliation': VERSION},
            'limitation': 'Reconciled evidence only; calculations and narrative report are not implemented. Missing/conflicting data and unsupported extraction contexts remain visible.'})
        self.repo.save_contract(run_id, 'manifest-reconcile-' + uuid4().hex, snapshot)
        return snapshot

    def coverage(self, run, facts, groups, context):
        # Filing years without validated exact intervals still get a missing row;
        # never invent their fiscal start dates.
        years = sorted(set(run.covered_years) | {c.period.fiscal_year for c in facts.values()}, reverse=True)[:run.requested_years]
        observations, rows = [], []
        for year in years:
            year_groups = [g for g in groups if g.period.fiscal_year == year and g.annuality == 'annual']
            periods = {g.period.model_dump_json(): g.period for g in year_groups if g.scope == 'consolidated' and g.basis == 'gaap'}
            selected, missing, flags, eids, metrics = {}, {}, [], [], {}
            for metric in Metric:
                options = [g for g in year_groups if g.metric == metric and g.scope == 'consolidated' and g.basis == 'gaap']
                winners = [g for g in options if g.selected_id]
                reason = 'No eligible annual GAAP candidate.'
                state = 'missing'
                if any(g.unresolved_conflicts for g in options) or len(winners) > 1 or len(periods) > 1:
                    state, reason = 'conflicting', 'Unresolved values, fiscal intervals, units, attribution or share classes; no silent combination.'
                elif winners:
                    g = winners[0]
                    selected[metric] = g.selected_id
                    eids.extend(eid for cid in g.candidate_ids for eid in facts[cid].evidence_ids)
                    state, reason = 'selected', '; '.join(g.selection_reasons)
                    if metric in (Metric.EPS_DILUTED, Metric.SHARES_DILUTED):
                        # Record per-share basis explicitly; calculations must not
                        # mix adjusted and original years without a full series.
                        adjustment = context[g.selected_id]['adjustment']
                        flag = 'per_share_basis:' + (adjustment + ':' + context[g.selected_id].get('accession', 'unknown')
                                                     if adjustment else 'reported')
                        flags.append(flag)
                else:
                    if options:
                        state = 'unsupported'
                        reason = 'Candidates rejected by context/source rules.'
                if state != 'selected':
                    missing[metric] = state
                metrics[metric.value] = {'status': state, 'candidate_id': selected.get(metric),
                    'reason': reason, 'group_ids': [g.group_id for g in options]}
            # Distinct EPS/share classes or currencies must remain visible even
            # if each metric independently has a single winning group.
            picked = [facts[cid] for cid in selected.values()]
            classes = {c.share_class for c in picked if c.metric in (Metric.EPS_DILUTED, Metric.SHARES_DILUTED, Metric.NET_INCOME_COMMON)}
            currencies = {c.currency for c in picked if c.currency}
            if len(classes) > 1 or len(currencies) > 1:
                flags.append('Incompatible share classes/currencies across selected metrics; automated comparisons require compatible inputs.')
            if len(periods) == 1:
                period = next(iter(periods.values()))
                if not 330 <= (period.end - period.start).days <= 380:
                    flags.append('Fiscal transition/nonstandard annual duration; suppress automated annualized comparisons.')
                obs = AnnualObservation(observation_id=stable_id('observation', {'version': VERSION, 'year': year, 'selected': selected, 'missing': missing, 'groups': [g.group_id for g in year_groups]}),
                    period=period, selected_facts=selected, missingness=missing,
                    comparability_flags=sorted(set(flags)), evidence_ids=sorted(set(eids)))
                observations.append(obs)
            rows.append({'fiscal_year': year, 'periods': [p.model_dump(mode='json') for p in periods.values()],
                         'metrics': metrics, 'comparability_flags': sorted(set(flags))})
        bases = {flag for row in rows for flag in row['comparability_flags'] if flag.startswith('per_share_basis:')}
        if len(bases) > 1:
            warning = 'Mixed original/adjusted per-share bases; series comparability unresolved.'
            for row in rows:
                row['comparability_flags'].append(warning)
            observations = [o.model_copy(update={'comparability_flags': o.comparability_flags + [warning]}) for o in observations]
        # Hash the finalized payload, including cross-year comparability flags,
        # so a changed series cannot overwrite a historical observation.
        finalized = []
        for obs in observations:
            payload = obs.model_dump(mode='json', exclude={'observation_id'})
            finalized.append(obs.model_copy(update={'observation_id': stable_id('observation',
                {'version': VERSION, 'payload': payload})}))
        return finalized, rows

    def passages(self, run_id, attempts):
        passages = {}
        for a in attempts:
            if a.status != 'accepted' or a.candidate or not a.evidence_id:
                continue
            ref = EvidenceRef.model_validate_json(self.repo.read(run_id, a.evidence_id))
            filing = FilingRecord.model_validate_json(self.repo.read(run_id, ref.filing_id))
            quote = ' '.join(ref.exact_segments)
            topic = 'restatement/share basis' if re.search(r'restat|recast|split', quote, re.IGNORECASE) else 'earnings/EPS change'
            key = (filing.report_date.year, topic, ' '.join(quote.split()))
            item = passages.setdefault(key, {'year': key[0], 'topic': topic, 'quote': quote,
                'attribution': a.proposal.get('attribution', 'Source passage; attribution not established'), 'evidence_ids': []})
            item['evidence_ids'].append(a.evidence_id)
        return sorted(passages.values(), key=lambda p: (p['year'], p['topic'], p['quote']), reverse=True)
