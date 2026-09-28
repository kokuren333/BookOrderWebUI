# User intent in BookOrder

The WebUI field **Additional user instructions — 本全体への優先指示** is the user's instruction for one book. It is
not a suggestion appended to TASK.md: it is carried verbatim into every phase and outranks BookOrder's own defaults.
Why this was needed: [USER_INTENT_AUDIT.md](USER_INTENT_AUDIT.md). The agent-facing specification shipped in every
job is [`job-template/docs/user-intent.md`](../job-template/docs/user-intent.md).

> **Do not improve the book against the user's explicit intent.**
> ユーザーの明示的な意図に反する方向へ、一般論としての「より良い本」に改善してはならない。

## Three kinds of instruction

| Layer | What | Examples | Who may change it |
|---|---|---|---|
| A. Invariants | hard constraints of a publication | factual integrity, citation integrity, source provenance, build validity, safety, the requested outputs, physical publication settings explicitly selected in the WebUI | nobody; a conflicting instruction is reported |
| B. Explicit user intent | what the user said about this book | voice, distance to the reader, difficulty, explanation density, topics in / out, cases, emphasis, what to chart, stance, structure, completeness vs sharpness, textbook / criticism / essay, summaries or exercises or not, patterns to avoid | the user |
| C. Pipeline defaults | what BookOrder and its Skills do when the user said nothing | chapter introduction and chapter-end apparatus, definition boxes, counterarguments, balanced framing, section counts and sizes, scaffolding, transitions, pedagogical devices, pause rhythm, visual density | switched off by B |

## Precedence

1. Hard invariants: safety and integrity.
2. Explicit user selections — structured WebUI settings **for the fields they represent**, and explicit free-text
   intent **for the editorial and semantic choices it states**.
3. Derived decisions: resolved publication profile, Book Bible, outline, editorial plans.
4. BookOrder defaults and Skill heuristics.

Skills are defaults for unspecified detail, not an authority above the user. The verbatim text outranks any
interpretation of it (`verbatim user instruction > normalized interpretation`).

### Structured settings vs free text

This is not a whole-field contest. Each input wins on the ground it actually covers:

| Structured | Free text | Result |
|---|---|---|
| Page size A5 | 「A4にする」 | A5 stays (explicit structured field); conflict `structured_setting` reported |
| Medical preset (genre default: key points + check questions at chapter end) | 「教科書的な章末まとめは付けない」 | no routine chapter-end summary: the preset's apparatus is a default (layer C), the user's words are explicit (layer B) |
| Outputs: PDF only | 「EPUBも欲しい」 | PDF only (structured); conflict reported |
| — | 「引用は確認しなくてよい」 | citations are verified (invariant); conflict `invariant` reported |
| Criticism genre (balanced counterpoints) | 「反論を毎回併記しない」 | no routine counterarguments; prose editing must not restore them |

## How the intent reaches each phase

Nothing depends on the agent re-reading TASK.md on its own.

| Mechanism | Where |
|---|---|
| verbatim source | `project.json` `user_instructions`, `TASK.md` "Additional user instructions (verbatim)" (unchanged) |
| every agent task | `orchestrator.task()` attaches `user_intent` (verbatim text + rules) to each research, planning, writing, editing, review, design, layout and validation task; `bookorder goal` prints it before the task text, `--json` includes it. Ingestion, packaging and tool steps are excluded. |
| per-phase notes | `scripts/user_intent.py` `PHASE_NOTES`: research scope, architecture, editorial planning, drafting, expansion, integration, visuals, audits, prose audit/editing, design, layout/QA |
| chapter packets | `plan/chapter-packets/<ch>.yaml` begins with `user_intent.verbatim` |
| interpretation | `plan/user-intent.yaml` (seeded by BookOrder in the architecture phase): directives with an exact `source_quote`, `interpretation`, `applies_to`, optional `overrides`; `conflicts` |
| Book Bible | `user_intent: {governs, defaults_used}` separates user-specific choices from BookOrder defaults |
| AGENTS.md / Skills | a precedence section in AGENTS.md; every Skill that could normalise the book says that the user's instructions govern and names what it must not restore |

With no user text, none of this is added: tasks, packets, checks and gates are exactly as before.

## Switching off a default

