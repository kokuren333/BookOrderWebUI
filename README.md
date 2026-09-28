# Portable Publishing Job Generator v0.2 (BookOrder vNext)

A completely static React / TypeScript / Vite application. Book instructions, URLs and uploaded files are packaged with JSZip in the browser. There is no AI API, backend, database, account system or automatic agent execution.

## Run

```
npm ci
python tools/prepare-runtimes.py
npm run dev
```

Open http://127.0.0.1:5173. `npm run build` writes the deployable app to `dist/`. Serve that folder through Cloudflare Pages, GitHub Pages or another static host. For deployment below a path, set Vite's base at build time: `npm run build -- --base=/repository/`. No hosting deployment is performed by this repository.

## User flow

Enter the book plan, source files, URLs, research and figure policies, and requested outputs. Download the job ZIP, extract it and open it with a file/command capable AI agent. Give one instruction — with Codex: `/goal AGENTS.mdを読み、bookorder goal が STATUS: COMPLETE を表示するまで出版ジョブを最後まで実行してください。` The job's root orchestrator (`bookorder goal`) then owns every phase — source ingestion, supplementary research, corpus synthesis, research freeze, Book Bible, architecture, chapter contracts, chapter-by-chapter drafting and expansion, integration, assets, audit, targeted rewrite, re-audit, design, layout, build, validation, packaging — and is the only component that can declare the publication complete (17 publication gates). See [docs/vnext-audit.md](docs/vnext-audit.md) and [docs/production-e2e.md](docs/production-e2e.md). Read publications in publish/ and retain publish/result.zip as the editable completed project.

Files remain in browser memory until included in the download; nothing is uploaded or persisted. Very large source collections require enough browser memory for the source data and compressed ZIP.

## Implementation

The runtime preparer is a maintainer step requiring Python and internet access. It downloads pinned official releases, matching source and notices, verifies SHA-256 locks, and writes split static assets to `public/runtimes/`. The lock file is retained; generated archives are ignored by Git. `npm run build` refuses missing/corrupt packs. Deploy the entire `dist/`, including all runtime parts; allow roughly 1 GB of host storage. No dependency download occurs when executing a bundled job. The browser fetches its packs from the same static host. The shared source pack makes job ZIPs relatively large.

Choose the OS/CPU of the machine running the agent: Windows 10+ x64, macOS 15+ arm64/x64, Linux glibc 2.17+ arm64/x64. The ZIP contains Python/Pandoc/Typst, Japanese fonts, notices and locally available corresponding source. The agent uses `run.cmd` or `sh run.sh`; prerequisites are not installed system-wide. The WebUI includes dedicated contents/licensing and safety/data-handling pages, with links beside the download action.

- src/job.ts: portable schema, path-safe source filenames and ZIP generator.
- job-template/: agent instructions, plain Markdown skills, templates and portable Python scripts.
- The canonical source is chapter Markdown, metadata YAML, BibTeX and editable figure assets.
- Pandoc performs Markdown/YAML parsing, citations and document conversion. Typst builds PDF. Python scripts require no third-party Python packages.
- Semantic DOCX uses distinct paragraph styles for DTP mapping. Semantic HTML is separate from the multi-page publication website. The static site has chapter navigation, global cross-references, local search, syntax highlighting, responsive typography and print styling.
- Validation checks canonical structure and references, built HTML links/assets, requested output integrity and source freshness. Packaging requires final validation plus editorial and layout inspection reports. Programmatic checks cannot replace visual/editorial review.

## Verification

```
npm test
npm run build
python tests/test_orchestrator.py   # deterministic orchestration tests (Pandoc required)
python tests/test_user_intent.py    # user instructions reach every phase; precedence, overrides, conflicts, gate 22
python tests/mini_e2e.py            # real /goal orchestration with a scripted mock agent (Pandoc + Typst)
python tests/e2e.py                 # legacy build pipeline on the npm-test job ZIP
python tests/design.py              # themes, tokens, fonts, previews
```

