"""Bounded, inspection-only SEC PRE/NUM enrichment after findings seal."""
import calendar
import csv
import hashlib
import io
import json
import re
import time
import zipfile
import zlib
from datetime import date
from decimal import Decimal, InvalidOperation

from profitlab.sec.client import SECClient, SECError

from .contracts import (
    FactPresentation,
    StatementDatasetRef,
    StatementLocation,
    StatementNumericRecord,
)
from .source_service import _V2Trace


class PresentationService:
    def __init__(self, settings, repository):
        self.settings, self.repo = settings, repository

    @staticmethod
    def inspection_limits(settings):
        return {name: getattr(settings, name) for name in (
            'sec_total_timeout', 'sec_statement_archive_bytes', 'sec_statement_expanded_bytes',
            'sec_statement_max_rows', 'sec_statement_projection_rows',
            'sec_statement_projection_bytes',
        )}

    def enrich(self, run, facts):
        self.repo.require_findings_seal(run.run_id)
        if not facts:
            self.repo.save_fact_presentations(run.run_id, [])
            return []
        filing = self.repo.filing(run.run_id)
        client = SECClient(self.settings, _V2Trace(self.settings.redactor()))
        dataset = None
        dataset_payload = None
        try:
            if not self.settings.sec_contact_ready():
                raise ValueError('SEC_USER_AGENT is required for presentation enrichment.')
            filed = date.fromisoformat(filing['filing_date'])
            quarter = f'{filed.year}q{(filed.month - 1) // 3 + 1}'
            raw, metadata = client.statement_archive(quarter)
            dataset = StatementDatasetRef(source_url=metadata['url'], source_hash=metadata['sha256'],
                retrieved_at=metadata['retrieved_at'], accession=filing['accession'], quarter=quarter)
            projection = self.project(raw, filing, facts, deadline=client.deadline)
            index_error = None
            try:
                index = client.filing_index(filing['cik'], filing['accession'])
            except SECError as error:
                index, index_error = {}, str(error)
            presentations = self.match(projection, filing, facts, dataset, index)
            if index_error:
                presentations = [item.model_copy(update={'diagnostics': [
                    *item.diagnostics, f'Report links unavailable: {index_error}']}) for item in presentations]
            dataset_payload = {'dataset': dataset.model_dump(mode='json'), 'projection': projection,
                 'report_index': {
                     'source_url': f'https://www.sec.gov/Archives/edgar/data/{int(filing["cik"])}/{filing["accession"].replace("-", "")}/index.json',
                     'source_hash': hashlib.sha256(json.dumps(index, sort_keys=True).encode()).hexdigest() if index else None,
                     'verified_report_urls': sorted({location.report_url for item in presentations
                                                    for location in item.locations if location.report_url}),
                     'diagnostic': index_error,
                 }}
        except (SECError, ValueError, KeyError, TypeError, OSError, csv.Error,
                zipfile.BadZipFile, RuntimeError, zlib.error, EOFError) as error:
            reason = self.settings.redactor().text(str(error))[:1000]
            presentations = [FactPresentation(fact_id=fact.fact_id, status='retrieval_failed',
                dataset=dataset, diagnostics=[f'Presentation enrichment unavailable: {reason}']) for fact in facts]
        finally:
            client.close()
        self.repo.save_fact_presentations(run.run_id, presentations, dataset_payload=dataset_payload)
        return presentations

    def project(self, raw, filing, facts, *, deadline=None):
        """Stream TSV members without extraction; retain only the bounded accession/tag slice."""
        deadline = deadline if deadline is not None else time.monotonic() + self.settings.sec_total_timeout
        tags = {fact.concept.split(':', 1)[1] for fact in facts}
        accession = filing['accession']
        result = {'sub': [], 'pre': [], 'num': []}
        count = retained = expanded = projected_bytes = 0
        required = {
            'sub': {'adsh', 'cik', 'form', 'filed', 'period'},
            'pre': {'adsh', 'report', 'line', 'stmt', 'rfile', 'tag', 'version', 'plabel'},
            'num': {'adsh', 'tag', 'version', 'ddate', 'qtrs', 'uom', 'value', 'coreg'},
        }
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            if len(members) > 20 or sum(item.file_size for item in members) > self.settings.sec_statement_expanded_bytes:
                raise ValueError('Statement archive exceeds expansion limit.')
            for name, retained_rows in result.items():
                matches = [item for item in members if item.filename.lower() == f'{name}.txt']
                if len(matches) != 1:
                    raise ValueError(f'Statement archive lacks one unique {name.upper()} file.')
                with archive.open(matches[0]) as stream:
                    def lines():
                        nonlocal expanded
                        while True:
                            if time.monotonic() >= deadline:
                                raise ValueError('Statement parsing time limit reached.')
                            line = stream.readline(65537)
                            if not line:
                                break
                            expanded += len(line)
                            if len(line) > 65536 or expanded > self.settings.sec_statement_expanded_bytes:
                                raise ValueError('Statement TSV exceeds line/expansion limit.')
                            yield line.decode('utf-8-sig')
                    reader = csv.DictReader(lines(), delimiter='\t')
                    if not required[name] <= set(reader.fieldnames or []):
                        raise ValueError(f'Statement {name.upper()} headers are incomplete.')
                    for row in reader:
                        count += 1
                        if count > self.settings.sec_statement_max_rows:
                            raise ValueError('Statement parsing row limit reached.')
                        if row.get('adsh') != accession or (name != 'sub' and row.get('tag') not in tags):
                            continue
                        if None in row or any(value is None for value in row.values()):
                            raise ValueError('Malformed matching statement row.')
                        retained += 1
                        projected_bytes += len(json.dumps(row).encode())
                        if retained > self.settings.sec_statement_projection_rows:
                            raise ValueError('Statement accession projection limit reached.')
                        if projected_bytes > self.settings.sec_statement_projection_bytes:
                            raise ValueError('Statement accession projection byte limit reached.')
                        retained_rows.append(row)
        submissions = result['sub']
        if not submissions:
            return result
        expected = (str(int(filing['cik'])), filing['form'], filing['filing_date'].replace('-', ''),
                    filing['report_date'].replace('-', ''))
        if len(submissions) != 1 or tuple(submissions[0][key] for key in ('cik', 'form', 'filed', 'period')) != expected:
            raise ValueError('Statement submission does not match retained filing identity.')
        return result

    @staticmethod
    def match(projection, filing, facts, dataset, index):
        base = f'https://www.sec.gov/Archives/edgar/data/{int(filing["cik"])}/{filing["accession"].replace("-", "")}/'
        directory = index.get('directory', {})
        # Even a report name must come from this filing's directory, not a guessed extension.
        expected_directory = base.split('https://www.sec.gov', 1)[1].rstrip('/')
        names = {row.get('name') for row in directory.get('item', []) if isinstance(row, dict)} if directory.get('name', '').rstrip('/') == expected_directory else set()
        result = []
        for fact in facts:
            namespace, tag = fact.concept.split(':', 1)
            records, locations = {}, {}
            diagnostics = [
                'NUM period ends are rounded to month-end; durations are rounded to quarters. PRE rows are presentation order, not canonical filing lines.',
                'PRE identifies concept presentations without numeric-cell or dimensional context coordinates. These locations do not prove an exact visible fact occurrence.',
            ]
            rejected_units = set()
            for row in projection['num'] if projection['sub'] else []:
                version = row['version']
                if row['adsh'] != fact.accession or row['tag'] != tag or not re.fullmatch(re.escape(namespace) + r'/\d{4}', version):
                    continue
                try:
                    value = Decimal(row['value'])
                    end = date(fact.period_end.year, fact.period_end.month,
                               calendar.monthrange(fact.period_end.year, fact.period_end.month)[1])
                    if (row['ddate'] != end.strftime('%Y%m%d') or row['qtrs'] != '4'
                            or value != fact.value or not value.is_finite()
                            or fact.period_start is None or not 300 <= (fact.period_end - fact.period_start).days + 1 <= 400):
                        continue
                    if row.get('coreg') or row.get('segments'):
                        continue  # Company Facts exposes entity-level, dimensionless comparator values.
                    if row['uom'] != fact.unit:
                        rejected_units.add(row['uom'])
                        continue
                    record = StatementNumericRecord(tag=tag, taxonomy_version=version,
                        period_end_month=end, duration_quarters=4, unit=fact.unit, value=value)
                    records[record.model_dump_json()] = record
                except (ValueError, InvalidOperation):
                    continue
            versions = {record.taxonomy_version for record in records.values()}
            for row in projection['pre']:
                if row['adsh'] != fact.accession or row['tag'] != tag or row['version'] not in versions:
                    continue
                report = int(row['report'])
                suffixes = ('htm', 'html') if row['rfile'] == 'H' else ('xml',) if row['rfile'] == 'X' else ()
                verified = sorted(name for name in names if isinstance(name, str) and
                                  any(re.fullmatch(fr'R0*{report}\.{suffix}', name) for suffix in suffixes))
                location = StatementLocation(tag=tag, taxonomy_version=row['version'],
                    report=report, statement=row['stmt'], presentation_row=int(row['line']),
                    filer_label=row['plabel'], report_url=base + verified[0] if len(verified) == 1 else None)
                locations[location.model_dump_json()] = location
            if len(versions) > 1:
                status = 'ambiguous'
                diagnostics.append('Company Facts omits taxonomy year; several exact NUM taxonomy versions match. All candidates retained.')
            elif records and locations:
                status = 'matched'
                diagnostics.append('Exact concept namespace/tag, accession, annual period bucket, unit, Decimal and consolidated dimensionless context match.')
            else:
                status = 'missing'
                diagnostics.append('No matching SUB/NUM/PRE location for the exact concept, annual period bucket, unit, Decimal and consolidated dimensionless context.')
                if rejected_units:
                    diagnostics.append(f'NUM unit {sorted(rejected_units)} differs from Company Facts unit {fact.unit}; no unit conversion was inferred.')
            if any(location.report_url is None for location in locations.values()):
                diagnostics.append('Report link unavailable: no unique matching file in this filing’s SEC directory index.')
            result.append(FactPresentation(fact_id=fact.fact_id, status=status, dataset=dataset,
                numeric_records=sorted(records.values(), key=lambda item: item.taxonomy_version),
                locations=sorted(locations.values(), key=lambda item: (item.report, item.presentation_row, item.taxonomy_version)),
                diagnostics=diagnostics))
        return result
