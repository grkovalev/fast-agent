# Numbered implementation tasks

Execute in order. These are bounded implementation assignments for GPT-5.6, not requests to solve the entire repository in one turn. The detailed contracts live in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md); current state lives in [PROGRESS.md](PROGRESS.md).

All commands below are **acceptance contracts to implement**, not claims that commands already exist. Each task adds a runnable slice to the same CLI and local browser interface.

## Handoff protocol for every task

1. Read repository instructions, PROGRESS.md, the relevant specification sections, and this task. Inspect actual installed code/dependency APIs before changing them.
2. Mark the task IN_PROGRESS. State the result the user will be able to inspect.
3. Implement the smallest complete slice described here. Do not implement future stages, substitute fake live results, or install unrelated frameworks.
4. Use service interfaces and Pydantic contracts; keep business logic out of CLI/web handlers. Keep mock behavior inside explicit fixture/provider adapters.
5. Add focused tests for the task's failure-prone behavior. Create `tests/task_gates/test_tNN.py` as an integration acceptance gate using the real service layer with controlled inputs. Avoid tests that merely check a function was called or compare an implementation to itself.
6. Run the gate, applicable existing tests, and `uv run ruff check .`. Run the offline demo below and start or reuse `uv run profitlab serve`.
7. Inspect the specified UI interactions when tooling is available. Otherwise provide the exact URL/click path and mark visual verification unrun. A passing HTTP test is not a visual inspection.
8. For required live checks, attempt only with available configured credentials. If absent or inaccessible, keep the check pending, explain the exact missing configuration, and finish independent offline work. Never print secrets or request they be pasted into the conversation.
9. Update PROGRESS.md with actual results, commands, demo ID, limitations, and next task. DONE means local acceptance passes; live verification has its own status.
10. End with a short handoff: what changed, command/URL, what the user should see, checks passed/pending, next task. Do not automatically start the next task.

If a task is larger than one implementation session, finish a coherent substep, mark it IN_PROGRESS, and record the exact remaining work. Do not mark a half-implemented task DONE to preserve the schedule.

All demo IDs shown assume their first execution. On later executions use a fresh suffix; existing runs must remain inspectable.

## Task summary

| Task | Visible result | Main dependency |
| --- | --- | --- |
| T01 | Open a running local app and synthetic demo page | None |
| T02 | Inspect validated run data that survives restart | T01 |
| T03 | Expand a recorded service/tool event and export its payload | T02 |
| T04 | Resolve ticker and inspect annual filing coverage | T03 |
| T05 | Click to an exact saved source table/block | T04 |
| T06 | Inspect chunk boundaries with intact tables | T05 |
| T07 | Verify Jev and LLM adapters with traced probes | T03, T06 |
| T08 | See Jev relevance probabilities and retained evidence | T07 |
| T09 | Inspect extracted values with exact table coordinates | T08 |
| T10 | Compare candidates and see coverage/selection reasons | T09 |
| T11 | Reproduce year-over-year calculations | T10 |
| T12 | Read a cited report and its actual agent conversation | T11 |
| T13 | Enter a ticker and watch the complete workflow | T12 |
| T14 | Compare chunk settings using measured retrieval results | T13 |
| T15 | Inspect successful, partial, failed, resumed runs | T14 |
| T16 | Run from a clean setup and verify a portable report export | T15 |

## T01 — Bootstrap the application and runnable inspection interface

**Goal:** establish one-command execution and a browser surface that every later task extends.

**Read:** specification sections 1–4 and project layout. Dependency: none.

**Implement:**

1. Initialize the existing repository as a uv Python project without overwriting the planning files. Create a `src/profitlab` package and `profitlab` CLI entry point. Select compatible versions, commit the lockfile when committing is requested, and record resolved direct dependencies in `docs/VERSIONS.md`.
2. Add settings, `.env.example`, and `.gitignore` covering `.env`, runtime data, caches, and exports containing traces. Keep fixture files trackable.
3. Implement `serve`, `doctor`, and `demo --through T01 --run-id ...`. Doctor checks local configuration only unless a later explicit live flag is used.
4. Build FastAPI/Jinja pages: home, recent runs, run overview, and tabs marked unavailable. Bind to `127.0.0.1:8000` by default.
5. The T01 demo uses the synthetic ticker DEMO, creates a minimal run summary, and renders a visible “Synthetic demo” badge. It stops at the implemented setup stage. No hard-coded completed financial report.
6. Add `/health` and CLI help. README gets exact launch and demo commands.

