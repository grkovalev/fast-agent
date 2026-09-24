"""Fresh-only V2 storage acceptance."""
import sqlite3

import pytest

from profitlab.v2.storage import V2Repository


def test_clean_database_creates_the_complete_current_schema(tmp_path):
    repo = V2Repository(tmp_path)

    with repo.connect() as db:
        tables = {row['name'] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}

    assert {'runs', 'stages', 'events', 'canonical_documents', 'outline_sections',
            'chunks', 'findings', 'structured_facts', 'comparisons',
            'retrieval_benchmarks'} <= tables


def test_existing_incompatible_database_is_refused_without_modification(tmp_path):
    database = tmp_path / 'v2' / 'profitlab-v2.sqlite3'
    database.parent.mkdir()
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE legacy_runs (run_id TEXT PRIMARY KEY)')
    original = database.read_bytes()

    with pytest.raises(ValueError, match='remove .*v2.*restart'):
        V2Repository(tmp_path)

    assert database.read_bytes() == original


def test_previous_live_mode_schema_is_refused_without_reading_runs(tmp_path):
    database = tmp_path / 'v2' / 'profitlab-v2.sqlite3'
    database.parent.mkdir()
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE runs (run_id TEXT PRIMARY KEY, ticker TEXT NOT NULL, mode TEXT NOT NULL, '
                   'status TEXT NOT NULL, selected_stage TEXT NOT NULL, cancellation_requested INTEGER NOT NULL, '
                   'created_at TEXT NOT NULL, updated_at TEXT NOT NULL, summary TEXT NOT NULL)')
        db.execute('PRAGMA application_id=0x50524F46')
    original = database.read_bytes()

    with pytest.raises(ValueError, match='remove .*v2.*restart'):
        V2Repository(tmp_path)

    assert database.read_bytes() == original
