"""Post-discovery SEC Company Facts retrieval and conservative normalization."""
import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from profitlab.sec.client import COMPANY_FACTS, SECClient, SECError

from .contracts import StructuredFact
from .fact_source_service import FactSourceService
from .presentation_service import PresentationService
from .source_service import _V2Trace

# This narrow mapping is deliberately application-owned, not provider input.  It
# connects the user-visible targets to SEC concepts without exposing them during
# Jev discovery or findings extraction.
FACT_TARGETS = (
    ('net_income_consolidated', 'NetIncomeLoss', 'USD', 'Consolidated net income'),
    ('net_income_consolidated', 'ProfitLoss', 'USD', 'Consolidated profit or loss'),
    ('net_income_common', 'NetIncomeLossAvailableToCommonStockholdersBasic', 'USD',
     'Net income available to common stockholders (basic)'),
    ('net_income_common', 'NetIncomeLossAvailableToCommonStockholdersDiluted', 'USD',
     'Net income available to common stockholders (diluted)'),
    ('eps_diluted', 'EarningsPerShareDiluted', 'USD/shares', 'Diluted earnings per share'),
    ('weighted_average_shares_diluted', 'WeightedAverageNumberOfDilutedSharesOutstanding',
     'shares', 'Diluted weighted-average shares'),
)