**Run:**

```sh
uv sync --locked
uv run profitlab doctor
uv run profitlab demo --through T01 --run-id demo-t01
uv run pytest tests/task_gates/test_t01.py
uv run ruff check .
uv run profitlab serve
```

**Browser verification:** open `/runs/demo-t01`. See DEMO, mode badge, setup completion, and unavailable future stages. Home links back to the run. A missing credential must not prevent starting the demo/UI.

**Acceptance gate:** fresh settings without keys start the application; health returns 200; invalid CLI input exits usefully; demo page links resolve; no network is used in demo mode.

**Do not include yet:** SEC integration, model calls, real financial facts. **Next: T02.**

## T02 — Pydantic contracts, fixtures, and persistent run storage

**Goal:** create the shared data backbone before services begin passing loosely structured dictionaries.

**Read:** sections 5, 6 persistence, and 13 fixtures. Dependency: T01.

**Implement:**

1. Define the minimum core contracts from section 5, splitting by domain. Use Decimal strings, explicit missingness, stable IDs, and schema versions. Validate source references at repository boundaries, where referenced artifacts are available.
2. Add an SQLite run/artifact index and immutable disk artifact store. Create schema initialization/versioning; a complex migration framework is unnecessary initially.
3. Write through temporary files and atomic rename. Detect attempts to overwrite a completed immutable artifact with different content.
4. Build the base DEMO source fixture: four small annual HTML reports, ticker/submissions responses, and a separate gold file with known metrics. Add a second scenario with only two reports.
5. Include all three core metrics, unit labels, fiscal dates, a GAAP/adjusted distractor, and annual/quarterly distractors. Values should be hand-calculable; document exact expected numbers. Gold answers are test-only and must never enter live extraction prompts.
6. Add a JSON artifact inspector to the run page; implement `inspect <run-id>` and demo through T02.

**Run:**

```sh
uv run profitlab demo --through T02 --run-id demo-t02
uv run profitlab inspect demo-t02
uv run pytest tests/task_gates/test_t02.py
```

**Browser verification:** open `/runs/demo-t02`, inspect the manifest and fixture artifact list, then restart the server. The run and artifacts remain accessible. Inspect a raw decimal and its unit.

**Acceptance gate:** Decimal values round-trip exactly; missing and zero remain distinct; invalid probability/date/identity contracts fail; restart preserves the run; an existing run ID cannot be silently overwritten; fixture gold answers are not loaded by production services.

**Next: T03.**

## T03 — Persistent trace recorder and trace viewer

**Goal:** make every subsequent integration observable from its first request.

**Read:** section 6 and trace UI contract. Dependency: T02.

**Implement:**

1. Introduce the TraceRecorder API, append-only JSONL events, payload artifacts, span/parent IDs, call IDs, and sequence allocation.
2. Add wrappers for deterministic service actions and future agent tools. Distinguish actor types; a demo operation is not an actual agent call.
3. Capture input, output, attempt, duration, error, and artifact links. Make safe redaction shared across logs, artifacts, exports, and UI.
4. Build `/runs/{id}/trace` with an expandable timeline and event filters. Full payload retrieval must work even when the timeline preview is short.
5. Implement a synthetic trace scenario using actual recorder calls: successful operation, cache hit, failure, retry, nested operation, and interrupted span. Label scripted conversation examples as fixtures if used; actual model conversation starts at T07/T12.
6. Export redacted trace JSON/JSONL now; complete report export comes later. Flush trace state on errors and cancellation.

**Run:**

```sh
uv run profitlab demo --through T03 --run-id demo-t03
uv run profitlab export demo-t03 --output ./exports/demo-t03
uv run pytest tests/task_gates/test_t03.py
```

