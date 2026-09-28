# User intent audit (2026-09-29)

Question: the WebUI's *Additional user instructions* are saved verbatim, so why do generated books drift away from
the voice, density, scope and structure the user asked for? This audit traces the free text through every stage
of the job as it was before the change (commit `0ee6941`). The fix is described in [USER_INTENT.md](USER_INTENT.md).

## Where the text went

| Stage | What carried the free text | Reachable by the agent? |
|---|---|---|
| WebUI | `BookForm.instructions` (`src/job.ts`), textarea in `src/App.tsx` | — |
| project.json | `user_instructions` (verbatim) | yes, if the agent opens project.json |
| TASK.md | `## Additional user instructions (verbatim)` followed by `## Precedence of settings` | yes, if the agent opens TASK.md |
| AGENTS.md | "Read TASK.md and project.json. Preserve the user's additional instructions verbatim." (once, under *Trust and data handling*) | only as a start-of-session instruction |
| `scripts/*.py` | **no reader.** No Python module read `user_instructions`; `common.py` only fingerprinted TASK.md for build freshness | — |
| orchestrator NEXT TASKS | `task()` built instructions from the phase, profile, packet and findings; none contained or referenced the user text or TASK.md | no |
| chapter packets | contract, Bible, glossary, summaries, sources, editorial plan; no user text | no |
| Skills (13 files) | none mentioned TASK.md, project `user_instructions` or user intent | no |
| completion gates (1–21) | no gate concerned the user's instructions | — |
| final report (`reports/editorial-review.md`, `execution-summary.json`) | no user-intent or conflict section | — |

The only path from the free text to a phase was: the agent reads TASK.md at the start of the session, remembers it
across dozens of tasks (and sub-agents, and resumed sessions), and chooses to let it outrank the task it is given.

## Findings on the six questions

1. **Was TASK.md required reading for each phase?** No. AGENTS.md asked once. Each task names only its Skill files
   ("Read: skills/…"), and sub-agents that receive one task section never see TASK.md.
2. **Did task packets contain the user text?** No. Neither the printed NEXT TASKS, `bookorder goal --json`, nor
   `plan/chapter-packets/*.yaml` carried it.
3. **Could a phase be completed from the Skill alone?** Yes. Every Skill and task is self-sufficient: the Book
   Bible, profile and packet give all the information needed to pass the checks.
4. **Could editing/QA "improve" against the intent and still pass?** Yes. Nothing compared any artifact with the
   user text. `developmental-editing.md` keeps "genre-required material"; `cadence-editing.md` preserves "the
   established StyleBible voice" (not the user's); `prose-audit.md` sets priorities from the profile genre
   ("essay/criticism receives closer review of automatic balancing") without asking what the user wanted;
   `audit.md` treats "weak transitions" or "repetition" as issues that feed rewrites with no exception for
   requested style.
5. **Was instruction compliance part of completion?** No. No gate, report field or task verification.
6. **Were pipeline defaults stronger than the user text?** Yes, mechanically:
   - `publication_profile.summary_lines()` told architecture and editorial planning that the profile "is binding
     for the plan" — device densities, chapter lead and chapter-end apparatus included.
   - `editorial_plan.check_chapter()` raised `chapter_end_missing` as an **error** ("the profile requires
     key_points at the end of every chapter"). Errors cannot be waived, so a user who wrote 「章末まとめを付けない」
     for a criticism or technical book could not pass editorial planning without adding the summary.
     `pause_interval_exceeded` and `device_count_over` behaved the same way; `device_count_under`,
     `key_point_needed`, `chapter_lead_missing`, `abstract_run` etc. could only be waived with a planner's
     reason, never because the user said so.
   - Gate 17 (measured text walls) could not be waived; its revision candidates include `insert_summary`,
     `add_counterpoint` and `add_pull_quote`, i.e. the exact devices a user may have excluded.
   - `editorial-planning.md`: "chapter end — what the profile requires, in every chapter";
     `editorial-design.md`: "summary at chapter ends"; `book-authoring.md` expansion lists "historical context,
     counterexamples" as the default way to add length.
   - TASK.md's precedence paragraph said the free text "supplements" structured settings, and README /
     `docs/webui-information-architecture.md` / the WebUI hint all described it as supplementary. Agents
     reasonably read it as the weakest input.

## Where intent was lost, by phase

| Phase | Loss mechanism |
|---|---|
| research | scope gaps are listed generically (definitions, history, contradictory evidence), so exclusions and emphasis are re-widened |
| architecture | Bible and outline derived from synthesis + profile; the profile is "binding" |
| editorial planning | profile device counts and chapter-end errors force the default apparatus |
| drafting / expansion | packet and editorial plan only; length deficits are filled with "historical context, counterexamples" |
| integration | "inconsistent voice" is fixed toward the Bible, not toward the user text |
| audit / final audit | requested one-sidedness, roughness or omissions can be logged as medium issues and rewritten |
| prose audit / editing | genre profile and StyleBible voice set the target; balancing and scaffolding can be restored |
| layout pacing | text walls are resolved by adding summaries, counterpoints, pull quotes |
| design / QA | art direction is read from book.design.yaml only |
| completion | no check, no conflict report |

## What was already sound

- The text is preserved verbatim in project.json and TASK.md (tested in `tests/job.test.ts`).
- Structured settings are resolved deterministically (profile, LayoutSpec, StyleBible), so a free-text
  "A4 please" cannot silently change a WebUI A5 selection.
- Invariants (citations, source provenance, audit ledger, build validity) are machine-checked and independent of
  prose preferences.

## Minimal fix (implemented)

Keep project.json / TASK.md as the single source; add no second store of the verbatim text beyond a mirrored copy
BookOrder itself refreshes. Re-inject the verbatim text into every agent task; let explicit user intent switch off
named pipeline defaults (never invariants) with a verbatim quote; require a short intent check in the files the
content-changing phases already write; report conflicts; add one completion gate. See [USER_INTENT.md](USER_INTENT.md).
