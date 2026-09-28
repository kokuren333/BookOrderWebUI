# Editorial planning (tasks `editorial:<chapter>`, then drafting)

The user's instructions (printed verbatim with every task; docs/user-intent.md) govern this book. This Skill gives defaults for what they leave open; it is not a higher authority. Invariants — facts, citations, provenance, safety, the build — still bind. The profile's device counts, pauses and
chapter-end items below are defaults; a device the user excluded is not planned (docs/user-intent.md, `overrides`).

Plan what each section does for the reader, where the reader rests and which content becomes a device *before*
drafting. Do not write the chapter and look for figures afterwards. One file per chapter:
`plan/editorial/<chapter-id>.yaml`. BookOrder checks every plan against the resolved profile
(`plan/profile.resolved.yaml`) and writes `reports/editorial-plan.yaml`.

```yaml
chapter_id: ch-selection
chapter_title: 勝ち筋のあとに
chapter_role: development        # introduction | problem_setting | development | counterargument | synthesis | practice
reader_before: 合格や資格を「上がり」と感じている
reader_after: 選抜のあとも評価軸が入れ替わり続けることを、自分の進路の問いに置き直せる
target_chars: 17000              # the outline budget (±10%)
lead: 大学・資格・就活を「勝ち筋のあと」の選択として読む
density_profile: [light, heavy, light, heavy, medium]   # optional; must equal the sections' expected_density
sections:
  - id: sec-selection-faculty
    heading: 学部と専門をどう使うか
    purpose: 学部別の「予後」論を、根拠の種類ごとに読み分ける
    rhetorical_role: evidence    # thesis | evidence | example | contrast | concession | synthesis | transition | application
    intended_reader_effect: 「この学部なら安心」という断定を、根拠の範囲で受け取り直す
    expected_density: heavy      # light | medium | heavy — vary them
    target_chars: 1600
    summary_points: [学部の予後は著者の観察, 採用基準は年度と職種で変わる, 高校名による上書きの主張は検証されていない]
    new_terms: []
    counterarguments: []
    example_needs: [法学部と経済学部の進路の違い]
    case_study_needs: []
    citation_needs: [{claim: 学部別の予後, source_ids: [src-0015]}]
    cross_refs: ["@ch:school"]
    visual_opportunities:
      - {information_shape: {kind: comparison, items: 3, attributes: 3}, note: 三つの学部の主張・根拠・注意}
    devices:
      - id: tbl-faculty-prognosis          # becomes the slot id; fig-/tbl- ids are also the asset ids
        type: table
        why: 三学部の主張と根拠の種類を並べると、断定の強さと根拠の弱さの落差が一度に見える
        placement: {intent: 学部ごとの主張を紹介した直後, position: middle}
        information_shape: {kind: comparison, items: 3, attributes: 3}
        basis: source
        source_ids: [src-0015, src-0062]
chapter_end:
  - {type: key_points}
  - {type: open_question}
  - {type: bridge_to_next}
waivers:                                   # only for medium/low findings, always with a reason (user-excluded defaults: plan/user-intent.yaml overrides)
  - {rule: device_count_under, reason: この章の材料には他者の発言の引用がなく、pull quote を作ると捏造になる}
```

## Device catalogue (closed)

figure, table, chart, timeline (visual intents), key_point, definition, glossary, warning, counterpoint,
checklist, pull_quote, case_study, column (sidebar), chapter_summary (chapter end only). Every device has `id`,
`type`, `why` and `placement` (`intent`, `position`: section_start | early | middle | late | section_end).

Use a device only when its condition holds and the user's instructions do not exclude it:

- key_point — the section is over 1,500 characters and has 3+ summary points.
- definition / glossary — a new, technical or coined term appears for the first time (`new_terms`, `terms`).
- pull_quote — the argument starts from a specific text or statement; `source_ids` and `quote` or `locator`.
- counterpoint — a serious objection or alternative reading exists (`counterarguments`); external ones cite it.
- case_study — abstraction has run long and the reader needs a real application; real cases cite sources
  (`basis: hypothetical` must be presented as such).
- timeline — 3+ dated events, with sources.
- table — a comparison of 3+ items on 3+ attributes.
- figure / chart — only an information shape the visual review can accept (a branching process, a hierarchy,
  5+ values …); never an illustrative arrangement, never a straight A→B→C chain.
- chapter end — by default what the profile lists (`structure.chapter_end`), in every chapter. If the user's
  instructions exclude an item (for example no chapter-end summaries), leave it out and switch the default off in
  plan/user-intent.yaml (`overrides: [chapter_end_missing]`); do not add it back as "good pedagogy".

Source ids must exist in the research registry; an unknown id is a planning error. Do not invent quotes, cases,
dates or data to fill a device.

## Pauses and rhythm

The profile's `rhythm.pause_every_chars` is checked on the plan in characters: no stretch between devices may
exceed its `max`. About `scale.chars_per_text_page` characters fill a text page; a stretch longer than
`rhythm.max_text_only_pages` pages is flagged as a text-wall risk. The typeset proof is judged later by the pacing
gate on real pages. When a stretch is too long, restructure: split the section, move a comparison into a table,
set an objection apart as a counterpoint, bring the example forward. Device counts per chapter come from
`devices.*_per_chapter`; below the minimum is a finding, not a quota — waive it with a reason when the chapter has
no such material.

## Slots

Drafting reserves each device where it is planned:

```markdown
::: {.slot #tbl-faculty-prognosis kind=table}
三学部の主張・根拠の種類・読むときの注意
:::
```

Do not explain in the prose what the slot will show. Components may be written directly with the same id
(`::: {.key-point #id}`, `.definition`, `.warning`, `.counterpoint`, `.case-study`, `.pull-quote`, `.sidebar`,
`.checklist`; chapter end: `.summary` for key_points, `.note` for open_question, `.exercise` for check questions,
`::: {#id}` for bridge_to_next). Figures and tables replace their slots in the asset phase. Proof builds show open
slots as placeholders; the final validation fails while any remains.

## When the visual review rejects a planned visual

`bookorder editorial fallback <device-id> --to table|prose|case_study|summary --reason "..."` rewrites the plan:
prose drops the device (remove its slot), the others add a device in its place that must pass its own conditions.
If that leaves a long stretch or a visual shortage, change the section structure; do not add a figure to reach a
number.
