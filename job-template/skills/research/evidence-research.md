# Evidence research (Claude-orchestrated jobs)

The user does not have to supply sources. Claude turns the user's goal and research requirements into a research
brief; the research delegate (Codex CLI) builds the corpus from it, maps evidence to each chapter and checks the
drafts against it. This skill is read by both.

## 1. Research brief (Claude, before `research:supplementary`)

Write plan/research-brief.md (template: docs/research-brief.md) from project.json `research.requirements`
(verbatim user requirements), the book's goal, readers and instructions:

- research questions grouped by the part of the book they serve;
- claim types that need evidence (numbers, effects, definitions in regulation, recommendations, history, cases) and
  what kind of source settles each (guideline, statute, statistics, trial, review…);
- acceptable tiers, recency limits, jurisdictions, languages (search Japanese and English when useful);
- exclusions (the user's, and source types to avoid);
- what counts as general knowledge for these readers — stated without citation.

## 2. Corpus (delegate: `research:supplementary`, `analyze:`)

Tier 1 primary sources first, Tier 2 trustworthy secondary sources where no primary exists; weak web pages only to
discover better sources. Every selected source is logged and added with a role:

| Role | Meaning | In the book |
| --- | --- | --- |
| `evidence` | supports a specific fact, number, finding, definition or recommendation | cited in the text; listed in 引用文献 when cited |
| `background` | general knowledge, orientation, viewpoints the author reads | never cited, never listed |
| `further_reading` | only when the user asked for a reader list | listed, not cited |

By default the back matter therefore lists only evidence that the text actually cites.

## 3. Evidence map (delegate: `bookorder delegate evidence <chapter>`, before drafting)

research/evidence/<chapter>.yaml: claims with sources, locators, short verbatim quotes and the strength of the
evidence (strong / moderate / contested / weak) and how to use it (state / attribute / contrast / avoid); numbers;
sharp findings; genuine disagreements; misconceptions; gaps. The quotes are what make it verifiable.

## 4. Verification (after drafting, before a chapter audit is accepted)

- `bookorder delegate factcheck <chapter>` — the delegate reads each factual sentence and the cited passage:
  supported / partly / unsupported / miscited / needs_citation / overhedged. Valid only for the exact chapter text it
  checked (a later edit requires a new check).
- `bookorder evidence verify [--chapter]` — mechanical: every quote in the map occurs in the persisted source text,
  every ID exists, every [cite:] points to an evidence-role source, no factual claim rests on a background source.
- Claude moves real problems into plan/audit/<chapter>.yaml and fixes them in the rewrite phase. Gate 24 requires
  maps, current fact checks and no high verification finding for every chapter.

## Citing well

Cite the specific claim, not the paragraph. Prefer one strong primary source to three weak ones. Do not cite
background sources; if a sentence is general knowledge, it needs no citation, and if it is not, find evidence.
