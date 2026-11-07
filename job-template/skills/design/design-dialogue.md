# Design dialogue

In a Claude-orchestrated job the book's design is not picked from a menu and not finished by the agent alone. You
design it with the user, in conversation, learning from well-made reference books and looking at real typeset
pages. This extends skills/design/editorial-design.md; its craft rules (reading mode, pacing, components, layout
references) still apply.

## What is free and what is fixed

Free: theme (any existing one, or a book-specific theme you write), page size and margins, typography roles,
colours, chapter openers, headings, callouts, tables, figure style, running heads, folios, density and rhythm —
in book.design.yaml, `themes/<name>/` (theme.yaml, css/*.css for HTML/EPUB/site, typst/theme.typ for PDF),
custom.typ and custom.css. The WebUI's design choices are a starting point; what the user says in this
conversation outranks them. Record each change of a WebUI value in plan/design-dialogue.md.

Fixed: manuscript text, citations, factual chart data and figure content (frozen at the handoff), the requested
outputs, and legibility. A page-size or density change moves the page count; say so when you propose it.

## The loop

0. **Reference books.** List 4–6 books this one should learn from: same genre and reading mode, admired for clear,
   practical design, plus one or two exemplary outliers; the user's named books first (project.json
   design_references.books). `bookorder delegate design-refs` has Codex find them and collect public sample pages
   (publisher previews, sample PDFs, retailer look-inside images) into design/references/ with
   design/references.yaml. Open every image and write plan/design-references.yaml:
   for each book — trim, text block and margin proportions, columns, body size/leading relative to the page, heading
   hierarchy, chapter opener structure, how tables/figures/callouts are treated, colour use, what makes it readable,
   and what does NOT fit this book. Learn principles; never copy text, artwork, logos or a recognisable trade dress.
   Show the user the list and ask if any should be added or dropped.
1. **Read the book.** plan/book-bible.yaml (tone, readers, reading mode), plan/publication-architecture.yaml, two
   representative chapters, the user's art direction and instructions.
2. **Propose 2–3 directions in words**, each grounded in named references and this book's use, e.g.
   *"Like <ref A>'s practical spreads: B5, sans headings on a 2-level hierarchy, tinted procedure boxes, tables with
   strong header rows; body 9.5pt/1.75 Noto Serif."* Name the trade-offs (pages, reading mode, printing cost). Decide
   minor matters yourself; ask only what the user will care about.
3. **Build it.** Small changes: book.design.yaml and custom.typ. A distinct direction: `bookorder theme fork
   <closest-theme> book`, then rewrite themes/book/typst/theme.typ and css/*.css. Keep renderer contracts (the
   functions and labels the template calls); change their appearance freely.
4. **Proof and look.** `bookorder proof` → page PNGs and proofs/<run>/compare.html (proof beside references).
   Critique against the checklist below before showing anything. Fix what is obviously wrong first.
5. **Show and ask.** Show the pages with a short description and one or two specific questions
   ("見出しの青をもう少し落ち着かせますか？" "章扉は左寄せと中央寄せのどちらが好みですか？"). Offer quick variants
   (`bookorder proof --label a`, `--label b`) when the user is unsure.
6. **Apply feedback literally, then interpret.** "もっと余白を" → margins and spacing, not a smaller font. Re-proof
   after each round; log date, the user's words, what changed and the proof folder in plan/design-dialogue.md.
7. **Images.** If the book uses generated images, write plan/image-style.md (skills/design/image-style.md) from the
   agreed direction, run `bookorder images samples`, choose the anchor with the user (`bookorder images anchor …`).
8. **Approval.** Only when the user says it is good: `bookorder design-approve --user-approval "<their words>"`,
   write plan/design-decisions.yaml (theme, decisions [{direction, spec_change}], references_applied, overrides,
   notes, intent_check), then `bookorder done design`. Later changes to the design files, the image style sheet or
   the anchor need a new approval.

If the user says "おまかせで", still do references, two proof rounds and the checklist, and record their words.

## Checklist: refined, readable, clear, practical

- Text block: comfortable measure (about 30–45 Japanese characters per line in one column), leading 1.6–1.9, no
  cramped margins; the inner margin survives binding.
- Hierarchy: at most three heading levels visible on a spread; each level distinct by more than one cue
  (size, weight, space), and space above > space below.
- Colour: one accent used for meaning (navigation, key points), not decoration; everything works in grayscale.
- Tables: header row clearly marked, numbers right-aligned, few rules, no text crammed below 7pt.
- Figures and captions: consistent widths on a grid, captions in one syntax, figure near its first mention.
- Callouts: two or three kinds at most, each with a distinct and consistent treatment; not every page boxed.
- Openers and running heads tell the reader where they are; folios readable.
- Practical use: a reader can scan a spread and find the point, the procedure, the warning and the source.
- Consistency: chapters look like one book; generated images match the image style sheet and anchor.
