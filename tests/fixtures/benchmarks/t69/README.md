# T69 retained Findings baseline

Captured 2026-10-14 before any database reset, outside the resolved application data
namespace. `manifest.json` owns provenance, bounds, hashes, model/configuration
identity, observed stage timings and measurement gaps. Gzip archives use mtime=0;
verify both compressed and decompressed SHA-256 before reuse. Treat these retained
artifacts as immutable inputs, not as generated demonstration or labeled gold.

Three recent saved SEC runs are retained: AZZ `v2-6eca22455a84`, Energy Transfer
`v2-14f354b9349e` and JPM-PK `v2-5a51d865d5e9`. The latter two offer different
entity/share-class presentation contexts; they have not been human annotated.
No saved Apple or Microsoft V2 run exists in this database. Their genuine filing
fixtures remain under `tests/fixtures/t64` and `tests/fixtures/t62` for later
acceptance; no upstream retained inputs are invented for them.

Capture used a read-only SQLite transaction against the resolved database. Each
archive contains the complete canonical document, filing URL/accession/hash,
outline, persisted upstream scores and chunks, published findings, Findings stage
snapshot/summaries/performance and saved Findings actions. The manifest records the
current allowlisted configuration; historical `run.version_components` and saved
response models remain in each artifact and can differ. Neither raw Company Facts
nor evaluation results enter these input archives. SQL-row `payload`, `canonical_json`
and `version_components` values are JSON strings, matching their stored form;
compressed diagnostic blobs were decompressed first. Existing redaction was applied
to the decoded capture, including diagnostic text. No credentials are stored.
Bounds: three runs, at most 5,000 rows per captured table, 8 MB compressed per run;
capture fails rather than truncating an admitted input. Total saved-run archives are
401,778 bytes. These historical results and timings mix policies/cache states and
are observational, not a controlled latency comparison.

`live-old-azz.json.gz` records a **real live** old Findings execution on the exact
retained AZZ canonical/outline/chunk/score/filing inputs in a temporary isolated
repository with empty caches. The application database/server was not modified or
reset. The first sandbox attempt failed to connect; the authorized network retry
completed in **26.5535 seconds** under a 120-second bound. Returned models:
`gpt-5.6-luna`, `jev-1.13.0`. Two LLM requests (initial plus whole-response repair),
four classification requests, 23,069 JEV input and 240 output tokens; four findings,
zero final rejections. Old Findings does not record native conversion/repair usage,
so LLM token totals remain explicitly unavailable. Full safe requests/answers,
initial/replacement proposals and validation diagnostics are retained where the old
service records them. The archive is a single cold observation, not a p95 or a
financial-quality acceptance result. Future T77 needs labeled identical-input
quality comparisons, more comparable cold/cache measurements and new conversion
usage capture; fewer tokens alone will not establish the speed goal.

Actual commands: `.venv/bin/python /tmp/capture_t69.py` (read-only snapshot) and
`.venv/bin/python /tmp/live_t69.py` (temporary-repository replay). These were bounded
one-off capture scripts, not an application baseline execution mode. T69 gate
validates manifest checksums and reconstructs source-owned requests directly from
the retained real inputs without any provider I/O. No reset has occurred; T71 must
stop the server and reset only the resolved `data/v2` namespace as separately scoped.
