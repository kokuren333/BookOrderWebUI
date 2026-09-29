# Source role system

Not every input is a "source". A guideline that supports a recommendation, a nurse's blog that shows what the ward is
like, a sample page whose margins the user likes and an image for chapter 3 are four different things; BookOrder
keeps them apart from the upload to the bibliography. Vocabulary: `job-template/schemas/publication-architecture.json`
(`source_roles`, `source_authority`, `asset_roles`, `quick_uses`). Code: `scripts/source_roles.py`.

## Roles

| SOURCE_ROLE | Content? | Citable for facts? | Back matter | Use |
|---|---|---|---|---|
| evidence | yes | yes | 引用文献 when cited; otherwise omitted | facts, definitions, numbers, recommendations, claims |
| background | yes | no | omitted; authoring use only | understanding, viewpoints, field experience, topic discovery |
| further_reading | yes | no | 参考資料 / Further reading when assigned this role | reader-facing sources to recommend explicitly |
| structure_reference | yes | no | omitted | chapter order and explanation sequence |
| style_reference | **no** | no | omitted | voice and atmosphere; never copied |
| layout_reference | **no** | no | omitted | margins, columns, typesetting, figure placement only |
| visual_reference | **no** | no | omitted | visual design reference |
| asset | **no** | no | 図表・画像出典 when placed | placed in the publication |
| redraw_source | yes | no prose citation | 図表・画像出典 only if actually used in a figure | understood and redrawn |

## Where each input goes

```
WebUI file (role chosen or estimated)
  content role    → project.json input.sources[] {path: input/sources/…, usage}  → research/index.json → notes → references.json
  non-content     → project.json input.assets[]  {id: asset-00N, path: input/assets/…, usage} → plan/uploaded-assets.yaml
                                                   placeable files copied to source/assets/uploaded/
```

Layout, style and visual references therefore never enter the research registry, the notes, the chapter packets'
source lists or `references.json`: they cannot be cited (a `[cite:]` to them would not resolve) and the architecture QA
fails with `reference_as_content` if one is ever registered as a source.

## Per-file metadata (`usage`)

`label, role, asset_role, authority, citation_allowed, intended_usage, intended_chapter, intended_section, priority,
caption, crop_allowed, redraw_allowed, transform_allowed, use_verbatim, notes (free instruction), role_origin
(user | inferred | agent)`. Examples of free instructions: 「第2章の病棟業務の流れを説明する場所で使用」「この画像の色味と余白だけ全体
デザインの参考にする」「そのまま貼らず、情報構造だけ再作図する」「表紙には使用しない」「第4章の右ページに大きく配置したい」.

`intended_chapter` may be an outline id, a number (「第2章」, "2", "chapter 2") or a title; `source_roles.chapter_ref()`
resolves it once the outline exists.

### What enforces the instructions

| Stage | Mechanism |
|---|---|
| publication planning | the task lists every upload with its instruction; `plan/layout-references.yaml` required for layout references (≥8 composition features, `content_used: false`, `apply`) |
| architecture | an upload whose `intended_chapter` resolves to no chapter is an error |
| chapter packets / editorial planning | `uploaded_assets` for the chapter; each needs a device with `asset_ref` or `declined_assets: [{asset, reason}]` (`uploaded_asset_unplanned`) |
| visual planning | `uploaded_asset` must exist; `redraw_from_asset` only if redraw is allowed; references are never placed |
| asset planning | `plan/assets-plan.yaml uploaded_assets: [{asset, decision: placed|redrawn|reference_only|not_used, asset_id, chapter, reason}]`; placed = the figure's path is the uploaded file and it carries `uploaded_asset`; the intended chapter is respected (or `deviation_reason`); not a cover unless it is a cover candidate; "redraw, don't paste" is respected; high-priority uploads left unused need a real reason |
| visual review | a user-placed upload is not rejected by usefulness heuristics (only by evidence problems) |
| bibliography | placed/redrawn uploads are credited under 図表・画像出典 |
| QA (gate 23) | `uploaded_asset_instruction`, `reference_as_content` |

## Role resolution

