# Visual planning (plan/visual-plan.yaml)

Visuals are planned with the chapters, before drafting — not added afterwards as decoration, and never to reach a
count. For each visual intent in plan/editorial/*.yaml BookOrder seeds an entry; complete it:

| field | meaning |
|---|---|
| type | workflow, decision_tree, timeline, comparison_table, checklist_table, decision_table, hierarchy_chart, concept_map, algorithm_card, dialogue_card, case_flow, dos_and_donts, summary_infographic, process_diagram, relationship_map, anatomy_or_domain_schematic, data_chart, annotated_image, callout, full_page_visual |
| purpose | what the reader can do after seeing it |
| content | exactly what is shown (steps, branches, rows × columns, events, axes) |
| reason | why seeing it beats reading it *here* |
| source_requirements | source ids, or derived_from_text |
| generation_method | diagram_ir, native_table, chart_code, component, uploaded_asset, redraw_from_asset, generated_image, screenshot |
| importance | essential, helpful, optional |
| caption_intent | what the caption must make the reader notice |
| duplication_check | how it adds to the prose instead of restating it |
| uploaded_asset | the upload it uses, when the user assigned one |

Choose the type from the information's shape, not from habit: a decision is a decision_tree or decision_table; a
comparison is a comparison_table or dos_and_donts; a course over time is a timeline or case_flow; a procedure an
operator follows is an algorithm_card; talk is a dialogue_card; quantities are a data_chart. A box-and-arrow flow is
right only for a real process with a meaningful order or branches.

The QA (reports/visual-plan-qa.yaml) flags: one type above the policy's share, too few distinct types, the same flow
type in every chapter, avoided types, chapters that need a visual and have none, and uploads used against their
instructions (a layout/visual reference placed, redraw not allowed). Fix the plan, change the editorial device, or
record a waiver with the reason. A chapter that truly needs no visual goes to `text_only_chapters` with its reason.