The integration check uses PANDOC and TYPST environment variables when tools are not on PATH. It extracts the ZIP produced by npm test, fills a representative Japanese two-chapter manuscript with a citation, table, figure, code, footnote and cross-chapter references, then builds all formats and checks failure cases. Test tools may be provided as portable executables; app dependencies remain React, JSZip, TypeScript and Vite.

This demonstrates the publishing pipeline with a short fixture. An external agent's actual research quality, 50–400-page writing, licensing review and complete editorial work depend on that agent and its available tools. A generated job alone does not guarantee those outcomes.

## Settings layout (what goes where)

| Section | Basic | Advanced |
|---|---|---|
| 01 本の企画 | title, goal, readers, language, **Target scale** (the only scale input) | tier override (automatic by default) |
| 02 資料と指示 | URLs, files, additional instructions — book-wide priority instruction, carried verbatim into every phase; outranks BookOrder defaults, not structured settings or integrity rules ([docs/USER_INTENT.md](docs/USER_INTENT.md)) | — |
| 03 調査とコンテンツの方針 | research, citation style, whether tables/diagrams/charts/images may be made | — |
| 04 希望する出力 | output formats | — |
| 05 出版形式とデザイン | Publication preset, Genre, Theme, Layout, Page size, Columns | Geometry · Typography · Visual grammar · Expert |
| 06 実行環境 | runtime OS/CPU | — |

A **Publication preset** (Standard Book, Technical / Reference, Medical / Scientific, Magazine / Mook, Compact) fills genre, layout preset, PDF style preset and theme at once; any later edit wins. **Genre** = kind of content, **Layout** = page size, columns and margins, **Theme** = typefaces, colour and component look. Each concept has exactly one control: page size and orientation belong to the layout; density, chapter opener and accent belong to the Design Spec and, when changed from the theme default, are passed on to the StyleBible automatically. Changing the theme keeps the values you changed and the whole layout; only untouched values follow the new theme. The right-hand summary shows the resolved format, typography, tier, PDF style and outputs next to a schematic page and the theme sample.

The WebUI writes only request fields that the job's resolvers already read (`profile`, `layout_preset`, `layout_spec`, `style_preset`, `style_controls`, and `style_bible` only for an explicit accent colour) plus `book.design.yaml`; the job resolves them into plan/profile.resolved.yaml, plan/layout-spec.yaml and plan/style-bible.yaml. Presets, paper sizes, validation limits and the pages→tier rule are shared with the Python resolvers through `job-template/schemas/publication-presets.json`. Untouched settings produce the same project.json and book.design.yaml as earlier releases. Resolution order and the full field mapping: [docs/webui-information-architecture.md](docs/webui-information-architecture.md).

Tests: `npm test` (payload, single authorities, compatibility fixtures), `python tests/test_publication_ui.py` (resolvers + WebUI payload + TypeScript/Python parity), `python tests/ui_interaction.py` (headless Chromium via Playwright; skips without it), and after `python tests/mini_e2e.py --keep`, `python tests/publication_e2e.py` (A5 one-column and B5 two-column PDFs from WebUI payloads).

## Book design

See [the design system guide](job-template/docs/design-system.md). Section 05 of the GUI configures five themes, role fonts, density, components, vector diagrams and custom CSS (page size and orientation are part of the layout). Content IR, Design Spec and renderer are separate; CSS/Typst/DOCX share normalized tokens. Theme preview builds an isolated sample. No alternate PDF backend or print PDF/X certification is implemented.


Design integration: python tests/design.py (PANDOC/TYPST must be available). Portable integration: node --experimental-strip-types tools/make-portable-fixture.mjs, then python tests/e2e.py --portable.

## Editorial prose review

Generated jobs now run a whole-book prose audit after fact/citation correction, followed by targeted developmental and cadence editing and a final fact/citation audit. The deterministic `reports/prose-signals.json` records lexical and structural signals only; its Japanese phrase list is configurable in `config/prose-signals/ja.json`. The agent records contextual decisions in `plan/prose-audit.yaml` and `plan/prose-editing.yaml`. See [Skill architecture](docs/SKILLS_ARCHITECTURE.md) and [prose quality](docs/PROSE_QUALITY.md).

