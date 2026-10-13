# Pipeline UI work

T48–T59 are DONE; their implementation scopes are archived in
[PIPELINE_UI_COMPLETED_TASKS.md](PIPELINE_UI_COMPLETED_TASKS.md). The active
[design brief](PIPELINE_PAGE_DESIGN.md) owns durable UI decisions, and
[PROGRESS.md](PROGRESS.md) records implementation evidence.

**T60 — DONE (closed at the user's request).** Automated gates passed. Manual
visual and comprehension review was not performed, so this closure does not claim
visual acceptance. There is no active numbered UI task or later task planned.

## Shared constraints

- Read [PIPELINE_PAGE_DESIGN.md](PIPELINE_PAGE_DESIGN.md) before UI edits.
  Check any pipeline logic change against the page and selected-stage inspection.
- Preserve backend execution order, outputs, budgets, validation, and independent
  Facts/Evaluate boundaries. Type/refactor runtime payloads without changing their
  wire semantics. Surface discovered backend bugs separately instead of changing
  behavior to fit a drawing.
- Reuse actual domain classes. Shared presentation metadata may wrap domain objects
  but may not duplicate their field definitions or policy implementation.
- Keep replay entirely out of scope. Do not add recording, playback, migrations,
  a graph engine, a frontend framework, or new provider dependencies.
- Initial render must explain the route; clicking only adds inspection. Preserve
  existing selected-stage, exact-source, and sanitized-trace links.
- Keep illustrative contracts and current configuration distinct from persisted
  run data. Missing accounting is not zero; unavailable history is not current config.
- Use focused contract/integration checks. Follow the existing no-browser-automation
  task policy and provide manual UI verification steps with each UI handoff.
- Test pipeline behavior only with isolated test storage; do not start a second app
  against user run storage, where startup recovery can change active run state.
- Record results and limitations in PROGRESS.md. Outstanding required visual
  verification must remain explicit until it is completed.

## T60 — Verify the page's semantic and contract promises

**Result:** one documented acceptance pass covers the assembled page and backend coupling.

**Scope:** relevant existing task gates, focused contract/JS checks, manual checklist,
and PROGRESS.md. Depends on all stage composition tasks.

**Completed local work:** obsolete CSS/source-string assertions were consolidated
into route, contract, and behavior checks. Backend field/constraint and shared
prompt/question propagation, Decimal/range preservation, route branches and gates,
bounded overview loading, and no-provider rendering have focused coverage. The
commands and results are recorded in [PROGRESS.md](PROGRESS.md). No page-speed gain
is claimed without a measured comparison.

**Unverified follow-up:** the manual visual and comprehension pass below remains
unperformed. Record its observations and any fixes if it is undertaken later.

**Acceptance:** all eight stages are usable without interaction; inspection is consistent;
running and terminal state agree after refresh; pending, zero, incomplete, example,
current configuration, and persisted data are distinguishable. No frontend contract
field copies or misleading provider paths remain. No replay behavior or storage was added.

**Checks:** focused backend/UI suites plus shared-change checks required by TASKS.md;
`git diff --check`; manual wide/mobile/zoom, keyboard, no JS, reduced motion, long
payloads, and available run states. Ask a reviewer to identify: what each stage accepts
and produces, what gets rejected, what repeats, and where independent facts first meet
findings. Record unresolved visual or comprehension issues as remaining work.

**Closure:** [PROGRESS.md](PROGRESS.md) records the passed checks and the manual
verification gap. No visual observations are claimed. Replay requirements remain open.