**Browser verification:** open `/runs/demo-t03/trace`. Expand a failed call, inspect its arguments/error, follow its retry, and open a complete payload. Refresh the browser and confirm it remains.

**Acceptance gate:** concurrent events have unique ordered sequences; start/end IDs match; nested events preserve parentage; large output is retrievable; test credentials are absent from every persisted/exported artifact, including errors; a truncated last event does not destroy earlier history.

**Next: T04.**

## T04 — SEC ticker lookup and annual filing discovery

**Goal:** accept a ticker and show which company and reporting years will be processed.

**Read:** section 7. Dependency: T03.

**Implement:**

1. Add a typed SEC client using httpx, a shared rate limiter, declared contact header, cache metadata, timeouts, bounded observable retries, and mock transport injection.
2. Resolve ticker via the official mapping; return distinct `not_found`, `ambiguous`, `unsupported`, and `service_error` outcomes.
3. Fetch submissions and referenced older history as necessary. Build FilingRecords for up to four distinct fiscal annual periods, retaining associated amendments.
4. Deduplicate original reports by accession/report period. A 10-K/A does not consume another year slot. Do not select quarterlies.
5. Add a discovery operation to the home UI and a list of filings with year, form, filing date, report date, and original URL.
6. Add `doctor --live sec`, plus a bounded CLI stage command `discover TICKER --years 4 --mode demo|live` that creates a run ending at discovery. Document it in help.

**Run:**

```sh
uv run profitlab demo --through T04 --run-id demo-t04
uv run profitlab demo --through T04 --scenario two-years --run-id two-years-t04
uv run pytest tests/task_gates/test_t04.py
uv run profitlab doctor --live sec
```

The last command is an external check: run when configured and record actual results; local acceptance must remain possible offline.

**Browser verification:** open `/runs/demo-t04`. Verify the matched company and four years. Open `/runs/two-years-t04` and see two years, not a padded four-year claim. Enter an unknown demo ticker and see the missing-ticker message; simulated timeout must show a service failure instead.

**Acceptance gate:** historical file traversal works; amendments and quarterly reports do not displace annual periods; normalization is deterministic; timeout/403/429 cannot become not-found; all requests/retries are traced and rate-limited.

**Next: T05.**

## T05 — Download reports and build the anchored source viewer

**Goal:** the user can already verify a source quote before any model interprets it.

**Read:** sections 7–8. Dependency: T04.

**Implement:**

1. Download primary documents into the immutable source store with provenance, hash, and status. Handle partial downloads and validate content before marking cached success.
2. Parse content into SourceBlocks and TableCells while preserving captions, headers, labels, units, footnotes, and inline-XBRL references.
3. Generate stable local anchors and map original DOM IDs when present. Add quote matching with explicit whitespace normalization.
4. Build `/sources` list and the sanitized source-document route. Render a readable table and highlight requested row/column/cell IDs.
5. Show a source card with saved-source link, SEC original link, accession, filing date, heading path, and printed page label only when explicitly known.
6. Include synthetic cases with missing original anchors, merged table headers, script content, and an unrelated source block containing repeated numeric values.
7. Add a pipeline stage command `stage <run-id> download` and `stage <run-id> parse` for controlled live progression after discovery. Later stages reuse this command contract.

**Run:**

```sh
uv run profitlab demo --through T05 --run-id demo-t05
uv run pytest tests/task_gates/test_t05.py
```

**Browser verification:** open `/runs/demo-t05/sources`. Click the diluted-EPS table, confirm the anchor scrolls to it, and highlight one year cell. Check the neighboring year is not highlighted. Follow the original-link control; synthetic sources must be labeled instead of linking to an invented SEC filing.

**Acceptance gate:** anchors are stable across reparsing identical input/version; row/column spans preserve interpretation; normalized quotes match; raw source remains unchanged; scripts/event handlers cannot execute; path traversal cannot access arbitrary files; no made-up page numbers.

**Live check:** download and parse one real discovered 10-K when SEC access is available. Record whether the original anchor exists and works. Do not call an HTTP 200 alone a successful citation inspection.

