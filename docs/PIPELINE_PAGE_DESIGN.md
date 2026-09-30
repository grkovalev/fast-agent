# Pipeline page design brief

## Intent

The pipeline page is an editorial, explorable explanation of how the report is assembled. It should feel closer to a Seeing Theory explanation than a workflow editor, Mermaid diagram, or application canvas.

The page must remain useful without interaction. Interactions add inspection and flow cues; they must not be required to understand the route.

## Outline loop

Represent the outline operation as one responsive inline-SVG loop:

`Window → Propose → Validate → Reconcile → next Window`

- Draw an unambiguous return arrow from Reconcile to Window.
- Label every connector with its payload: canonical line window, navigation proposals, accepted ranges plus rejected proposals, and continuation context.
- Each station has a number, title, clear one-line description, and a concrete description of its output.
- Preserve the loop in a vertical reading layout on narrow screens. Do not make labels illegible by simply shrinking the SVG.
- Never introduce a canvas grid, pan/zoom controls, draggable nodes, minimap, side-panel workflow editor, or graph/workflow dependency for this page.

## Station content

Station content should explain data movement, not repeat generic labels. Prefer this pattern:

- **Accepts**: representative incoming data.
- **Does**: the transformation, including the mechanism when useful.
- **Outputs**: representative outgoing data or payload shape.

For Propose specifically:

- It accepts a bounded canonical line window plus prior reconciled context.
- It sends that bounded source material and continuation metadata to the configured LLM with a navigation-only request.
- It returns navigation proposals, such as a title and source-bounded start/end line range.
- Keep the explanation wrapped and give the card enough height; never clip long SVG text.

## Interaction

- Hover and focus may highlight a station and its incoming/outgoing connectors.
- Avoid black floating tooltips for primary content.
- Avoid card-replacement or collapse behavior. Keep explanatory station content open and stable.
- A click/tap may animate only the active connector once, subtly, to communicate direction. Respect `prefers-reduced-motion`.
- Selecting Propose opens the LLM Request panel automatically. It should not require a second click on a "Prompt" label.

## LLM Request panel

On wide screens, show inspection material beside the loop rather than below it. On narrow screens, stack it beneath the loop.

The panel should show values that are sourced from the same application variables used for the actual request:

- System prompt.
- User prompt template, with safe placeholders for window-specific filing lines and continuation context.
- The returned object contract, formatted as readable JSON. Show the `sections` array and representative section fields rather than transport implementation metadata.

Do not show “Tools: none” or `json_object` response-format implementation details. Readers care about the object the model returns, not the provider transport setting.

## Layout and growth

- The pipeline workspace may use a wider content width than ordinary pages.
- On wide screens, use a main loop column and an information side rail; collapse to one column below the layout breakpoint.
- Leave room to increase station-card height and for wrapped text. Prefer growing a card over clipping or reducing type size.
- Reuse the existing muted blue/teal visual language, borders, and typography.

## Accessibility

- Station controls must be keyboard reachable and have useful accessible names.
- Connector and station state must have sufficient visual contrast.
- Keep essential explanatory text visible without hover, focus, or click.
- Disable flow animation under reduced-motion preferences.
