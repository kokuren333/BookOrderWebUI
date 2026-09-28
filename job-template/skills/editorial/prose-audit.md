# Prose audit

Read the manuscript as evidence. Diagnose candidates; do not rewrite here. Use `reports/prose-signals.json` to locate weak lexical and structural signals, then inspect the surrounding argument and the full-book distribution. Record chapter, section, excerpt, rhetorical role, whether the passage gives readers new information, and a proposed action. No single phrase is evidence of AI writing; no deterministic signal is a verdict.

Examine chapter-purpose announcements, recaps, previews, redundant topic announcements, recurring `XではなくY` and automatic balancing, repeated paragraph openings and closing paraphrases, definitions, callouts, key-point boxes, summaries, exercises and checklists. Compare section-role sequences and chapter lengths. Uniformity is a reason to read, never an automatic failure.

Classify orientation, recap, preview, substantive claim, qualification, counterargument, definition, summary and exercise from context rather than lexical matches. Compare role frequencies and sequences across chapters, including chapter-opening recap/preview rates, ending-summary rates and qualification density. Keep lexical repetition and rhetorical repetition distinct.

Use `plan/profile.resolved.yaml` and `plan/book-bible.yaml` for genre and voice. Medical/scientific qualifications and definitions receive high tolerance; essay/criticism receives closer review of automatic balancing. These are review priorities, not thresholds. Report findings in `plan/prose-audit.yaml`; leave the source untouched.
