# Audit

The audit runs after all chapters and major assets exist. BookOrder runs deterministic checks itself (citation /
source mismatches, unavailable or unknown sources, hard-coded citation numbers, numeric claims without citation,
supplied-source coverage, terminology drift, concepts before introduction, duplicated passages, broken cross
references, missing or unplanned assets, uncaptioned figures, equation IDs, chapter balance, visual pacing,
Design Spec validity) and keeps every finding in `reports/audit-ledger.json` / `reports/audit-report.yaml`.

Your part is the semantic audit that tools cannot do. Audit against the user's instructions as well as the sources:
a choice the user explicitly asked for (no chapter summaries, a one-sided critical stance, a rough voice, an omitted
topic) is not a defect and must not be sent to rewriting. A departure from the user's instructions is an issue with
`type: user-intent`. Factual, citation and provenance errors are always issues, whatever the instructions say.

Source roles (plan/source-roles.yaml) are part of citation integrity: a citation of a background, structure or
reference-only source is a `source-role` issue (BookOrder detects it); a factual claim supported only by background
or experience sources is a high `source-role` issue; a claim below the evidence policy's authority
(plan/publication-architecture.yaml evidence_policy) is an `evidence-authority` issue. Structural problems — the
same chapter template everywhere, exercises without answers, exercises or blocks the architecture excludes — are
`publication-architecture` issues (reports/publication-architecture-qa.yaml).

## Chapter audit (tasks `audit:<chapter>`, parallel)

Re-read the chapter against its packet, the research notes and source texts, and the Book Bible. Check factual
consistency, unsupported claims, whether each citation really supports its sentence, contradictions, terminology
and definitions, repeated explanations, duplicated examples, dependency errors, transitions, and figure / table /
equation consistency and notation. Write `plan/audit/<chapter>.yaml`:

```yaml
chapter: ch-attention
reviewed: true
checks: [what you verified]
issues:
  - {severity: high, section: sec-attention-cost, type: unsupported-claim, description: "...", action: rewrite, evidence: "quoted text"}
```

Severity: high = wrong, unsupported or misleading content, broken citation/reference; medium = clarity,
repetition, terminology, weak transition; low = polish. Report real problems only and do not fix them yet.

## Whole-book audit (task `audit:book`)

Cross-chapter contradictions, narrative progression, chapter balance, supplied-source coverage
(`reports/source-coverage.json`), bibliography and design consistency. Write `plan/audit/book.yaml` with
`reviewed_chapters` (all), `issues` and, when the user wrote instructions, `intent_check` (how the whole book
matches them).

## Re-audit (tasks `reaudit:<chapter>`)

After targeted rewrites, re-read each changed chapter completely and write `plan/audit/final-<chapter>.yaml`
(`reviewed: true`, `new_issues`). New high or medium issues send the book back to rewriting. The publication
cannot complete while any high-severity issue is open or the manuscript changed after its final audit.
