# Prose quality in BookOrder

Review of generated development histories, essays/criticism and medical teaching material found repeated chapter-purpose announcements, recaps, contrast frames, paragraph mini-summaries, uniform section roles and automatic balancing. These are discourse-level patterns. A sentence can be sound while its repetition across a book tires readers. Detection scores, vocabulary blacklists, emoji removal and artificial variation do not measure that reader cost.

The editor reads the completed book and compares opening, ending and rhetorical role across chapters. `prose-signals.json` gives configurable phrase counts, per-chapter distribution, per-1000-character rates, paragraph/section lengths, lexical n-grams and repeated openings/endings. Python emits no genre mismatch or rhetorical verdict. The reviewer classifies roles from context, compares their rates and sequences, and records evidence and reader work. The editor then makes the minimum effective edit: delete, merge, move, consolidate or keep. It does not regenerate the manuscript. Each edit records citation impact; changed or uncertain cited claims require a supported source recheck before the prose phase can complete, followed by the existing final audit of changed chapters.

The goal of prose editing is the book the user asked for, with less mechanical repetition and over-explanation —
not a humanised or normalised house style. The user's verbatim instructions come before genre: a requested rough
first-person voice, a one-sided critical stance, or the absence of summaries and counterarguments is protected
(`protected_passages`), and neither developmental nor cadence editing may restore balance, scaffolding or summaries
the user excluded. Both editing files record an `intent_check`; see [USER_INTENT.md](USER_INTENT.md).

Genre comes from the resolved publication profile. Medical/scientific prose retains necessary uncertainty, warning and definitions, while avoiding duplicated explanations. Technical teaching can retain useful scaffolding; repeated summaries still need a purpose. Essay and criticism can use stronger authorial voice and fewer automatic counterarguments. These are qualitative policies rather than numeric thresholds. The StyleBible supplies the existing voice context.

## External work reviewed

| Source | Adopted idea | Decision |
| --- | --- | --- |
| [msimchowitz/writing-skills](https://github.com/msimchowitz/writing-skills), especially [writing-cadence](https://github.com/msimchowitz/writing-skills/tree/main/for-agents/writing-cadence), [non-autoregressive-writing-pass](https://github.com/msimchowitz/writing-skills/tree/main/for-agents/non-autoregressive-writing-pass), [general-writing](https://github.com/msimchowitz/writing-skills/tree/main/for-agents/general-writing) and [humanizer](https://github.com/msimchowitz/writing-skills/tree/main/for-agents/humanizer) | Whole-draft review, repeated openings/endings, purposeful cadence, minimum effective edit | No broad humanizer rewrite loop or copied text. Repo is MIT licensed. |
| [forjd/better-writing](https://github.com/forjd/better-writing) | Genre and voice context, false-positive checks, preservation of facts | No dependency or wholesale rewrite. Repo is MIT licensed. |
| [textlint-ja AI writing preset](https://github.com/textlint-ja/textlint-rule-preset-ai-writing) | Pattern signals as hints | No default lint failure or marker blacklist: its sentence-level rules do not decide book-level structure. Repo is MIT licensed; no code copied. |
| [textlint Japanese technical writing preset](https://github.com/textlint-ja/textlint-rule-preset-ja-technical-writing) | Awareness of technical-register and terminology checks | No automatic prose decisions; strict defaults can reject legitimate domain wording. Repo is MIT licensed. |

No external code or Skill text is bundled, so there is no copied-code license obligation. The links record the ideas reviewed and their provenance.

## Known limits

The rule-based signals cannot infer whether a caveat is scientifically necessary, whether two arguments are semantically duplicated, or whether a chapter should intentionally mirror another. Japanese phrases reside in `job-template/config/prose-signals/ja.json` as weak signal configuration, not a blacklist. Markdown heuristics may include code or callout text in counts. The whole-book agent review makes those decisions against sources and context.

## Sample PDF dry-run

On 2026-09-29, text extraction over the three user-provided books succeeded without copying them into this repository: medical teaching text 45 pages / 35,238 extracted characters, development history 36 pages / 36,912 characters, and criticism 147 pages / 168,013 characters. The configured `ではなく` signal appeared 19, 22 and 138 times respectively; `しかし` appeared 5, 2 and 61 times. This supports chapter-by-chapter review of the criticism book's contrast structure, while the medical qualification remains a protected contextual decision. PDF page extraction does not reliably preserve BookOrder's chapter/paragraph Markdown structure, so these runs validate extraction and whole-document counts only; no book was automatically edited or scored.
