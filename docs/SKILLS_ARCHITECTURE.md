# Skill architecture

The source of job skills is `job-template/skills/`; each generated job receives the same hierarchy.

```text
skills/
  authoring/book-authoring.md
  research/{source-ingestion,research}.md
  editorial/{editorial-planning,editing,prose-audit,whole-book-review,developmental-editing,cadence-editing}.md
  design/{editorial-design,figures}.md
  quality/{audit,publication-qa}.md
```

Authoring drafts chapters; research handles source intake and synthesis; editorial plans and edits reader-facing prose; design handles visual and page systems; quality verifies claims and finished publication outputs. Prose audit reports review candidates and never edits. Publication QA checks rendered artifacts.

`scripts/skills.py` recursively scans Markdown under `skills/`, accepting files inside these five category directories at any depth. README, tests, fixtures, build and dist material are excluded. A Skill ID is its unique filename stem. Duplicate stems and missing IDs raise an error. The orchestrator maps phases to IDs, then resolves paths at task creation. Existing Markdown has no frontmatter parser, so frontmatter was not introduced.

Skills are defaults, not authorities. The user's verbatim instructions (project.json `user_instructions`) are
attached to every task the orchestrator prints and outrank Skill preferences for the editorial choices they state;
invariants (facts, citations, provenance, build) and structured WebUI settings stay binding. A Skill rule is written
as an invariant only when it protects integrity ("never invent quotes"); anything that shapes the book (summaries,
counterarguments, device counts, scaffolding, pacing devices) is phrased as a default the user may switch off. See
[USER_INTENT.md](USER_INTENT.md).

Add a Skill by choosing the owning category, creating `<unique-id>.md`, and mapping that ID to a phase in `SKILL_IDS` if the job invokes it. Add a loader test for any new collision or category behavior. Keep a single owner for each edit. Use lowercase kebab-case names.

The prose pipeline is fact/citation audit → ledger rewrite → whole-book prose audit → developmental and cadence edit → final fact/citation audit → publication QA. The user's instructions, then the Book Bible and the resolved publication profile, guide editing judgment. Frequency counts inform the reader of the report; they do not trigger automatic deletion.

Manual migration from older jobs: replace `skills/<name>.md` with `skills/<category>/<name>.md` in custom task instructions, and copy the nested tree. Existing generated jobs contain their own old instructions and remain valid without migration.