**Next: T06.**

## T06 — Table-aware chunking and chunk inspector

**Goal:** make chunk size and evidence context visible and testable before adding Jev.

**Read:** section 9 chunk policy. Dependency: T05.

**Implement:**

1. Deterministic block-based chunker with configurable target/overlap, default 1,500/180 estimated tokens.
2. Preserve headings and complete financial tables. Handle oversized tables with row-group splitting and repeated headers; link all pieces to their original table/cells.
3. Save primary/overlap references, content hashes, token estimates/estimator version, and source anchors. Avoid duplicate overlap inflation in future coverage counts.
4. Enforce a conservative request-size guard accounting for metadata and question overhead; clearly distinguish estimate from Jev-reported tokens.
5. Add `/chunks` with filtering by filing, heading, and size. Show preceding/following chunks and original table links.
6. Add `stage <run-id> chunk`. No screening scores should appear yet.

**Run:**

```sh
uv run profitlab demo --through T06 --run-id demo-t06
uv run pytest tests/task_gates/test_t06.py
```

**Browser verification:** inspect a prose boundary with overlap, an intact multi-year table exceeding the target, and a very large table split by row groups. Every split piece has year/unit headers and opens the correct source.

**Acceptance gate:** source content coverage is preserved; no cross-filing chunks; headings/context stay attached; chunk hashes repeat; table numbers cannot detach from year/unit headers; oversized unsupported rows produce an explicit error; nominal target is not misrepresented as a hard table limit.

**Next: T07.**

## T07 — Jev and OpenAI-compatible provider adapters

**Goal:** prove the chosen endpoints can perform the required typed operations and capture the actual requests.

**Read:** sections 3, 6, 9, and report-provider paragraph in 11. Dependencies: T03, T06.

**Implement:**

1. A Jev client protocol with live and fake implementations. Use typed Pydantic request/response models around the documented HTTP API. Keep Jev separate from the generative Chat Completions adapter.
2. A Pydantic AI model factory using explicit OpenAIChatModel/OpenAIProvider configuration for the installed version. Model name and URL are settings, not hard-coded OpenAI defaults.
3. A compatibility probe that returns a tiny typed output and performs one harmless read-only tool call, proving both capabilities. Unsupported structured-output/tool behavior must produce a specific compatibility failure.
4. Request tracing with exact redacted messages/state/questions, complete responses, actual model ID, usage, and retries. Preserve native Pydantic message history and map observable events to the local conversation viewer.
5. Use one transport retry owner; explicitly handle Jev 429/529 and authentication/validation failures according to current docs. Track structured-output repairs separately.
6. Extend doctor with `--live jev` and `--live llm`. A live probe creates an inspectable run and prints its trace URL. Add tests with fake transports and Pydantic test/function-model facilities supported by the installed release.

**Run:**

```sh
uv run profitlab demo --through T07 --run-id demo-t07
uv run pytest tests/task_gates/test_t07.py
uv run profitlab doctor --live jev
uv run profitlab doctor --live llm
```

**Browser verification:** open `/runs/demo-t07/trace`; distinguish the fake Jev request from the fixture agent conversation. If live probes run, open their separate trace IDs and inspect one real tool call and typed response.

**Acceptance gate:** absent keys do not break demo; provider URL/model settings are honored; no silent fallback to another provider; malformed schema and unsupported features fail visibly; retry count is bounded; secrets are redacted; native message history survives serialization.

**Next: T08.**

## T08 — Jev relevance screening and coverage recovery

**Goal:** inspect exactly which document chunks Jev retained and why.

**Read:** section 9 screening policy. Dependency: T07.

**Implement:**

1. Version the five screening questions in a prompt file and send them together for each chunk. Record all responses, including low probabilities.
2. Apply configurable keep/uncertain/drop thresholds with the initial values from the specification. Display them as experimental settings.
3. Preserve statement/EPS tables through structural safeguards, logging an override instead of modifying the model's reported score.
4. Retain evidence by filing/year/metric; no global top-k cutoff. Add one bounded recovery pass for missing expected evidence using labels/neighbors, recording its lineage.
5. Implement stage caching keyed by source/chunk/question/model configuration. Track alias-model uncertainty; a cached `jev-latest` response is a recorded old result, not a new response from today's model.
6. Enhance chunk inspector with probability columns, decision, policy reason, override, trace link, and retained text totals. Implement `stage <run-id> screen`.