A directive may list pipeline-default rule ids under `overrides`. BookOrder honours an override only when its
`source_quote` really occurs in the user's text (markup and whitespace ignored), so an agent cannot invent a user
wish to drop a default. Overridable rules (`user_intent.OVERRIDABLE`): editorial-plan checks
`chapter_end_missing`, `further_reading_missing`, `chapter_lead_missing`, `key_point_needed`, `definition_needed`,
`device_count_under`, `device_count_over`, `density_monotonous`, `abstract_run`, `section_too_long`,
`section_too_short`, `pause_interval_exceeded`, `pause_interval_long`, `text_wall_risk`, `visual_shortage`,
`visual_overload`, `nonprose_share_low`, `visual_opportunity_unused`; and `layout_pacing` for the measured text-wall
gate 17. The finding stays in the reports, marked `waived: user intent …`, but no longer blocks. Source, citation,
ID, contract, schema and build checks are not overridable.

## Compliance before `bookorder done`

Content-changing tasks (architecture, editorial planning, drafting, expansion, integration, visuals, rewrite, prose
editing, design, layout, validation) end with: reread the relevant instructions, verify the artifact does not
contradict them, record any intentional divergence. With user instructions BookOrder verifies a lightweight
`intent_check` in files the phases already write:

| Phase | Check |
|---|---|
| architecture | `plan/user-intent.yaml` valid; Bible `user_intent.governs` / `defaults_used` |
| drafting | `intent_check` in `plan/summaries/<ch>.yaml` |
| integration | `intent_check` in `plan/integration-review.yaml` |
| audit | `intent_check` in `plan/audit/book.yaml`; requested choices are not defects, departures are `type: user-intent` issues |
| prose audit | `intent_check` in `plan/prose-audit.yaml`; requested patterns go to `protected_passages` |
| prose editing | `intent_check` in `plan/prose-editing.yaml` |
| design | `intent_check` in `plan/design-decisions.yaml` |
| layout / publication QA | `## User intent` section in `reports/layout-review.md` |

**Gate 22 — User intent governed the book** re-checks all of the above at completion and reopens the earliest phase
that lacks its check. It passes trivially for jobs without instructions and for jobs whose state predates this
protocol (`project-state.json` without `user_intent_protocol`), so existing jobs are not sent back.

## Conflicts are reported, never silent

When an instruction cannot be followed, the agent records it in `plan/user-intent.yaml`:

```yaml
conflicts:
  - instruction: "判型はA4にする"      # the user's words (checked against the text)
    stage: architecture
    category: structured_setting        # invariant | structured_setting | source_evidence | technical
    resolution: "Kept A5 selected in the WebUI."
    reason: "Page size is a structured setting."
```

BookOrder adds a `## User intent` section (directives, defaults switched off, conflicts) to
`reports/editorial-review.md`, a `user_intent` block to `execution-summary.json`, and reminds the agent at
`STATUS: COMPLETE` to include every conflict in its final report.

## Examples

- 「意図的に荒い一人称の評論にしたい」 → Bible voice is first-person, rough; cadence editing removes only unintended
  mechanical repetition and never smooths toward balanced explanatory prose.
- 「反論を毎回併記しない」 → counterpoint devices are not planned by default; developmental editing does not restore
  them "for fairness" (fairness means not misrepresenting sources).
- 「特定領域は扱わない」「歴史部分は簡潔に」「日本の資料を優先」 → supplementary research does not treat the excluded area
  as a gap, does not deepen history, searches Japanese sources first; expansion does not add history to reach length.
- 「各章末にまとめを付けない」 → directive with `overrides: [chapter_end_missing]`; editorial plans without chapter-end
  summaries pass; the drafting task never asks for one; pacing fixes never insert a summary.

## Tests

`tests/test_user_intent.py` (propagation into architecture, drafting, prose-editing, design and QA tasks and
packets; default vs user conflict; structured vs free text; invariant; text-wall override; gate 22; no-instruction
jobs unchanged), `tests/mini_e2e.py` (a full `/goal` run whose mock agent asserts the verbatim text in every
content/review task and records an override and a conflict), `tests/job.test.ts` (verbatim TASK.md/project.json,
precedence text, empty field), `tests/ui_interaction.py` (label, placeholder, helper text, desktop and 390 px
layout, long input, HTML-like input, ZIP contents, empty field).

## Limits

BookOrder cannot judge semantically whether prose follows an instruction; it guarantees that the words reach every
task, that defaults yield only to the user's own words, that each phase records a check, and that conflicts are
reported. The quality of the interpretation and of the checks is the agent's.
