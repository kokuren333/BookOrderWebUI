# Research brief template (plan/research-brief.md)

Claude writes this before supplementary research in a Claude-orchestrated job. It turns the user's research
requirements (project.json `research.requirements`, verbatim) and the book's goal into instructions the research
delegate can execute. Keep it concrete; the delegate reads it with every research task.

```markdown
# Research brief — <book title>

## Purpose
What the reader must be able to do or understand, and what the research must make possible.

## User requirements (verbatim)
<copy project.json research.requirements>

## Research questions
### Part / chapter area A
- Q1 … (what would settle it: e.g. national statistics 2020–2025, a clinical guideline, the statute text)
- Q2 …

## Claims that need evidence
- numbers and trends → official statistics / peer-reviewed data, with year and population
- effects and risks → systematic reviews or guidelines; single studies only as examples, labelled as such
- legal / regulatory statements → the statute, regulation or regulator's guidance itself
- recommendations → the issuing body's own document

## Acceptable sources
Tier 1 first (…); Tier 2 when no Tier 1 exists (…). Recency: … Jurisdictions: … Languages: Japanese and English.

## Exclusions
Topics the user excluded; source types not to use (…).

## General knowledge (no citation needed)
Basics these readers already accept: …

## Targets
Roughly N evidence sources; every research question answered or recorded as a gap.
```
