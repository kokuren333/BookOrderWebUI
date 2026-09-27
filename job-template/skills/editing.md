# Whole-book editing

## Integration pass (task `integrate`)

Read the manuscript in order as one book, not a set of essays. BookOrder's deterministic findings (terminology
drift against glossary/Bible `forbidden`/`avoid` variants, concepts used before their introducing chapter,
duplicated paragraphs and sentences, broken cross references, missing hand-offs, chapter size imbalance) are
listed in the task and in `reports/audit-report.yaml`. Also look for what tools cannot see: inconsistent
definitions, contradictions, missing callbacks, abrupt transitions, weak hand-offs, inconsistent voice.

Fix the canonical chapters, keep contracts satisfied, update summaries/glossary, then write
`plan/integration-review.yaml` with `reviewed_chapters` (all IDs), `changes` and `remaining_issues`.

## Targeted rewrite (tasks `rewrite:<chapter>`)

Rewrite only the affected sections unless a structural fix is required; never regenerate the whole book.
After rewriting update citations, cross references, the chapter summary, glossary, affected figures/tables and
source coverage. Close agent-reported issues with `bookorder audit resolve <id> --note "what changed"`.
Deterministic issues close automatically when the re-audit no longer detects them. A medium issue may be waived
with `--wontfix --note "reason"`; high-severity issues must be fixed. Rewritten chapters are re-audited.

A successful build is not evidence of successful editing.
