"""Post-discovery SEC Company Facts retrieval and conservative normalization."""
import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from profitlab.sec.client import COMPANY_FACTS, SECClient, SECError

from .contracts import StructuredFact
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


def offline_company_facts():
    """Saved, labeled fixture only; it does not represent a live SEC response."""
    annual = {'start': '2025-01-01', 'end': '2025-12-31', 'accn': '0001234567-25-000001',
              'form': '10-K', 'filed': '2026-02-15', 'fy': 2025, 'fp': 'FY'}
    return {'cik': 1234567, 'entityName': 'Synthetic Demo Corporation', 'facts': {'us-gaap': {
        'NetIncomeLoss': {'units': {'USD': [{**annual, 'val': 180000000},
                                           {**annual, 'val': 179999999, 'frame': 'CY2025'}]}},
        'EarningsPerShareDiluted': {'units': {'USD/shares': [{**annual, 'val': '2.00'}]}},
        'WeightedAverageNumberOfDilutedSharesOutstanding': {
            'units': {'shares': [{**annual, 'val': 90000000}]}},
    }}}


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
        if run.mode == 'offline':
            dataset, source_url = offline_company_facts(), 'saved synthetic Company Facts fixture'
        else:
            if not self.settings.sec_contact_ready():
                raise ValueError('Configure SEC_USER_AGENT with a real contact email before live Company Facts retrieval.')
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
        self.repo.save_fact_summary(run.run_id, {
            'cik': cik, 'source_url': source_url, 'source_hash': source_hash,
            'supported_facts': len(facts), 'alternatives': alternatives,
            'mapping': [{'metric': metric, 'concept': concept, 'unit': unit, 'label': label}
                        for metric, concept, unit, label in FACT_TARGETS],
            'provenance': ('saved synthetic Company Facts fixture' if run.mode == 'offline'
                           else 'SEC Company Facts JSON'),
        })
        return facts, alternatives, source_hash

    @staticmethod
    def normalize(dataset, filing):
        facts_root = dataset.get('facts', {}).get('us-gaap', {}) if isinstance(dataset, dict) else {}
        expected_accession = filing.get('accession') or '0001234567-25-000001'
        expected_form = filing.get('form', '10-K')
        expected_end = filing.get('report_date')
        selected, alternatives = [], {}
        for metric, concept, unit, _label in FACT_TARGETS:
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
            if len(candidates) > 1:
                alternatives[f'fact-{identity}'] = [
                    {'value': str(item[1]), 'filed_date': item[4].isoformat(),
                     'frame': item[0].get('frame'), 'accession': item[0].get('accn')}
                    for item in candidates[1:]]
        return selected, alternatives
