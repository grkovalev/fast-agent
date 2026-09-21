"""Acquire a primary filing into V2 and make its visible source canonical."""
from contextlib import contextmanager
from datetime import UTC, datetime

from profitlab.sec.client import SECClient, SECError
from profitlab.sec.fixtures import FIXTURES
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
    def __init__(self, settings, repository):
        self.settings, self.repo = settings, repository

    def acquire(self, run):
        """Store one primary visible filing without creating or reading a V1 run."""
        if run.mode == 'offline':
            filing_id = 'filing-synthetic-2025'
            raw_html = (FIXTURES / 'annual-2025.html').read_bytes()
            filing = {'filing_id': filing_id, 'form': '10-K', 'report_date': '2025-12-31',
                      'source_url': 'synthetic:annual-2025.html', 'provenance': 'saved synthetic fixture'}
        else:
            if not self.settings.sec_contact_ready():
                raise ValueError('Configure SEC_USER_AGENT with a real contact email before live source retrieval.')
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