class CompanyFactsService:
    def __init__(self, settings, repository):
        self.settings, self.repo = settings, repository

    def load(self, run):
        """Fetch exactly once after findings are sealed, then persist raw and normalized data."""
        findings = self.repo.stage(run.run_id, 'findings')
        if findings.status != 'completed':
            raise ValueError('Findings must be sealed before Company Facts retrieval begins.')
        filing = self.repo.filing(run.run_id)
        cik = str(filing.get('cik', '')).zfill(10)
        if len(cik) != 10 or not cik.isdigit():
            raise ValueError('Discovered filing lacks a valid company CIK for Company Facts.')
        if not self.settings.sec_contact_ready():
            raise ValueError('SEC_USER_AGENT is required before Company Facts retrieval.')
        client = SECClient(self.settings, _V2Trace(self.settings.redactor()))
        try:
            dataset = client.company_facts(cik)
            source_url = f'{COMPANY_FACTS}CIK{cik}.json'
        except SECError as error:
            raise ValueError(str(error)) from None
        finally:
            client.close()
        raw = json.dumps(dataset, sort_keys=True, separators=(',', ':')).encode()
        source_hash = hashlib.sha256(raw).hexdigest()
        facts, alternatives = self.normalize(dataset, filing)
        self.repo.save_company_fact_dataset(run.run_id, cik=cik, source_url=source_url,
                                           source_hash=source_hash, payload=raw)
        self.repo.save_structured_facts(run.run_id, facts)
        presentations = PresentationService(self.settings, self.repo).enrich(run, facts)
        sources = FactSourceService(self.settings, self.repo).enrich(run, facts, presentations)
        self.repo.save_fact_summary(run.run_id, {
            'cik': cik, 'source_url': source_url, 'source_hash': source_hash,
            'supported_facts': len(facts), 'alternatives': alternatives,
            'mapping': [{'metric': metric, 'concept': concept, 'unit': unit, 'label': label}
                        for metric, concept, unit, label in FACT_TARGETS],
            'provenance': 'SEC Company Facts JSON',
            'source_mapping': {
                'method': 'inline-visible-1',
                'statuses': {status: sum(item.status == status for item in sources)
                             for status in ('verified', 'ambiguous', 'hidden_only', 'unavailable')},
            },
            'presentation': {
                'method': 'sec-pre-num-v1',
                'statuses': {status: sum(item.status == status for item in presentations)
                             for status in ('matched', 'ambiguous', 'missing', 'retrieval_failed')},
                'meaning': 'SEC statement presentation rows, separate from verified canonical filing lines.',
            },
        })
        return facts, alternatives, source_hash

    @classmethod
    def inspection_view(cls, *, summary: dict | None = None,
                        finding_count: int = 0, settings=None):
        """Return the server-owned Facts explainer contract.

        The browser receives the actual configured concept mapping and durable
        accounting, but does not recreate the SEC selection policy.
        """
        summary = summary or {}
        mapping = [
            {'metric': metric, 'concept': concept, 'unit': unit, 'label': label}
            for metric, concept, unit, label in FACT_TARGETS
        ]
        alternatives = summary.get('alternatives', {})
        return {
            'sealed_findings': finding_count,
            'supported_facts': summary.get('supported_facts', 0),
            'alternative_groups': len(alternatives),
            'provenance': summary.get('provenance', 'SEC Company Facts JSON'),
            'checkpoint': {
                'accepts': {'findings_completion': 'sealed stage status is a scheduling gate, not a value input',
                            'filing_identity': 'discovered company CIK and annual filing accession'},
                'does': 'Requires the findings checkpoint to complete before the independent SEC-data lane can begin. Finding values are not read for normalization.',
                'outputs': {'eligible_request': 'one company CIK scoped to the selected filing'},
                'guarantee': 'Company Facts cannot enter discovery, scoring, or findings generation.',
            },
            'retrieve': {
                'accepts': {'eligible_request': 'one company CIK',
                            'source': 'SEC Company Facts JSON endpoint'},
                'does': 'Fetches the Company Facts dataset for one CIK and retains its source URL and content hash.',
                'outputs': {'company_facts_dataset': 'raw SEC JSON with durable provenance'},
                'guarantee': 'Company Facts alone supplies comparator values; later retained-HTML inspection supplies provenance only.',
            },
            'normalize': {
                'accepts': {'company_facts_dataset': 'raw SEC JSON',
                            'filing_identity': 'accession, form, and annual report date'},
                'does': 'Selects configured annual, same-accession facts with exact Decimal values and literal units; ordered concepts are fallbacks for one metric. Checkpoints the raw dataset and selected comparator values before presentation enrichment.',
                'outputs': {'structured_facts': 'configured annual metric, Decimal, period, unit, and filing provenance'},
                'guarantee': 'Duplicate or ineligible candidates remain diagnostics; a selected fact is never guessed or converted.',
                'policy': {'concept_mapping': mapping},
            },
            'store': {
                'accepts': {'structured_facts': 'normalized independent annual facts',
                            'alternatives': 'unselected or duplicate candidate diagnostics'},
                'does': 'Persists the raw Company Facts dataset, normalized comparator values, mappings, alternatives, and separate statement and canonical-line inspection provenance. Enrichment failure never removes a comparator.',
                'outputs': {'comparison_input': 'immutable structured facts available only to Evaluate'},
                'guarantee': 'Persisting Facts cannot revise sealed findings or their source quotes.',
                'policy': {
                    'presentation_rows': 'PRE.line is statement presentation order, never a canonical filing line.',
                    'join': 'Exact accession, concept namespace/tag and taxonomy version, annual period bucket, unit, Decimal, and consolidated dimensionless context. NUM dates/durations are rounded by SEC.',
                    'taxonomy': 'Company Facts lacks taxonomy year; retain all matching versions and mark multiple versions ambiguous.',
                    'saved_presentation': summary.get('presentation', 'Unavailable: no saved presentation provenance.'),
                    'saved_source_mapping': summary.get('source_mapping', 'Unavailable: no saved source mappings.'),
                },
            },
            'enrich': {
                'accepts': {'selected_facts': 'stable fact IDs and exact Company Facts identities',
                            'filing_date': 'submission quarter selects the SEC archive'},
                'does': 'Joins bounded SEC SUB/NUM/PRE records and validates report filenames against the filing directory. Then inspects retained Inline XBRL for exact concept, entity, period, unit and Decimal matches, reproducing canonicalization to verify visible cells and anchors. Saves provenance separately from comparator values.',
                'outputs': {'fact_presentation': 'matched, ambiguous, missing, or retrieval_failed statement provenance',
                            'fact_source_mapping': 'verified, ambiguous, hidden_only, or unavailable canonical-line provenance'},
                'guarantee': 'PRE.line is a presentation row, not a canonical filing line. Missing enrichment never blocks evaluation or changes comparator values.',
                'policy': {'saved_presentation': summary.get('presentation', 'Unavailable: no saved presentation provenance.'),
                           'current_enrichment_limits': PresentationService.inspection_limits(settings) if settings else 'Unavailable without current settings.',
                           'saved_source_mapping': summary.get('source_mapping', 'Unavailable: no saved source mappings.'),
                           'source_mapping_limits': '50 MB retained HTML; 100,000 Inline occurrences; 1,000 locations per fact; 4 MB run projection. Unsupported transforms and source disagreement receive no invented link.',
                           'period_resolution': 'NUM rounds periods; Inline source mapping requires exact start/end dates and consolidated dimensionless entity context.'},
            },
        }

    @staticmethod
    def normalize(dataset, filing):
        facts_root = dataset.get('facts', {}).get('us-gaap', {}) if isinstance(dataset, dict) else {}
        expected_accession = filing.get('accession') or '0001234567-25-000001'
        expected_form = filing.get('form', '10-K')
        expected_end = filing.get('report_date')
        selected, alternatives = [], {}
        selected_metrics = set()
        for metric, concept, unit, _label in FACT_TARGETS:
            # Concepts on the same metric line are ordered fallbacks, not two
            # independently expected discoveries.  A filing may report both
            # NetIncomeLoss and ProfitLoss for the same annual period; comparing
            # a single visible finding against both creates a false ambiguous
            # oracle rather than evidence of a discovery failure.
            if metric in selected_metrics:
                continue
            entries = facts_root.get(concept, {}).get('units', {}).get(unit, [])
            candidates = []
            for entry in entries:
                try:
                    start, end = date.fromisoformat(entry['start']), date.fromisoformat(entry['end'])
                    value = Decimal(str(entry['val']))
                    filed = date.fromisoformat(entry['filed'])
                except (KeyError, TypeError, ValueError, InvalidOperation):
                    continue
                duration = (end - start).days + 1
                if (entry.get('accn') != expected_accession or entry.get('form') != expected_form or
                        entry.get('fp') != 'FY' or end.isoformat() != expected_end or
                        not 300 <= duration <= 400 or not value.is_finite()):
                    continue
                candidates.append((entry, value, start, end, filed))
            # A deterministic choice is necessary because comparative facts may be repeated.
            candidates.sort(key=lambda item: (item[0].get('frame') is not None,
                                               -item[4].toordinal(), str(item[0].get('val')),
                                               item[0].get('accn', '')))
            if not candidates:
                continue
            entry, value, start, end, filed = candidates[0]
            identity = hashlib.sha256(f'{metric}|{concept}|{unit}|{expected_accession}|{start}|{end}|{value}'.encode()).hexdigest()[:20]
            selected.append(StructuredFact(fact_id=f'fact-{identity}', concept=f'us-gaap:{concept}',
                metric=metric, value=value, unit=unit, period_start=start, period_end=end,
                accession=expected_accession, form=expected_form, filed_date=filed))
            selected_metrics.add(metric)
            if len(candidates) > 1:
                alternatives[f'fact-{identity}'] = [
                    {'value': str(item[1]), 'filed_date': item[4].isoformat(),
                     'frame': item[0].get('frame'), 'accession': item[0].get('accn')}
                    for item in candidates[1:]]
        return selected, alternatives
