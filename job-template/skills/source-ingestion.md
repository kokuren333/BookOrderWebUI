# Source ingestion

Every explicitly supplied file and URL gets a permanent source ID (`src-0001`, …) and is attempted. Registering
a URL is not reading it. BookOrder fetches URLs and extracts files itself (HTML main content → Markdown, DOCX /
EPUB / ODT / RTF via Pandoc, text formats directly, PDF via pdftotext when available) and stores the result in
`research/<supplied|discovered>/<id>/source.md` with `metadata.json` (URL/path, title, author, date, retrieval
time, character count, SHA-256, attempts, limitations).

You receive a task only when the tool could not finish a source:

- `ingest:<id>` — fetch failed (network sandbox, bot protection, JavaScript page) or the format needs you
  (scanned PDF, image, unsupported binary). Open it with your own browser/PDF tools and extract the COMPLETE
  readable text, not the title or the first paragraphs. Save it to a temporary Markdown file and run
  `bookorder source submit <id> --file <file> --status fully_ingested --method <how> [--title --author --published --site]`.
  If only part is accessible use `--status partially_ingested --note "what is missing"`.
- `verify:<id>` — the extraction looks short, truncated or gated. Compare with the original. Then either
  `bookorder source confirm <id> --note "why it is complete"`, submit the full text, or
  `bookorder source accept-partial <id> --note "what is missing and why"`.
- Truly unreadable: `bookorder source unavailable <id> --attempt "what you tried" --reason "why"`. A reason is
  mandatory and the source stays visible as unavailable in every report.

Never mark a source unavailable or complete to save time. Duplicate URLs are detected automatically and point to
their first occurrence. Ingestion is complete only when no supplied source is pending.
