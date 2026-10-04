"""Acquire a primary filing into V2 and make its visible source canonical."""
from contextlib import contextmanager
from datetime import UTC, datetime

from profitlab.sec.client import SECClient, SECError
from profitlab.sec.service import DiscoveryService

from .canonical import canonicalize_html


class _V2Trace:
    """SECClient needs operation recording; V2 publishes stage events instead."""
    def __init__(self, redactor):
        self.redact = redactor

    @contextmanager
    def operation(self, _name, _request, **_metadata):
        output = {}
        yield output


class V2SourceService:
    @staticmethod
    def inspection_view(*, request: str, received: str, stored: str) -> dict:
        return {
            'request': {
                'accepts': 'Selected ticker and annual filing identity.',
                'does': 'Locates and requests the SEC primary annual filing for the report.',
                'outputs': received,
                'guarantee': 'The document identity is retained before downstream transformation.',
            },
            'convert': {
                'accepts': received,
                'does': ('Converts filing HTML to canonical visible text, removing hidden and '
                         'Inline XBRL-only content and metadata.'),
                'outputs': 'Sanitized visible lines.',
                'guarantee': 'No source text is invented or supplied by hidden metadata.',
            },
            'store': {
                'accepts': 'Sanitized visible lines and source HTML anchors.',
                'does': 'Persists stable line numbers and sanitized HTML anchors.',
                'outputs': stored,
                'guarantee': 'Later source links resolve to the retained line-addressable record.',
            },
        }

    def __init__(self, settings, repository):
        self.settings, self.repo = settings, repository

    def acquire(self, run):
        """Store one primary visible filing in the V2 workspace."""
        if not self.settings.sec_contact_ready():
            raise ValueError('SEC_USER_AGENT is required and must include a real contact email (for example, "ProfitLab you@example.com").')
        trace = _V2Trace(self.settings.redactor())
        client = SECClient(self.settings, trace)
        try:
                # Reuse the well-tested selection rules, but keep all resulting data in V2.
                result = DiscoveryService(self.settings).discover(client, run.ticker, 1, synthetic=False)
                if result.outcome != 'found' or not result.filings:
                    raise ValueError(result.message)
                selected = next((item for item in result.filings if item.form == '10-K'), result.filings[0])
                raw_html, _content_type = client.get(selected.primary_document_url, bytes,
                                                     stage='source', document=True)
                filing_id = selected.filing_id
                filing = {'filing_id': selected.filing_id, 'form': selected.form,
                          'report_date': selected.report_date.isoformat(),
                          'accession': selected.accession,
                          'cik': result.company.cik,
                          'company_name': result.company.name,
                          'source_url': selected.primary_document_url,
                          'provenance': 'SEC primary filing HTML'}
        except SECError as error:
            raise ValueError(str(error)) from None
        finally:
            client.close()
        document_id = 'document-' + filing_id.removeprefix('filing-')
        document, visible_html = canonicalize_html(raw_html, document_id=document_id,
                                                    filing_id=filing_id)
        payload = {**filing, 'document_id': document.ref.document_id,
                   'source_hash': document.ref.source_hash, 'line_count': document.ref.line_count,
                   'canonical_version': 'visible-html-1',
                   'retrieved_at': datetime.now(UTC).isoformat()}
        self.repo.save_canonical_document(run.run_id, document, raw_html, visible_html)
        self.repo.save_filing(run.run_id, filing_id, document.ref.source_hash, payload)
        return document, payload
