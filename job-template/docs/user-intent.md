# User intent

The WebUI's *Additional user instructions* are the user's instruction for **this** book. They are saved verbatim in
`project.json` (`user_instructions`) and `TASK.md`, and BookOrder prints them verbatim in every research, writing,
editing, review and design task (`User intent (verbatim …)` in NEXT TASKS, `user_intent` in `bookorder goal --json`
and in each chapter packet). Read them every time; do not rely on having read TASK.md earlier.

> Do not improve the book against the user's explicit intent.

## Precedence

1. **Invariants** — factual accuracy, citation integrity, source provenance, safety, build validity, the requested
   outputs, and the physical publication settings explicitly selected in the WebUI. Never waived.
2. **Explicit user choices** — structured settings for the fields they represent (scale, outputs, page size,
   layout, selected design values); the verbatim instructions for the editorial and semantic choices they state
   (voice, tone, distance to the reader, difficulty, explanation density, topics in or out, emphasis, cases,
   structure, what becomes a figure or table, chapter apparatus such as summaries, exercises or counterarguments).
3. **Derived decisions** — resolved profile, Book Bible, outline, editorial plans. They must follow 1 and 2.
4. **BookOrder defaults and Skill heuristics** — genre/tier device counts, chapter-end apparatus, balanced framing,
   teaching scaffolding, pacing devices. They fill only what the user left unspecified.

Skills describe good defaults, not a higher authority. "More balanced", "more educational" or "more standard" is
not an improvement when the user asked for something else.

Structured vs free text is not a contest of the whole field: WebUI A5 + "make it A4" → A5 stays (structured field)
and the conflict is reported; Medical preset + "no routine chapter-end summaries" → no summaries (the preset's
chapter-end apparatus is a default, the user's words are explicit).

## plan/user-intent.yaml (written in the architecture task)

BookOrder seeds the file; you interpret. The verbatim text always wins over this interpretation.

```yaml
verbatim_source: "project.json user_instructions (also TASK.md); authoritative over everything below"
verbatim: "..."                     # copied by BookOrder for reference
directives:
  - id: intent-001
    source_quote: "教科書的にせず"     # exact words from the user's text (checked)
    interpretation: "Avoid default textbook scaffolding: no learning objectives, boxed definitions only where needed."
    applies_to: [architecture, editorial_planning, drafting, prose_editing]
  - id: intent-002
    source_quote: "各章末にまとめを付けない"
    interpretation: "No routine chapter-end summary or key-point box."
    applies_to: [architecture, editorial_planning, drafting, prose_editing, layout]
    overrides: [chapter_end_missing]   # pipeline defaults this directive switches off
conflicts:
  - instruction: "A4にする"          # the user's words
    stage: architecture
    category: structured_setting      # invariant | structured_setting | source_evidence | technical
    resolution: "Kept A5 selected in the WebUI."
    reason: "Page size is a structured WebUI setting."
```

`overrides` accepts only pipeline defaults, and only with a quote that really occurs in the user's text:
`chapter_end_missing`, `further_reading_missing`, `chapter_lead_missing`, `key_point_needed`, `definition_needed`,
`device_count_under`, `device_count_over`, `density_monotonous`, `abstract_run`, `section_too_long`,
`section_too_short`, `pause_interval_exceeded`, `pause_interval_long`, `text_wall_risk`, `visual_shortage`,
`visual_overload`, `nonprose_share_low`, `visual_opportunity_unused`, and `layout_pacing` (measured text walls,
gate 17). An overridden finding stays visible in the reports, marked as waived by user intent, but no longer
blocks. Invariant checks (sources, citations, IDs, contracts, the build) cannot be overridden: record a conflict.

Also write a `user_intent` section in `plan/book-bible.yaml`:

```yaml
user_intent:
  governs: ["一人称の評論として書く (intent-001)", "章末まとめなし (intent-002)"]
  defaults_used: ["numeric citations", "profile section length range"]   # [] if none
```

## Intent checks before `bookorder done`

Content-changing tasks reread the instructions and check their result before reporting done. With user
instructions, BookOrder also requires a short `intent_check` (a sentence or two: how this work follows the
instructions, or which conflict was recorded) in the files these tasks already write:
`plan/summaries/<chapter>.yaml`, `plan/integration-review.yaml`, `plan/audit/book.yaml`, `plan/prose-audit.yaml`,
`plan/prose-editing.yaml`, `plan/design-decisions.yaml`, and a `## User intent` section in
`reports/layout-review.md` (publication QA). Completion gate 22 checks all of them.

Reviews (audits, prose audit) never report a requested choice as a defect; a departure from the user's intent is an
issue with `type: user-intent`.

## Conflicts

Never drop an instruction silently. When you cannot follow it — it conflicts with an invariant or a structured
setting, the sources do not support it, or it is technically impossible — add a conflict with the user's words, the
stage, the category, what you did instead and why. BookOrder lists every conflict in `reports/editorial-review.md`
(`## User intent`) and `execution-summary.json` (`user_intent`); include them in your final report to the user.
