# Figures, tables, equations and images

## Planning (task `plan-assets`)

Plan assets after substantive text exists, where a non-prose representation materially improves understanding:
relationships → Diagram IR, comparisons of 3–6 items → table, calculations → equation, numeric trends → chart,
chronology → timeline. Never add decorative visuals to fill pages. Respect the figure policy in project.json;
generated images only when enabled and when a diagram, table or equation would not communicate better.

`plan/assets-plan.yaml`:

```yaml
rationale: "..."
assets:
  - id: fig-feedback-loop        # fig- for diagram/chart/image/screenshot, tbl- for tables, eq- for equations
    chapter: ch-learning
    section: sec-learning-loop
    placement: "after the paragraph introducing reward"
    purpose: "what the reader gains"
    type: diagram                # diagram | chart | table | equation | image | screenshot | cover
    source: source/assets/diagrams/feedback-loop.yaml   # diagram: Diagram IR
    path: source/assets/images/x.png                    # chart / image / screenshot / cover
    data: source/assets/data/x.csv                      # chart
    prompt: "..."                                        # image
    caption: "..."
    provenance: "authored from src-0012"
    style: technical
```

Include every `expected_assets` entry from outline.yaml.

## Generation (tasks `asset:<id>`)

- Diagram IR (renderer-independent; BookOrder renders SVG and PNG fallbacks with the book's tokens):

  ```yaml
  type: flow        # flow | concept-map | hierarchy | timeline | comparison | cycle | process | network | matrix
  title: "..."
  nodes: [{id: action, label: "Action"}, {id: reward, label: "Reward"}]
  edges: [{from: action, to: reward, label: "optional"}]
  ```

  Place `![Caption](source/assets/figures/<name>.svg){#fig-id}` in the planned section.
- Tables: a pipe table followed by `Table: Caption {#tbl-id}`.
- Equations: `::: {.equation #eq-id}` / `$$ LaTeX $$` / `:::` — numbered automatically; inline math `$x$`.
  Never rasterize normal equations.
- Charts: keep the data file and the script or tool used; export SVG where possible.
- Generated images: save under `source/assets/images/` and record `source/assets/generated/<id>.json`
  (prompt, generator, created_at, purpose, provenance). Match the book's visual direction. If no image tool is
  available, change the plan to a diagram or table instead of leaving a gap.

Refer to assets with `@fig:`, `@tbl:`, `@eq:` so numbering stays correct after reordering.