`source_roles.resolve()`: the user's explicit role wins; then an explicit role passed by the research agent; then the
agent's estimate in `research/notes/<id>.yaml`; then the WebUI estimate; finally `evidence`. `background`,
`further_reading` and `structure_reference` are never cited. Background is for authoring only and never appears in the
manuscript or bibliography. Further reading is never cited and appears in the reader-facing list only when explicitly
assigned that role. The resolved table is `plan/source-roles.yaml`.

Quick-mode estimates (src/architecture.ts `inferUsage`): images → asset/inline_figure; names with layout/レイアウト/組版/
誌面 → layout reference; style/文体/トーン → style (or visual) reference; logo/cover/扉 → the matching asset role;
blog/note/体験/経験談 → background with professional_experience or anecdotal authority; ガイドライン/厚生労働省/journal/学会
→ evidence with guideline/governmental/peer_reviewed/institutional authority. Every estimate is shown as 「推定」 and is
editable.

## Authority

`primary_authoritative, guideline, governmental, peer_reviewed, institutional, textbook, expert_commentary,
professional_experience, anecdotal, unknown` with a rank (5…0). Authority is advisory — it never overrides the user's
role choice. The evidence policy (`plan/publication-architecture.yaml evidence_policy`: priority, preferred authority,
free note such as 「医学的推奨は guideline / governmental / peer_reviewed を優先」「現場の困りごとの紹介では experience
source を利用可能」) sets `minimum_rank_for_factual_claims`; the audit raises `evidence-authority` (medium) when a
paragraph with numbers or dates cites only sources of a known lower rank.

## Audit rules

- `source-role` (high): a citation of a non-citable source; a factual paragraph supported only by background sources.
- `evidence-authority` (medium): see above.
- Coverage: a supplied background source assigned to a chapter counts as `consulted`; it remains an authoring input
  and is not exposed to readers.

## URLs (same model as files)

URLs use the same usage model (`role, authority, citation_allowed, intended_chapter, intended_usage, notes,
role_origin`), UI parts (`RoleSelect`, `SourceUsageFields`) and validation (`source_roles.usage/validate_usage`).

- **WebUI**: paste many URLs at once (one per line). Each line becomes a URL card with a role estimated from the
  address (`inferUrlUsage`: `.go.jp`/`.gov`/mhlw → evidence, governmental; PubMed/DOI/J-STAGE → evidence,
  peer_reviewed; ガイドライン/guideline → guideline; 学会/`.or.jp`/`.ac.jp` → institutional; note.com/blog/体験 →
  background; layout/見本/template → layout_reference; dribbble/図解 → visual_reference; Wikipedia/まとめ → background),
  marked 「推定」. Roles offered for URLs: 根拠・引用資料 (evidence), 執筆時の参考 (background), 読者向け
 参考資料 (further_reading), 構成参考 (structure_reference), レイアウト参考 (layout_reference), 図解参考 (visual_reference). Select several cards (or
  「すべて選択」) to set role, authority, citation, chapter and usage in one step; Advanced publishing opens per-URL details.
  The WebUI never fetches pages, so page titles cannot inform the estimate; unset roles are re-estimated by the agent
  after reading (notes `source_role`), and the user's choice always wins.
- **project.json**: content URLs stay in `input.urls` (unchanged format) with `input.url_usage: {url: usage}` beside it;
  layout / visual reference URLs go to `input.assets` as `{id, kind: "url", url, usage}` and are never registered as
  sources (even a hand-edited `input.urls` entry with a reference role is skipped). A project without `url_usage`
  behaves exactly as before (every URL is evidence).
- **Agent research**: `bookorder source add --url … --role evidence|background|further_reading|structure_reference --authority …
  [--citation no] [--intended-usage …] [--intended-chapter …] [--notes …]` records the same metadata with
  `role_origin: agent` (below the user's choices, above estimates and defaults). `background` is not cited or listed;
  `further_reading` is listed without in-text citations. Layout and visual reference roles are refused for sources.
- Downstream nothing is URL-specific: plan/source-roles.yaml, packets, the `source-role` audit, gate 23 (including a
  reference URL registered as a source) and the 引用文献 / 参考資料 lists treat URL and file sources alike.
