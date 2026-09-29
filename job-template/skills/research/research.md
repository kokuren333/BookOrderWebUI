# Research

## Supplementary research (task `research:supplementary`)

After all supplied sources are ingested, skim the corpus and list gaps: missing definitions, primary or official
references, standards, statistics, historical background, newer developments, contradictory evidence,
terminology. That list is a default; the user's instructions set the scope. A topic they exclude is not a gap, a
case or region they emphasise comes first, a part they want brief is not deepened, and sources they prefer (for
example Japanese materials) are searched first. Do not widen the scope for completeness; do keep factual accuracy
and provenance for whatever is covered. Respect `research.allow_web_research` in project.json; when it is false, discover nothing and record
gaps as limitations.

Persist everything — conversation memory is not storage:

```
bookorder research log --query "..." --gap gap-01 --tool <search tool> --candidates results.json --selected <url> [--rejected "<url>=reason"]
bookorder source add --url <url> --query "..." --gap gap-01 --reason "why it is needed"
```

`source add` assigns the next permanent ID and fetches/persists the content. Then write
`research/research-plan.yaml`:

```yaml
web_research: performed        # performed | disabled | not_needed
gaps:
  - id: gap-01
    description: "..."
    priority: high
    status: resolved           # resolved | unresolvable | not_needed
    sources: [src-0101]
    queries: [q-0001]
    note: "..."
```

Prefer primary and authoritative sources when requested. Distinguish verified fact, inference, uncertainty and
opinion.

## Per-source analysis (tasks `analyze:<id>`)

Read each source's complete persisted text and write `research/notes/<id>.yaml`:

```yaml
source: src-0001
relevance: core            # core | supporting | background | irrelevant | duplicate
duplicate_of: src-0000     # only for duplicates
reliability: primary       # primary | secondary | tertiary | unknown
summary: "whole-source synthesis"
key_claims:
  - {text: "...", locator: "section / page"}
concepts: [term, term]
limitations: "..."
bibliographic: {title: "...", authors: ["..."], published: "2024-05-01", container: "...", publisher: "...", type: webpage}
source_role: evidence      # your estimate unless the user set it: evidence | background | further_reading | structure_reference | redraw_source
authority: guideline       # primary_authoritative | guideline | governmental | peer_reviewed | institutional | textbook |
                           # expert_commentary | professional_experience | anecdotal | unknown
```

When you add a source found by web research, declare its role: `bookorder source add --url … --role evidence|background|further_reading|structure_reference --authority … [--citation no]`. Pages used only for the author's viewpoint or experience are `background`; pages to recommend to readers are `further_reading`; neither role gets in-text citations, and only `further_reading` appears in the back matter.

Source role is separate from relevance: a highly relevant nurse's blog can be `relevance: core` and `source_role:
background` — it shapes the book's field perspective but is not cited or shown to readers. Use `further_reading` only
when you explicitly recommend it to readers. Facts, numbers and recommendations cite evidence (guidelines, official data, peer-reviewed work). A role the user chose in the WebUI
always wins over your estimate (plan/source-roles.yaml). Files the user marked as layout, style or visual
references are not sources and never reach this registry.

Relevance decides coverage: every core/supporting supplied source must be reflected in the book (cited where it
supports the text) unless the job disables that requirement. Do not force irrelevant or duplicate sources into
the prose.

## Global synthesis (task `synthesize`)

Only after all notes exist, synthesize the WHOLE corpus — not the first sources, not URL order — into
`plan/book-context.yaml`, `plan/concept-map.yaml`, `plan/argument-map.yaml`, `plan/timeline.yaml`,
`plan/source-clusters.yaml`, `plan/topic-synthesis.yaml` (including `contradictions`) and
`source/metadata/glossary.yaml` (term, definition, aliases, forbidden variants). Identify recurring concepts,
aliases, chronology, disputes, causal relations, primary vs secondary evidence, duplicates, contradictions,
possible chapter boundaries and dependencies.

## Freeze and post-draft research

BookOrder then freezes research (`research/research-lock.json`). Existing IDs never change. If the audit later
reveals a real gap: `bookorder source add --url ... --post-draft --reason "..." --issue audit-021`, write its note,
and cite it only where it is needed. Untracked research during rewriting is not allowed.
