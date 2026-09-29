# Figures, tables, equations and images

## Planning (task `plan-assets`)

Visual intents come from the editorial plan (`plan/editorial/*.yaml`): every figure, chart, timeline and table
device there becomes a candidate with the same id (or `device: <id>`), and this plan decides its rows, nodes,
renderer, geometry and caption. A candidate the review rejects goes back to the editorial plan
(`bookorder editorial fallback <id> --to table|prose|case_study|summary --reason ...`).

Visuals the user's instructions ask for are planned first; things they say not to illustrate are not
illustrated. Plan assets after substantive text exists. Every asset is a *candidate* that must say what the reader gains;
BookOrder reviews each one (reports/visual-review.yaml) and only `accepted` candidates are generated.
Route by the shape of the information, not by habit:

| information_shape.kind | representation |
|---|---|
| comparison (3+ items × 3+ attributes) | table (2 items: a sentence or list) |
| quantity (5+ values) | chart |
| chronology (3+ dated events) | timeline diagram |
| hierarchy (2+ levels) | tree diagram |
| process with branch / merge / cycle | diagram (a straight A→B→C chain is a numbered list) |
| causal (confounding, mediation) | DAG, only with sources or data |
| formula | equation |
| abstract (chapter opener) | generative image, only if the profile allows it |

Never add visuals to reach a density target: `devices.visuals_per_10k` in the resolved profile is a health check,
and a shortfall means revisiting the sections, not drawing more. Captions must not apologise for the figure
(「実証的モデルではない」「編集部が整理した概念図」): if it is not grounded, drop it.

`plan/assets-plan.yaml`:

```yaml
rationale: "..."
assets:
  - id: fig-feedback-loop        # fig- for diagram/chart/image/screenshot, tbl- for tables, eq- for equations
    chapter: ch-learning
    section: sec-learning-loop
    placement: "after the paragraph introducing reward"
    purpose: "what the reader gains"
    improvement_claim:           # required: why this beats prose
      kinds: [reveal_structure]  # reduce_working_memory | reveal_structure | show_quantity_shape | anchor_abstraction | orient_reader
      statement: "読者は三つの経路が一か所で合流することを一目で掴める"
    information_shape: {kind: process, merging: true, steps: 5}   # see the table above
    factual_basis: source        # data | source | derived_from_text | illustrative (diagram/chart/table need one)
    source_ids: ["{{src:src-0012}}"]
    duplicate_group: loop-a      # optional: candidates meant to share one composition
    decision: pending            # optional: pending (keep, do not generate) or rejected (withdraw with rejection_reasons)
    type: diagram                # diagram | chart | table | equation | image | screenshot | cover
    source: source/assets/diagrams/feedback-loop.yaml   # diagram: Diagram IR
    path: source/assets/images/x.png                    # chart / image / screenshot / cover
    data: source/assets/data/x.csv                      # chart
    subject: "..."                                       # image: provider-neutral pictorial subject
    caption: "..."
    provenance: "authored from src-0012"
    style: technical
    geometry: {placement: column, width_mm: 90, aspect_ratio: "16:9"}   # printed size; optional (default: column)
```

## Printed size (every figure)

Figures are drawn at the size they are printed; the book never shrinks them. `geometry.placement` is one of
`column` (text width, default), `full-width` (into both margins), `margin`, `full-page`, `spread`; `width_mm`,
`height_mm` and `aspect_ratio` refine it. Text, lines and padding come from the book's figure tokens in points
(`.build/figure-tokens.json`: `min_label_pt`, `preferred_label_pt`, `axis_label_pt`, `tick_label_pt`,
`annotation_pt`, `legend_pt`, `stroke_width_pt`, `node_padding_mm`). Nothing inside a figure may print below
`min_label_pt`. Every build measures this (reports/figure-check.json) and the audit reports violations.

Include every `expected_assets` entry from outline.yaml.

## Review (reports/visual-review.yaml)

Rejected outright: no improvement claim or reader-gain sentence; visuals only for density or orientation;
disclaimer captions; illustrative structure without sources; causal diagrams without evidence; concept maps with
fewer than 3 nodes / 3 edges, unlabelled edges, no branch/merge/cycle/hierarchy, or a claim other than
`reveal_structure`; linear chains; two-item comparisons drawn as diagrams; the same type and claim twice in a
chapter; the same composition repeated across the book. Book-level monotony (one type in 4 consecutive
chapters, one template 3+ times, one identical visual per chapter) is raised as a plan finding. Rejected
candidates stay in the report with their reasons; remove them from the text. Pending candidates are kept but
not generated and must not be referenced in the text yet.

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
- Charts: keep the data file and the script. Draw them with `scripts/chartkit.py` (matplotlib), which sizes the
  figure from the plan's geometry, applies the figure tokens and refuses text below the minimum:
  `fig, ax = chartkit.figure("fig-id")` … `chartkit.save(fig, "source/assets/figures/name.svg", "fig-id")`.
  Save SVG (text stays measurable); a PNG needs the `.render.json` record chartkit writes beside it.
  Never enlarge a chart canvas and let the book scale it down; hand-made SVG uses points as user units and a
  physical `width`/`height` (chartkit.width_pt gives the printed width).
- Generated images: use `type: image` only for an accepted abstract/pictorial intent, with `role`,
  `subject`, `factuality`, `geometry`, `path: source/assets/images/<id>.png`, and a clear reader benefit.
  BookOrder writes `source/assets/generated/<id>.request.json` and `<id>.json`, then checks the PNG at
  its final print size. Text belongs in the renderer, not the image. The default provider is
  `pending_provider`; a required asset blocks completion until a provider is configured or the plan
  is revised. `project.image_generation.provider: fake` is for offline integration tests only.

Refer to assets with `@fig:`, `@tbl:`, `@eq:` so numbering stays correct after reordering.

## Visual plan first

Asset planning realises plan/visual-plan.yaml (skills/design/visual-planning.md): the type, purpose, content, reason,
method and caption intent were decided before drafting. Keep the visual grammar varied where the content varies —
decision trees, comparison and decision tables, timelines, case flows, algorithm cards, annotated images — and do not
turn everything into box-and-arrow flows. Uploaded images and diagrams follow the user's per-file instructions
(plan/uploaded-assets.yaml): record `uploaded_assets` decisions in plan/assets-plan.yaml; a placed upload is a
`screenshot`-type figure with `path: source/assets/uploaded/<file>` and `uploaded_asset: asset-00N`; redraw only when
redraw is allowed and credit the source. Layout, style and visual references are never placed.
