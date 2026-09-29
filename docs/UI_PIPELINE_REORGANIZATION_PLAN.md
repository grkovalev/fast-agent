# Pipeline UI reorganization plan

## Goal

Make the default Pipeline page a spacious, icon-led process map, rather than a
linear stage rail combined with the selected stage's detailed inspector.

## Current visual contract — T39 and later

This section supersedes the earlier two-horizontal-lane diagram and is the
single layout contract for subsequent card work. The overview is a vertical,
top-to-bottom reading path:

```text
Source
  ↓
Outline
  ↓
Sections
  ↓
Chunks
  ↓
Evidence
  ↓
Findings
  ↓
Evaluate ← only merge point
  ↑
Facts
```

`Facts` is physically below `Evaluate`; its connector points upward into
`Evaluate`. This communicates an independent comparison input without implying
that Facts begins concurrently with Findings: the current execution gate still
seals findings before Facts begins. No other card is a merge point.

Every overview card reserves the same stable anatomy: stage icon/name, visual
process-summary region, short plain-language-description region, prompt-control
region, and persisted text status/progress/duration. T39 deliberately fills the
three content regions with obvious placeholders only. It does not surface
service internals, prompts, provider traces, or new run data. T40–T47 replace
one card's placeholders at a time.

At narrow widths this remains the same single directional order. Cards span the
available width, connectors occupy their own space between cards, and every
whole-card stage link remains keyboard reachable with visible focus. The
upward Facts-to-Evaluate connector remains explicit; no connector may overlap a
card or obscure its link.

## Card replacement sequence

T39 established the shared card frame. T40 completed the Source card with its
persisted SEC request → visible-HTML conversion → canonical-line storage diagram.
Each following task replaces placeholders on exactly one card, retains the shared
desktop card size and responsive behavior, and does not change pipeline execution.

| Task | Card | Bounded overview content |
| --- | --- | --- |
| T41 | Outline | Canonical-line windows → generated navigation topics → validated source ranges. |
| T42 | Sections | Validated outline descriptors → Jev relevance scoring → deterministic selected/uncertain sections. |
| T43 | Chunks | Selected sections → bounded source-range chunks with context overlap → inspectable chunk set. |
| T44 | Evidence | Selected chunks → Jev detail scoring → diverse retained evidence. |
| T45 | Findings | Retained evidence → quote validation → published quote-backed findings. |
| T46 | Facts | Sealed findings → independent SEC Company Facts request → normalized annual facts. |
| T47 | Evaluate | Sealed findings plus independent facts → exact comparison → coverage and match states. |

The T41 card must distinguish generated navigation metadata from exact canonical
source text and ranges. It must not show raw prompts, provider traces, or unbounded
outline records on the overview; those remain in the existing stage detail.

## Session 1 — architecture map and navigation

**Scope:** `v2_workspace.html`, its route/view model as needed, and focused
route tests.

1. Make the Pipeline route's default page the overview map.
2. Replace the left stage rail on that page with eight small linked stage
   cards: icon, stage label, status indicator, and a one- or two-word purpose.
3. Render the filing stages as one horizontal lane; render `Facts` as an
   independent lower lane; use connectors which join Findings and Facts at
   Evaluate.
4. Keep every card keyboard-accessible and linked to its existing selected
   stage URL (`?stage=<name>`).
5. Preserve the detailed per-stage content at those selected-stage URLs, with
   a clear “Back to pipeline” link. Do not move stage output into the map.

**Not in scope:** changing pipeline execution, stage contracts, or any
provider/data behavior.

**Done when:** a user opening Pipeline sees only the architecture summary and
can enter all eight existing stage pages; no stage-specific tables, findings,
or diagnostics appear on the overview.

## Session 2 — visual system and responsive behavior

**Scope:** `style.css`, small markup refinements, visual/accessibility checks.

1. Establish consistent icons for the eight stages and compact status symbols:
   complete, running, queued, partial, failed, and cancelled.
2. Style connectors as directional paths with an unmistakable convergence into
   Evaluate; visualise blocked/dependent work without suggesting data is shared
   between the two lanes before Evaluate.
3. On narrow screens, stack the filing lane, SEC-data lane, and Evaluate merge
   in reading order while preserving visible direction and links.
4. Add non-colour status text/ARIA labels and visible keyboard focus states.
5. Keep the architecture map terse: no trace links or long input/output copy;
   reserve each card's small secondary line for the live progress and duration
   added in Session 3.

**Done when:** the map is readable at desktop and mobile widths, conveys the
two lanes without a legend, and is usable with keyboard navigation.

## Session 3 — live pipeline progress

**Scope:** architecture-map markup/data attributes, `v2-progress.js`, and
state/event route tests as needed.

1. Reuse the existing SSE feed with its polling fallback to update the map
   without a page refresh.
2. Show a compact overall progress indicator in the map header: completed
   stages out of eight, current stage, and run status.
3. Update each card's status icon and label live. Mark the active card as the
   current location in the pipeline without relying on colour alone.
4. Display a small duration beneath every terminal stage. For the active
   stage, show a live elapsed clock from its persisted timing fields; show
   queued/backoff time only where it is applicable, without adding verbose
   diagnostic copy.
5. Where a stage reports bounded work, show its compact item progress (for
   example `31 / 43`) on the active card. Do not invent a percentage for stages
   whose total work is unknown.
6. Stop live timers and fallback polling when the run reaches a terminal
   state, while preserving the final persisted durations after refresh.

**Done when:** a running map makes it clear which stage is active, how far the
run and any measurable active stage have progressed, and how long each
completed stage took. The same page remains accurate after a refresh, SSE
disconnect, cancellation, failure, or resume.

## Session 4 — stage-entry polish and regression coverage

**Scope:** selected-stage header/navigation, tests, and manual QA.

1. Give every selected-stage page a compact stage header with its icon, status,
   and “Back to pipeline” navigation, so entering a stage feels deliberate.
2. Confirm existing detailed content remains intact: source links, traces,
   findings, Company Facts provenance, and evaluation cards.
3. Add/update route and template tests for overview-versus-stage behavior and
   the Facts/Findings-to-Evaluate relationship.
4. Run the relevant test suite and manually inspect completed, running, and
   failed/partial pipeline states.

**Done when:** the map and all stage entry points work without losing current
V2 inspection capabilities or misrepresenting the dependency model.

## Deferred

- Interactive pan/zoom, animated execution, live graph layout, and loops.
- Any change that allows Facts to run concurrently with Findings.
- New pipeline stages, data models, or execution semantics.