**Run:**

```sh
uv run profitlab demo --through T08 --run-id demo-t08
uv run pytest tests/task_gates/test_t08.py
```

**Browser verification:** compare a retained EPS table, uncertain explanation, irrelevant paragraph, and low-scored table saved by a structural override. Click a score to open the exact Jev request and answer.

**Acceptance gate:** unknown/failed answers cannot become confident drops; all uncertain chunks remain available; missing-year evidence triggers recovery; duplicated overlap does not inflate coverage; model/version changes invalidate appropriate caches; fake-provider outcomes are labeled fixture results.

**Live check:** run screening on a small real parsed filing subset, inspect relevant/irrelevant examples, and record request/usage counts. Do not claim accuracy from this spot check.

**Next: T09.**

## T09 — Candidate extraction with source validation

**Goal:** turn retained evidence into typed numbers that can be checked against a table cell.

**Read:** sections 5 and 10 extraction. Dependency: T08.

**Implement:**

1. A deliberately limited inline-XBRL extractor for the supported metrics, preserving period contexts, units, sign, scale, and visible source references. Unsupported taxonomy/transformation/context cases remain flagged.
2. A table extractor for explicit annual metric rows. Require year headers and unit context; identify column and row accurately across merged headers.
3. A Pydantic AI structured extraction fallback for retained chunks unresolved by the parsers. Supply valid block/cell IDs; demand raw value text and references. Keep its message/tool trace.
4. Validate every proposed figure against its cited source and normalized value. Separate accepted, ambiguous, and rejected extraction attempts.
5. Extract narrative evidence passages separately from numeric facts. They require quote validation too.
6. Build the candidate list, source drawer, and optional Company Facts cross-check for a small explicit concept mapping. That cross-check must not silently replace the cited filing value.
7. Implement `stage <run-id> extract`.

**Run:**

```sh
uv run profitlab demo --through T09 --run-id demo-t09
uv run pytest tests/task_gates/test_t09.py
```

**Browser verification:** click a diluted-EPS candidate, inspect raw text, Decimal value, units, fiscal period, row/year highlight, and extractor method. Inspect an intentionally invalid LLM-proposed citation and its rejection reason.

**Acceptance gate:** test negative parentheses, scale, per-share versus millions, quarterly and adjusted distractors, wrong-year columns, segment scope, hallucinated source IDs, hidden-only XBRL, and missing context. Gold numbers are never used by the extractor. Invalid candidates cannot proceed as selected facts.

**Live check:** extract at least one real income/EPS table and manually confirm three cells against the saved and original source. Record any unsupported layout; a fixture pass is not a general parser accuracy claim.

**Next: T10.**

## T10 — Candidate reconciliation and evidence coverage

**Goal:** show why a particular number was selected while preserving alternatives.

**Read:** section 10 candidate grouping/selection. Dependency: T09.

**Implement:**

1. Comparable-group keys with period, metric, unit, scope, attribution, basis, and share class. Deduplicate overlapping/repeated evidence without discarding provenance.
2. Apply explicit ordered selection rules. Emit reason codes plus short factual descriptions; record all selected/rejected/conflicting alternatives.
3. Handle repeated historical years across filings, explicit restated/split-adjusted comparatives, unexplained discrepancies, and differing reported precision.
4. Build the four-year × metric coverage matrix. Keep common-share earnings distinct from parent/consolidated alternatives.
5. Select complementary explanatory passages by year/topic, removing duplicate text while retaining source references. No need for an unconstrained model to choose a “best report.”
6. Add UI comparison of competing candidates and selection provenance. Implement `stage <run-id> reconcile`.

**Run:**

```sh
uv run profitlab demo --through T10 --run-id demo-t10
uv run profitlab demo --through T10 --scenario conflict --run-id conflict-t10
uv run pytest tests/task_gates/test_t10.py
```

