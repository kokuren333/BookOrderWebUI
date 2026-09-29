# BookOrder WebUI

BookOrder is a browser-based interface for planning a book and preparing a portable publishing job for an AI agent. It helps you describe the book, organize sources by role, set publication and research preferences, and choose deliverables. The downloaded job contains the project instructions and tools the agent uses to research, plan, write, edit, build, and validate the publication.

> 日本語での案内は [README.ja.md](README.ja.md) をご覧ください。

## Use the WebUI

1. Open the deployed static site, or run it locally (see [Run locally](#run-locally)).
2. Choose **Quick** or **Advanced publishing**.
3. Enter the title, goal, target readers, language, and approximate scale.
4. Add source URLs and files, review their estimated roles, and edit the roles where needed.
5. Write the book-specific instructions in your own words. These are carried into the agent's work throughout the job.
6. In Advanced publishing, optionally set the publication structure, evidence and research policy, citations and bibliography, outputs, layout, and design.
7. Choose the OS and CPU of the machine that will run the agent, then download the Publishing Job ZIP.
8. Extract the ZIP, open its `publishing-job` folder with a file-capable AI agent, and ask it to read `AGENTS.md` and run the job to completion. With Codex, the generated task gives a `/goal` command.

The WebUI does not run the agent or fetch the URLs. The agent performs research after you pass it the downloaded job.

## Quick and Advanced modes

**Quick** keeps the form focused on the book plan, source materials, instructions, target scale, requested outputs, and runtime. BookOrder estimates source roles and lets you edit them; the agent resolves the book's structure, figures, and citation approach from the stated intent.

**Advanced publishing** exposes the publication type and optional secondary type, AUTO/GUIDED/FIXED structure mode, chapter block policy, exercise and visual policy, source authority and usage, research settings, citation and bibliography styles, and publication format and design controls. Leave a field automatic when you want the agent to decide from the book's purpose and your instructions.

The additional-instructions field is for book-specific editorial intent: voice, difficulty, explanation depth, subjects to include or exclude, chapter shape, examples, and what should be shown as a figure or table. It is passed through to the agent as written. Structured controls remain authoritative for the settings they represent, such as scale, output formats, and page layout.

## Source roles and citations

Files and URLs use the same Source Role System. URL lists accept one URL per line; each URL gets an editable role card. You can edit one URL at a time or bulk-edit selected URLs. Estimates are marked as estimates and can be changed.

| Role | How BookOrder uses it | Appears in the finished book |
|---|---|---|
| `evidence` | Supports factual claims and can be cited in the text. | In-text citation and cited references when used. |
| `background` | Informs the author's understanding, viewpoint, or topic exploration. | Not cited and not listed. Authoring use only. |
| `further_reading` | A source explicitly recommended to readers. | Optional Further reading / 参考資料 list; no in-text citation. |
| `structure_reference` | Informs organization or explanation sequence. | Not cited or listed. |
| `layout_reference`, `style_reference`, `visual_reference` | Informs presentation or visual design, not factual content. | Not included in the literature bibliography. |
| `redraw_source` | Source for a figure that is actually drawn or adapted. | Figure credit only when the figure is used. |

No single phrase or source role is a verdict about a source. In Advanced publishing, **authority**, **citation**, **intended chapter**, **usage**, and **notes** provide additional context. Role semantics still apply: background is never made citable just by changing its citation setting.

In-text citation style and bibliography formatting/grouping are separate choices. Evidence sources used for factual claims belong in cited references. Background materials stay private to the authoring process. Only sources assigned `further_reading` are eligible for the reader-facing Further reading list.

## What happens in the publishing job

The WebUI creates a ZIP; the agent runs the job in the extracted folder. BookOrder's intent-driven architecture plans each book from the user's intent, audience, publication type, and source roles instead of applying a fixed chapter template.

The job separates responsibilities across its workflow:

- Research ingests supplied sources and, when allowed, discovers additional web sources. Supplied and agent-discovered sources follow the same role and citation rules.
- Publication planning resolves the book's structure and chapter-specific blocks. AUTO, GUIDED, and FIXED control how much structure is inferred or constrained.
- Drafting and editing produce canonical chapter Markdown, with citations, cross-references, and figures connected to source metadata.
- Audit and QA check source roles, citations, structure, visual assets, and requested outputs.
- Build and validation create the selected formats. Packaging requires the applicable publication checks to pass.

The canonical editable content is the chapter Markdown and associated project metadata and assets. PDF, DOCX, HTML, EPUB, and the static site are outputs; they do not replace the canonical source.

## Data handling

Files are handled in the browser and included in the ZIP; the WebUI does not upload them to a BookOrder server. The WebUI does not persist the form to an account or database. Keep the downloaded ZIP secure because it contains the book instructions and source materials. See the in-app **Safety & data handling** page for details about bundled runtimes, licenses, and execution.

## Run locally

```sh
npm ci
python tools/prepare-runtimes.py
npm run dev
```

Open `http://127.0.0.1:5173`. The runtime preparation command downloads pinned runtime assets for packaging the generated jobs. `npm run build` creates the static site in `dist/`; deploy that directory to a static host. For hosting under a path, set Vite's base, for example `npm run build -- --base=/repository/`.

## Further documentation

- [Source Role System](docs/SOURCE_ROLE_SYSTEM.md)
- [Citation and bibliography behavior](docs/CITATION_AND_BIBLIOGRAPHY.md)
- [Intent-driven publication architecture](docs/INTENT_DRIVEN_PUBLICATION_ARCHITECTURE.md)
- [WebUI information architecture](docs/webui-information-architecture.md)
- The in-app **Safety & data handling** page (runtime, licensing, and execution details)

