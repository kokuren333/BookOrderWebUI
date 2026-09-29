# Citation and bibliography

How the text refers to a source and how the back matter lists sources are two separate settings. Previously one
CSL file (`citations.style`) decided both, so footnote citations produced an unnumbered author-sorted list and
everything landed in one 「参考文献」. Code: `scripts/bibliography.py` (Citation Manager + Bibliography Builder),
wired into `common.combined()`.

## Settings (`project.json citations`)

| Key | Values | Meaning |
|---|---|---|
| `in_text_citation_style` (`style` kept for compatibility) | numeric, author-year, note | how the text cites |
| `footnote_style` | full, short, numbered_reference | what a footnote contains (note only): the full record, author + short title, or the back-matter number `[n]` |
| `bibliography_style` | standard, author_date | how one entry is formatted (`templates/csl/bibliography-*.csl`, entry format only) |
| `bibliography_numbering` | numbered, unnumbered | `[1]`, `[2]` … in the back matter |
| `numbering_scope` | per_group, continuous | numbers restart per list, or run through all lists |
| `bibliography_sort` | citation_order, author, title | order within a list (default: citation order for numeric, author otherwise) |
| `bibliography_grouping` | `{cited, background, visual, design}` | which lists to produce |
| `citation_source_roles` | default `[evidence]` | roles that may be cited in the text |
| `reference_source_roles` | default `[further_reading]` | reader-facing sources listed under 参考資料; background is never listed |

The WebUI (Advanced → 04 調査・引用・参考文献) writes all of them for new jobs. A `project.json` without any of the new
keys keeps the legacy single-CSL behaviour exactly.

## Lists

| Group | Title (ja / en) | Contents |
|---|---|---|
| cited | 引用文献 / Cited references | every source cited in the text, in the configured order |
| background | 参考資料 / Further reading | usable sources explicitly assigned the `further_reading` role; never cited in the text |
| visual | 図表・画像出典 / Figure and image sources | sources named by figures actually present in the manuscript and uploaded images actually placed or redrawn (with credit); no prose citation |
| design | (not emitted) | layout / style / visual references never appear in a bibliography |

A source appears in one list only. Empty lists and lists switched off are omitted. `reports/bibliography.json` records
the policy, the order of first citation in the text and every list with its numbers.

## How it is built

1. citeproc renders only the in-text form with the in-text CSL (`numeric.csl`, Pandoc's default author-date, `note.csl` or
   `note-short.csl`) and `suppress-bibliography: true`. With `footnote_style: numbered_reference` the numeric form is
   rendered and each citation is moved into a footnote.
2. The builder collects the lists (above) and formats each entry once with the bibliography-only CSL.
3. It numbers the entries (`[n] ` prefix) per list or continuously and writes `#refs` with one unnumbered sub-heading per
   list under 「参考文献」. Entry anchors stay `ref-<id>`, so linked citations resolve in HTML, EPUB and the site; the
   Typst renderer keeps using the `#refs` block.

Consistency rules: with numeric in-text citations (or numbered_reference footnotes) the cited list is always numbered
and in citation order, so the numbers in the text match the list; the cited list cannot be switched off while the text
cites (except footnote styles). Adjustments are recorded in `policy.adjustments`.

## Examples

Footnotes in the text, numbered back matter:

```
本文: 観察は4時間ごとに行う。¹            脚注: ¹ 日本看護学会, 急性期看護ガイドライン, 2024年.
引用文献  [1] 日本看護学会. 急性期看護ガイドライン. 2024.
参考資料  [1] 山田花子. 新人看護師の一年. 2023. (`further_reading` role)
```

Author-year in the text, numbered back matter (`numbering_scope: continuous`):

```
本文: 観察は4時間ごとに行う (日本看護学会, 2024)。
引用文献  [1] 日本看護学会 (2024). 急性期看護ガイドライン.
参考資料  [2] 山田花子 (2023). 新人看護師の一年. (`further_reading` role)
```

## QA

`bibliography.check_report()` (part of gate 23): lists switched off but built, numbering different from the policy, a
source listed twice, 引用文献 different from the sources cited in the text, numeric citations out of order, a cited
source listed under 参考資料, a cited source whose role is not a citation role. The audit additionally raises
`source-role` issues for citations of non-citable sources before the book is built.

## Tests

`tests/test_publication_architecture.py` (`test_03_footnote_citations_with_numbered_bibliography`,
`test_04_author_year_citations_with_numbered_bibliography`, `test_legacy_citations_keep_the_single_list`),
`tests/architecture_e2e.py` (footnotes + grouped numbered lists in HTML and PDF), `tests/mini_e2e.py` (legacy numeric).