**Browser verification:** open `/runs/demo-t10/candidates`, choose one metric/year, and inspect the selected value and alternatives. Open the conflict run and see an unselected cell with both competing sources; it must not quietly pick the newest or largest value.

**Acceptance gate:** annual/quarterly and common/parent/segment facts never merge; duplicate chunks do not add support; explicit restatement updates the comparable series with provenance; unexplained disagreement remains unresolved; missing metrics remain missing.

**Next: T11.**

## T11 — Deterministic annual-growth calculations

**Goal:** users can reproduce every growth number without trusting a language model.

**Read:** section 11 formulas and comparability. Dependency: T10.

**Implement:**

1. Decimal-based absolute change, eligible year-over-year percentage, and optional eligible CAGR. All inputs reference selected facts.
2. Explicit statuses for missing inputs, incompatible periods, currency/share-class mismatch, zero/negative bases, and profit/loss transitions.
3. Preserve source precision, display rounding, exact input values, and formula/version. No model performs arithmetic.
4. Build `/calculations` and a preliminary deterministic annual metrics table on the report tab, clearly marked “Data table; narrative not generated.”
5. Link every derived value to inputs and evidence. Implement `stage <run-id> calculate`.

**Run:**

```sh
uv run profitlab demo --through T11 --run-id demo-t11
uv run profitlab demo --through T11 --scenario losses --run-id losses-t11
uv run pytest tests/task_gates/test_t11.py
```

**Browser verification:** click one percentage, read its two input values and formula, and calculate it yourself. In the losses case, see transition text/absolute changes and suppressed conventional growth percentages. Verify four observations yield three annual intervals.

**Acceptance gate:** exact hand-calculated examples match; zero is not missing; negative/zero bases produce intended statuses; missing years cannot be bridged as annual comparisons; four-year CAGR uses three intervals; fiscal transition periods are flagged; report values link to the selected facts.

**Next: T12.**

## T12 — Report-writing agent, actual conversation, and citations

**Goal:** generate the readable report while preserving a verifiable trail for every figure and explanation.

**Read:** sections 4 evidence drawer, 6 tracing, and 11 report writer. Dependency: T11.

**Implement:**

1. Pydantic AI report agent with versioned instructions, typed dependencies, bounded read-only evidence tools, and Report output schema.
2. Supply selected figures/calculations and a compact index. The agent may inspect saved evidence; tool implementations enforce run ownership and valid IDs.
3. Build narrative quantitative placeholders/references resolved by application code. Render the financial table deterministically; do not accept model-generated table numbers.
4. Validate references, numeric placeholders, quotes, coverage, and unavailable calculations. Add bounded repair attempts with recorded feedback. On persistent failure produce a clearly marked data-only partial report.
5. Persist the complete observable conversation incrementally, including actual tool schemas, arguments/results, validation retries, and final typed output. Keep each extraction/writer agent run separate in the UI.
6. Add linked sentence citations, source drawer, and explicit management-attribution labels. Implement `stage <run-id> write` and `validate` plus the initial `verify <run-id>` command.

**Run:**

```sh
uv run profitlab demo --through T12 --run-id demo-t12
uv run profitlab verify demo-t12
uv run pytest tests/task_gates/test_t12.py
```

**Browser verification:** open `/runs/demo-t12/report`. Inspect one EPS value, one growth calculation, and one explanatory quote. Then open Trace → Conversation, expand a real fixture-driven tool call through the agent framework, and inspect an output-validation retry. The badge must make clear that the provider is fake.

**Acceptance gate:** fabricated evidence IDs and numeric assertions fail; another run's IDs cannot be read; source quote mismatch triggers repair/failure; incomplete coverage is disclosed; the final table uses calculation artifacts; interrupted agent runs keep partial history; a fallback report is not marked a successful model narrative.

**Live check:** generate a report with the configured model and record its real tool activity. Do not fabricate a tool call if that live model used the supplied evidence without invoking one.

**Next: T13.**

## T13 — Complete ticker-to-report workflow and run controls

