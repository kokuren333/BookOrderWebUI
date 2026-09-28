# Prose and Skill audit (2026-09-29)

## Before migration

`job-template/skills/` held nine flat Markdown guides. There was no general Skill loader: `scripts/orchestrator.py` mapped phases to literal paths, while `src/templates.ts` and `tools/ui-bundle.cjs` copied the template tree recursively into generated jobs. `scripts/package.py` also packages `skills/` recursively. CLI tasks expose skill paths, and `run-events.jsonl` / `execution-summary.json` record them. `tests/job.test.ts`, `tests/mini_e2e.py`, `tests/test_orchestrator.py`, `job-template/AGENTS.md`, authoring guidance and `docs/vnext-audit.md` referenced old paths. Existing generated jobs retain their own old flat guides and matching old orchestrator; new jobs use the new tree and path strings.

## Responsibility map

`editing.md` handles pre-audit whole-book integration and ledger-directed factual/structural rewrites. `audit.md` verifies claims, source support, citations and consistency without fixing them. `publication-qa.md` verifies built output and layout. New `prose-audit.md` and `whole-book-review.md` diagnose rhetorical repetition across the complete manuscript without changing it. `developmental-editing.md` makes structural prose edits; `cadence-editing.md` makes local rhythm edits. The split prevents the same prose pass from running in integration, audit and publication QA.

## Existing pipeline and change

Before: research → outline → draft → chapter review → assets → integration → fact/citation audit → ledger rewrite → final audit → design/layout/build → publication QA.

After: research → outline → draft → chapter review → assets → integration → fact/citation audit → ledger rewrite → **whole-book prose audit → developmental/cadence edit** → final fact/citation audit → design/layout/build → publication QA. `reports/prose-signals.json` is descriptive only. The prose report and edit log are `plan/prose-audit.yaml` and `plan/prose-editing.yaml`.

## Migration plan and compatibility

Move the nine files into responsibility directories. Resolve task skills by unique basename through a recursive scanner restricted to the five Skill categories. Reject duplicate basenames. Update job instructions, source references and tests. The web template glob and project packaging already recurse, so no UI or ZIP compatibility shim is needed. Existing job ZIPs are self-contained and remain runnable. For a manually maintained job, update old `skills/<name>.md` references to the new paths in `docs/SKILLS_ARCHITECTURE.md`; no permanent duplicate files are shipped.

The new phase state is added with `setdefault` when loading older state. A resumed job with completed earlier phases will run the new prose phases before publication. Changes to cited claims require explicit source recheck and then the existing final audit.

## External review

See `docs/PROSE_QUALITY.md` for sources and decisions. No external implementation or content is vendored.
