# UI work guidance

For any work that changes the pipeline page or its outline visualization, read [docs/PIPELINE_PAGE_DESIGN.md](docs/PIPELINE_PAGE_DESIGN.md) before editing. Treat it as the durable product and interaction brief for this UI.

For every change to pipeline execution, stage contracts, validation, selection,
budgets, state, or outputs, check whether the pipeline page and selected-stage
inspection still explain the implemented behavior. Trace the affected data and
control paths through the UI, including branches, gates, accounting, and provenance.
Update the UI and its focused checks in the same change when its explanation would
otherwise become inaccurate. If no UI change is needed, state why in the handoff.
Keep [docs/PIPELINE_PAGE_DESIGN.md](docs/PIPELINE_PAGE_DESIGN.md) current when a
durable UI decision or pipeline relationship changes.

Preserve unrelated worktree changes. Run focused checks appropriate to the files changed.