**Goal:** the original user flow works from a single ticker entry with live progress.

**Read:** sections 3–4 and 12. Dependency: T12.

**Implement:**

1. Wire the persisted stage state machine across the existing services. Implement `analyze TICKER --years 4 --mode live|demo`, `resume`, and `cancel`.
2. Home form launches the same pipeline used by CLI. Show resolved company, filing coverage, stage counts, elapsed time, errors, and report link.
3. Use an application-managed background async job for the initial local single-process server. Persist status before dispatch. Detect interrupted jobs on restart and offer resume.
4. Add per-stage input/output hashes and invalidation. Cached stages are linked to their actual source run/request; no fake new tool events.
5. Poll incremental progress without losing trace state. Enforce one active live run initially and bounded provider concurrency.
6. Add cancellation and stage-budget enforcement. Partial/failed runs must open their existing sources/candidates/trace.

**Run:**

```sh
uv run profitlab demo --through T13 --run-id demo-t13
uv run profitlab analyze DEMO --years 4 --mode demo
uv run pytest tests/task_gates/test_t13.py
```

**Browser verification:** on `/`, select demo mode and enter DEMO. Watch progress to report. Start the slow demo scenario, cancel it, and inspect its trace. Restart the server with an interrupted fixture run, resume it, and confirm completed unchanged stages are reused.

**Acceptance gate:** UI/CLI share pipeline behavior; refresh never loses state; changing prompt/chunks invalidates appropriate stages; duplicate starts are controlled; cancellation is not success; insufficient years produce a partial-coverage report; unavailable credentials fail before paid stages rather than silently switching to demo.

**Live check:** run one supported real ticker through all configured services. Record SEC/model access limitations separately; do not mark this checked if only stage mocks ran.

**Next: T14.**

## T14 — Measure chunk size and relevance quality

**Goal:** replace the provisional chunk-size recommendation with evidence, or document that it remains provisional.

**Read:** section 9 benchmark and section 13 evaluation design. Dependency: T13.

**Implement:**

1. A versioned evaluation dataset referencing immutable source block/cell IDs and human-entered gold labels. Make a dev/held-out split across filings/companies; do not tune thresholds on the held-out set.
2. A comparison runner for 750/1,500/3,000 target tokens, approximately 12% prose overlap, same table policy, same questions, and same pinned/recorded model identity.
3. Measure Jev-only recall, post-recovery recall, required fact coverage, irrelevant retained volume, downstream input volume, call counts, latency, usage, and exact final numeric accuracy against labeled facts. Explain each denominator and deduplicate source overlap.
4. Add an evaluation UI with missed-evidence links, settings, source labels, per-configuration totals, and whether provider calls were live/fake/replayed.
5. Initial selection target: at least 95% relevant-block recall and 100% coverage of the required labeled facts on the small held-out benchmark, with no wrong selected metric/year values. These are project acceptance targets, not a promise of population accuracy. Report sample counts.
6. Choose the smallest tested configuration that meets the targets; use downstream retained volume/cost as a tiebreaker. If none passes, report misses and keep settings explicitly provisional. If live credentials are unavailable, implement/verify the harness but leave the chunk-size conclusion pending.

**Run:**

```sh
uv run profitlab demo --through T14 --run-id demo-t14
uv run profitlab evaluate chunks --dataset evaluation/dev.json --mode demo
uv run pytest tests/task_gates/test_t14.py
```

Create the named dataset file or adjust/document its concrete path during this task. A live evaluation uses `--mode live` explicitly.

**Browser verification:** open the printed evaluation URL, compare the three settings, click a missed block, and inspect its source and Jev judgment. Confirm fixture metrics are labeled synthetic and cannot be mistaken for a real Jev benchmark.

**Acceptance gate:** hand-constructed evaluation counts match expected recall/coverage; gold labels are not exposed to screening; train/held-out identities do not overlap; duplicate chunk coverage is not double-counted; model/config differences are recorded; no benchmark result is invented when calls did not run.

**Next: T15.**

## T15 — End-to-end verification and failure/recovery cases

