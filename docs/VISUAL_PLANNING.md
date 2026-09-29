# Visual planning

Figures are not decoration added after the text, and a book is not better because every chapter has a box-and-arrow
flow. Visuals are planned with the chapters, before drafting, from what the reader must *see*. Code:
`scripts/visual_plan.py` (phase `visual_planning`, between editorial planning and drafting); skill:
`job-template/skills/design/visual-planning.md`.

## Where visuals are decided

| Stage | Decision |
|---|---|
| publication planning | `visual_policy`: density (minimal … very_high; 「図表を多く」 raises it), preferred / avoided types, `min_distinct_types`, `max_share_per_type` |
| architecture | each chapter's `visuals` (types it needs) in the outline |
| editorial planning | visual intents as devices: figure / chart / table / timeline, or visual blocks (workflow_diagram, decision_tree, decision_table, comparison_table, infographic) with `visual_type`, `information_shape`, `basis`, `source_ids`; uploads via `asset_ref` |
| **visual planning** | `plan/visual-plan.yaml`: one entry per visual intent (seeded by BookOrder, completed by the agent) |
| asset planning / generation | realises the plan (Diagram IR, native tables, charts, uploaded or redrawn images); the existing visual review still judges each candidate |
| QA | `reports/visual-plan-qa.yaml` (phase), gate 23 (book) |

## Taxonomy

workflow, decision_tree, timeline, comparison_table, checklist_table, decision_table, hierarchy_chart, concept_map,
algorithm_card, dialogue_card, case_flow, dos_and_donts, summary_infographic, process_diagram, relationship_map,
anatomy_or_domain_schematic, data_chart, annotated_image, callout, full_page_visual. Each type names the device that
realises it (figure / table / chart / timeline / component) and the information shapes it fits.

## VisualPlan entry

```yaml
- id: fig-ward-day            # the editorial device id (also the asset id)
  chapter: ch-ward
  section: sec-ward-flow
  type: decision_tree
  purpose: 急変時にどこで誰を呼ぶか判断できる
  content: 観察項目 5 つ、分岐 3 つ、連絡先 2 つ
  reason: 分岐が重なるため文章では順序と条件を同時に保持できない
  source_requirements: [src-0003]
  generation_method: diagram_ir     # native_table, chart_code, component, uploaded_asset, redraw_from_asset, generated_image, screenshot
  importance: essential             # helpful, optional
  caption_intent: 最初の分岐（意識レベル）に注目させる
  duplication_check: 本文は判断の理由だけを述べ、手順は図に任せる
  uploaded_asset: asset-002         # when the user's upload is used
```

## QA

| Finding | Meaning |
|---|---|
| `visual_plan_missing`, `visual_field_missing`, `visual_type_unknown`, `visual_type_device_mismatch`, `visual_method_unknown` | the plan is incomplete or inconsistent with the editorial device (errors) |
| `visual_asset_unknown`, `visual_redraw_not_allowed`, `visual_reference_placed` | uploads used against the user's instructions (errors) |
| `visual_monotony` | one type exceeds the policy's share (≥ 4 visuals) |
| `visual_variety_low` | fewer distinct types than the policy expects |
| `visual_same_type_every_chapter` | every chapter with visuals uses a workflow / process diagram |
| `visual_type_avoided` | a type the policy avoids is used |
| `visual_gap` | a long chapter plans no visual although the visual need is high (list it in `text_only_chapters` with the reason if it truly needs none) |
| `visual_preferred_unused` | preferred types never considered (low) |

Medium findings block the phase until the plan changes or a waiver with a reason is recorded. In FIXED mode the plan is
seeded and reported but never blocks. The book-level QA (gate 23) repeats monotony checks on the plan, counts Diagram IR
types in the final assets (`flow_diagram_monotony`) and flags figures whose labels restate the preceding paragraphs
(`visual_duplicates_text`).

The visual density also scales the profile's visuals-per-10,000-characters health range in the editorial plan check
and in the visual review, so 「図表を多く」 is not reported back as overload. A figure the user uploaded and placed is not
rejected by usefulness heuristics (only by evidence problems).

## Tests

`tests/test_publication_architecture.py::Visuals::test_10_visual_diversity` (four workflow diagrams fail; varied types
pass), `tests/architecture_e2e.py` (three distinct types incl. an uploaded annotated image; QA passes).
