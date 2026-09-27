# Portable Publishing Job · v0.2

1. Extract this ZIP and open the `publishing-job` folder with Codex, Claude Code, Gemini CLI or another agent
   that can read files and run commands.
2. Give ONE instruction. With Codex use `/goal`:

   ```
   /goal AGENTS.mdを読み、bookorder goal が STATUS: COMPLETE を表示するまで出版ジョブを最後まで実行してください。
   ```

   Other agents: send the same sentence as a normal prompt.
3. The agent loops `bookorder goal` → task → `bookorder done <task>` until BookOrder reports
   `STATUS: COMPLETE`. BookOrder owns the publication lifecycle: source ingestion, supplementary research,
   corpus synthesis, research freeze, Book Bible, architecture, chapter contracts, chapter-by-chapter drafting and
   expansion, integration, figures/tables/equations, audit, targeted rewrite, re-audit, design, layout, build,
   validation and packaging. You should not have to say "continue".
4. Read the publications in `publish/` and editable exchange documents in `interchange/`.
   `publish/result.zip` is the completed, editable project.

Check progress at any time: `execution-summary.json` (status, phases, counts, gates, diagnosis),
`run-events.jsonl` (every stage, tool and skill invocation), `bookorder status`.

`source/` is the canonical source. Never treat an exported PDF, DOCX, HTML or EPUB as its replacement.

Redistributed runtimes and fonts keep their separate upstream terms (GPL for Pandoc, Apache-2.0 for Typst, PSF
and others for Python, SIL Open Font License 1.1 for the fonts). Windows Python's LICENSE.txt includes Microsoft
Distributable Code conditions, applying only to that code. Keep all notices in `third-party/` and pass their
conditions to downstream recipients; do not strip or relicense runtime binaries when sharing a job or result ZIP.

## Local tools

When project.json has `runtime.bundled: true`, use `bookorder.cmd <command>` on Windows or
`sh bookorder <command>` on macOS/Linux. The launchers verify and unpack the bundled Python, Pandoc, Typst and
fonts inside this folder without installing or downloading anything. Low-level actions remain available through
`run.cmd` / `sh run.sh`: `check`, `goal`, `status`, `source-check`, `build`, `validate`, `package`.

Without bundled tools, run `python scripts/check_env.py`; Python 3.10+, Pandoc 3.6+ and Typst 0.13+ are needed.
Tool locations may be set with the `PANDOC` and `TYPST` environment variables. `pdftotext` (Poppler) is used for
PDF sources when available; otherwise the agent extracts PDFs. Automatic URL fetching needs network access for
the shell; if the agent sandbox blocks it, URLs are handed to the agent as `ingest:` tasks.

## Commands

```
bookorder goal | done <task> [--note] | status [--json] | gates
bookorder source list | fetch | submit <id> --file f | confirm <id> --note | accept-partial <id> --note
bookorder source unavailable <id> --attempt ... --reason ... | add --url ... [--post-draft --reason ... --issue ...]
bookorder research log --query ... [--gap --tool --candidates --selected --rejected]
bookorder audit resolve <id> --note ... [--wontfix] | audit report
bookorder build [--theme name] | fonts | theme list | theme preview <name>
bookorder block <task> --category ... --reason ... | unblock --note ...
bookorder rescale --pages N --user-approval "..."   (only with the user's explicit approval)
```

## Authoring conventions

- One chapter per Markdown file (`source/manuscript/NN-name.md`), starting with `# Title {#ch-name}`; every
  heading has an explicit stable ID (`{#sec-name}`).
- Citations use stable source IDs: `[cite:src-0042]`, `[cite:src-0042,src-0061]`, `[cite:src-0042, p. 7]`.
  Visible numbers are produced by the citation style (`citations.style` in project.json: `numeric`,
  `author-year` or `note`).
- Cross references: `@ch:name`, `@sec:name`, `@fig:name`, `@tbl:name`, `@eq:name`; numbers are computed at
  render time.
- Equations: `$inline$`; numbered display equations `::: {.equation #eq-name}` + `$$...$$` + `:::`. PDF uses
  native Typst math, HTML/EPUB MathML, DOCX native Word equations.
- Figures `![Caption](source/assets/figures/x.svg){#fig-name}`; tables `Table: Caption {#tbl-name}`; Diagram IR
  in `source/assets/diagrams/*.yaml` is rendered to SVG automatically.
- `book.author` and `book.colophon` may be added to project.json. Set the actual copyright and colophon before
  publication; defaults make no ownership claims.

## Book design

Read [docs/design-system.md](docs/design-system.md). Five themes (modern-technical, academic-jp, medical-textbook,
minimal-monochrome, business-reference) share one Design Spec schema; fonts are configured per role in
book.design.yaml. custom.css loads last for HTML/Web/EPUB; custom.typ overrides PDF styles.
