"""Offline setup and fixture-storage service; no financial pipeline stages yet."""
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter

from profitlab.contracts.base import CompanyIdentity, RunManifest, StableID
from profitlab.storage import Repository

RunSummary = RunManifest
FIXTURES = Path(__file__).parent / 'fixtures' / 'synthetic'


def validate_run_id(run_id: str) -> str:
    return TypeAdapter(StableID).validate_python(run_id)


class DemoService:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.runs_dir = data_dir / 'runs'

    def create(self, run_id: str, through: str, scenario: str = 'normal') -> RunManifest:
        validate_run_id(run_id)
        if through in ('T04', 'T05', 'T06'):
            from profitlab.sec.service import DiscoveryService
            from profitlab.settings import Settings

            settings = Settings(PROFITLAB_DATA_DIR=self.data_dir)
            run = DiscoveryService(settings).create(
                'DEMO', mode='demo', run_id=run_id, scenario=scenario)
            if through in ('T05', 'T06'):
                from profitlab.documents.service import SourceService

                sources = SourceService(settings, chunk_fixture=through == 'T06')
                sources.progress(run_id, 'download')
                sources.progress(run_id, 'parse')
            if through == 'T06':
                from profitlab.documents.chunk_service import ChunkService

                run = ChunkService(settings).progress(run_id)
            return run
        if through not in ('T01', 'T02', 'T03'):
            raise ValueError('Only --through T01, T02, T03, T04, T05 and T06 are implemented.')
        if scenario not in ('normal', 'two-years'):
            raise ValueError('Supported scenarios: normal, two-years.')
        now = datetime.now(UTC)
        years = [2022, 2023, 2024, 2025] if scenario == 'normal' else [2024, 2025]
        artifact_ids = (['ticker', 'submissions', 'fixture-metadata'] +
                        [f'annual-{year}' for year in years]) if through in ('T02', 'T03') else []
        manifest = RunManifest(
            run_id=run_id, ticker='DEMO', mode='demo', created_at=now, updated_at=now,
            company=CompanyIdentity(ticker='DEMO', name='Synthetic Demo Corporation',
                                    cik='0001234567', lookup_source='synthetic fixture',
                                    lookup_at=now),
            versions={'code': '0.1.0', 'schema': '1', 'parser': 'not implemented',
                      'prompt': 'not implemented'}, artifact_ids=artifact_ids,
            configuration={'scenario': scenario, 'through': through},
        )
        repo = Repository(self.data_dir)
        repo.create_run(manifest)
        # Keep the T01 summary filename as an indexed immutable compatibility artifact.
        repo.put(run_id, 'summary', manifest.model_dump_json(indent=2).encode())
        if through in ('T02', 'T03'):
            repo.put(run_id, 'ticker', (FIXTURES / 'ticker.json').read_bytes())
            submissions = json.loads((FIXTURES / 'submissions.json').read_bytes())
            recent = submissions['filings']['recent']
            submissions['filings']['recent'] = {
                key: [value for value, year in zip(values, [2025, 2024, 2023, 2022])
                      if year in years] for key, values in recent.items()
            }
            repo.put(run_id, 'submissions', json.dumps(submissions, indent=2).encode())
            repo.put(run_id, 'fixture-metadata', json.dumps({
                'synthetic': True, 'available_fixture_years': years,
                'financial_processing': 'not implemented',
                'unit_examples': {'currency': 'USD', 'income_scale': '1000000',
                                  'eps_scale': '1', 'example_decimal': '1.00'},
            }, indent=2).encode())
            for year in years:
                repo.put(run_id, f'annual-{year}',
                         (FIXTURES / f'annual-{year}.html').read_bytes(), 'text/html')
        if through == 'T03':
            from profitlab.trace import TraceRecorder
            from profitlab.trace.demo import record_demo

            record_demo(TraceRecorder(repo, run_id))
        return manifest

    def get(self, run_id: str) -> RunManifest:
        validate_run_id(run_id)
        if (self.runs_dir / run_id / 'manifest.json').exists():
            return Repository(self.data_dir).manifest(run_id)
        # Read-only compatibility for existing T01 summaries.
        old = json.loads((self.runs_dir / run_id / 'summary.json').read_text())
        return RunManifest(**old, updated_at=old['created_at'])

    def recent(self) -> list[RunManifest]:
        if not self.runs_dir.exists():
            return []
        runs = [self.get(path.name) for path in self.runs_dir.iterdir()
                if path.is_dir() and (path / 'summary.json').exists()]
        return sorted(runs, key=lambda run: run.created_at, reverse=True)
