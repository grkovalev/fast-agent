"""Explicit offline SEC transport; no gold extraction data."""
import json
from pathlib import Path

import httpx

from profitlab.sec.client import TICKERS

FIXTURES = Path(__file__).parents[1] / 'fixtures' / 'synthetic'


class FixtureLimiter:
    def wait(self, deadline):
        pass


def fixture_transport(scenario='normal', ticker='DEMO'):
    submissions = json.loads((FIXTURES / 'submissions.json').read_bytes())
    recent = submissions['filings']['recent']
    if scenario == 'two-years':
        recent = {key: values[:2] for key, values in recent.items()}
    # Recent includes a quarterly distraction, an amendment and a repeated original.
    rows = [{key: values[index] for key, values in recent.items()}
            for index in range(len(recent['form']))]
    rows += [dict(rows[0], form='10-Q', reportDate='2025-09-30',
                  accessionNumber='0001234567-25-000090'),
             dict(rows[0], form='10-K/A', filingDate='2026-03-01',
                  accessionNumber='0001234567-26-000002'), dict(rows[0])]
    history_rows = rows[2:4] if scenario != 'two-years' else []
    recent_rows = rows[:2] + rows[4:] if scenario != 'two-years' else rows
    submissions['filings']['recent'] = {
        key: [row[key] for row in recent_rows] for key in recent}
    name = 'CIK0001234567-submissions-001.json'
    submissions['filings']['files'] = [{'name': name, 'filingTo': '2024-02-15'}] if (
        history_rows) else []

    def respond(request):
        if ticker == 'TIMEOUT':
            raise httpx.ReadTimeout('Synthetic SEC timeout', request=request)
        if str(request.url) == TICKERS:
            return httpx.Response(200, json=json.loads((FIXTURES / 'ticker.json').read_bytes()))
        if request.url.path.endswith(name):
            return httpx.Response(200, json={key: [row[key] for row in history_rows]
                                           for key in recent})
        return httpx.Response(200, json=submissions)

    return httpx.MockTransport(respond)
