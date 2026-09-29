# Adversarial review of the intent-driven publication architecture (2026-09-29)

Scope: the implementation described in INTENT_DRIVEN_PUBLICATION_ARCHITECTURE.md. Goal: find where it would still
produce template-like, intent-violating or mis-cited books. Only Critical/High findings were fixed.

## Findings

| # | Sev. | Finding | Status |
|---|---|---|---|
| 1 | High | Numeric in-text citations + `numbering_scope: per_group`: 参考資料 restarted at [1], so 「[1]」 in the text was ambiguous. | Fixed: numbering runs on across lists whenever the text cites by number (recorded in `policy.adjustments`). |
| 2 | High | Author-year: the text showed Kaplan 2020a/2020b (citeproc disambiguation) but the list showed 2020 twice. | Fixed: bibliography CSL disambiguates by year suffix; entries are formatted per list, so suffixes are assigned among the same works as in the text. |
| 3 | High | AUTO with no user hint guessed "textbook" and made exercises + answer keys *preferred* for an unknown book (old apparatus back through the default). | Fixed: a guessed archetype never prefers exercises (policy `optional`); an explicit textbook/exam choice or wish still does. |
| 4 | High | Layout pacing (gate 17) revision candidates suggested insert_summary / add_pull_quote / add_counterpoint regardless of the block policy — a path to re-insert excluded apparatus. | Fixed: candidates for forbidden/discouraged blocks are not printed. |
| 5 | High | QA reported an unmet explicit wish (「ケースを多く」, 「図表を多く」) and a mechanical chapter end in the manuscript as MEDIUM; the book reached COMPLETE with them (seen in the first architecture E2E). | Fixed: HIGH (blocking) in AUTO/GUIDED; can stand only with `qa_waivers: [{rule, reason}]` in the architecture file (reported). |
| 6 | High | FIXED/legacy compatibility: the corpus task now asks the agent to estimate `source_role`; an estimate of "background" made the agent's own citations high audit issues in jobs that predate the role system. | Superseded 2026-09-29: role semantics are now enforced consistently in FIXED and adaptive jobs; `background` is writer-only. |
| 7 | Medium | Bibliography CSLs dropped DOI, volume/issue/pages; entries were formatted without the book's locale ("n.d." in Japanese books). | Fixed (cheap, CSL-only; `-M lang`). |
| 8 | Medium | Outline check required a non-empty `blocks` for every chapter ("say at least callout") — pushes a block into pure prose chapters. | Fixed: `blocks: []` is valid; the key must be present. |
| 9 | Low | `publication_architecture: "auto"` (string) was silently treated as a legacy FIXED job. | Fixed (string = mode). |
| 10 | Low | A block both preferred and forbidden in the agent's file was not reported. | Fixed (check error; forbidden wins at load anyway). |
| 11 | Medium | Answer keys are checked for presence, not completeness (one answer for five questions passes). | Not fixed: needs semantic matching; left to audit. |
| 12 | Medium | If `plan/publication-architecture.yaml` becomes unparseable after planning, `load()` silently uses the derived default (AUTO defaults, not the legacy template). | Not fixed: publication planning rejects invalid files; later corruption is visible in `bookorder architecture`; adding hard failure everywhere would stop unrelated phases. |
| 13 | Medium | Signals scan instructions + description only (not the free-text archetype note, chapter architecture, per-file instructions). First matching signal wins (「問題集…問題と解説を中心に」 gives `where_useful`, not `exam_focused`). | Not fixed: archetype choice already sets the exam policy; the agent sees all text verbatim. |
| 14 | Medium | `validate_usage` exists but a hand-edited project.json can put a non-content role into `input.sources`, which would be ingested. WebUI never does this. | Not fixed (report). |
| 15 | Medium | Visual policy `min_distinct_types: 3` (when density ≥ medium) can push variety for its own sake. It blocks only in visual planning and is waivable with a reason. | Not fixed: waiver path is the intended control. |
| 16 | Low | Requirements such as `every_major_chapter_must_have_actionable_content` are text only (not machine-checked). | Report. |
| 17 | Low | Figure/text duplication detection covers Diagram IR labels only and is LOW. | Report. |

## False positives (checked, no defect)

- Layout references reaching the research corpus: `input.assets` is never registered; QA `reference_as_content` also checks any registered path, including agent-added ones.
- Asset images as evidence: assets are not ingested and have no CSL record, so they cannot be cited; they appear only in 図表・画像出典.
- `citation_allowed=false` sources cited: they stay in references.json (so builds do not break), but every such citation is a HIGH `source-role` audit issue (gates 11/13) and a HIGH QA finding (gate 23).
- Silent fallback to the old template: AUTO never falls back to FIXED; unknown modes or invalid requests stop publication planning with a task.
- Same work cited several times: one list entry, same number ([1] … [1, p. 3]).
- Cited vs background duplicates: a source is placed in one list only (cited wins).

## Verification

- `tests/test_publication_architecture.py` (19 tests incl. 6 regression tests for the fixes).
- Bibliography matrix rendered through citeproc (Japanese authors, 3 Western authors + DOI + volume/pages, URL-only/no-author web page, report/guideline, government document, same author same year, missing metadata, no year, repeated citation, cited + background): see the audit report in the conversation.
- FIXED: `tests/mini_e2e.py` on the base commit and on this version; HTML identical after normalising port/date, PDF text differs only in a line wrap caused by the port number, same page count.
- `tests/architecture_e2e.py` now also shows that an unmet explicit wish blocks until fixed or waived.