**Goal:** prove the application is honest and inspectable when evidence or services fail.

**Read:** sections 12–13. Dependency: T14.

**Implement:**

1. Expand `verify <run-id>` to check schema/reference integrity, artifact hashes, citation targets, quote matches, selected facts, reproducible calculations, trace closure, and redaction. Clearly label these as mechanical checks.
2. Complete synthetic scenarios for missing ticker, two years, losses, conflicts, unsupported filing, ambiguous share class, restatement, changed units, source corruption, provider failure, invalid extraction, and interrupted runs.
3. Add representative end-to-end tests using the real pipeline plus controlled external transports. Verify outputs against independent fixture expectations.
4. Add browser checks or a reproducible manual script for the ticker form, source drawer, table highlighting, candidate alternatives, conversation expansion, and refresh/resume.
5. Verify prompt-injection-like filing text cannot activate extra tools or override source-only reporting. Verify source/model content is escaped in the UI.
6. Fix discovered defects within scope and record remaining unsupported layouts or provider limitations.

**Run:**

```sh
uv run profitlab demo --through T15 --run-id demo-t15
uv run profitlab verify demo-t15
uv run pytest
uv run ruff check .
```

**Browser verification:** inspect one complete report, one conflicting/partial report, and one provider-failed run. All retain their trace and evidence; none shows a misleading success status. Clicking every main-table value reaches a valid source or explicit missingness state.

**Acceptance gate:** the failure matrix passes; secret scanning of test exports finds no injected credentials; source hashes and quote validation detect deliberate corruption; resume does not duplicate selected facts; failed external stages cannot produce uncited confident claims.

**Live verification:** run at least one complete supported ticker and one with a different layout/fiscal calendar when access permits. Manually verify at least three figures, one growth calculation, and one explanation in each completed live report. Capture results in PROGRESS.md without overstating the small sample.

**Next: T16.**

## T16 — Final handoff, portable exports, and reproducibility

**Goal:** the user can start the app and verify a report independently, including after the original process stops.

**Read:** section 13 final definition of done. Dependency: T15.

**Implement:**

1. Finish `export` as a portable bundle: report HTML/Markdown/JSON, sanitized cited source pages, evidence/candidate/calculation artifacts, redacted trace and model conversations, manifest/version data. Exclude credentials and unrelated runs.
2. Rewrite local links for exported relative paths. Provide an offline static source/report viewer or a documented local serving command; do not depend on the original live server or a CDN. SEC-original links remain external supplements.
3. Polish the report/source/trace navigation only as needed for verification: clear labels, readable financial tables, collapsed technical detail, visible partial/conflict status, and accessible controls.
4. Write `docs/USER_GUIDE.md` with setup, credentials by environment-variable name, demo/live/replay modes, error meanings, and a two-minute verification walkthrough.
5. Update README with exact commands and screenshot(s) from actual implementation if browser tooling is available. Do not use mock images presented as real UI screenshots.
6. Run a clean-environment install using the lockfile, offline demo, checks, export, restart/replay, and a final live check when configured. Record precise verified versions and remaining live gaps.
7. Update PROGRESS.md to final status. If live evaluation/integration remains pending, state it prominently; local completion does not erase those gaps.

**Run:**

```sh
uv sync --locked
uv run profitlab demo --through T16 --run-id demo-final
uv run profitlab verify demo-final
uv run profitlab export demo-final --output ./exports/demo-final
uv run pytest
uv run ruff check .
uv run profitlab serve
```

**Browser verification:** open the report and verify an EPS value, an annual change, and an explanatory quote in under two minutes. Stop the application and open/serve the exported bundle; repeat the same checks. Confirm trace payloads are still readable and no links require the former run server.

**Acceptance gate:** fresh locked installation works; demo requires no network; portable citations resolve; export contains complete redacted trace payloads; report numbers reproduce; final documentation lists actual successful commands and explicitly unverified live checks.

**Final handoff:** provide startup command, demo URL, live command, export location, measured chunk setting/status, and the shortest click path to verify an answer. There is no next implementation task unless a recorded blocker or new user request remains.
