# Art Direction QA (P1-3)

The PDF build writes `reports/art-direction-check.yaml` after rendering and
layout measurement. Its schema is `schemas/art-direction-check.schema.json`.
Each finding names its category, severity, page, component, expected and
observed value, explanation, suggested fix, and measurement scope.

The audit has four evidence layers:

1. **Source:** resolved StyleBible versus compiled renderer tokens; Diagram IR
   SVG node shape; chartkit render records.
2. **PDF:** a dependency-free probe of Typst vector streams measures page colors,
   text sizes, line widths and drawing positions. It records page-level counts
   and vector geometry. Unsupported PDF streams are explicitly reported as
   unavailable.
3. **Layout:** Typst layout marks locate headings, tables and semantic components.
   The audit associates these with PDF text and vector fills/rules where possible,
   then compares component treatments and repeated internal padding.
4. **Book-wide:** page density, repeated component treatments and a conservative
   priority proxy flag hierarchy or rhythm problems. Thresholds vary by genre.

The PDF probe reads Typst-produced PDFs; it is not a general PDF reader.
Font size and vector color are directly measured. Semantic assignment, table
source-note relationships and subjective visual quality cannot always be
established from PDF operators alone. The report distinguishes `source`, `pdf`,
`layout` and `rendered` findings. Missing measurement never becomes an invented
pass for that measurement layer.

Completion gate 20 requires a current QA report, a matching PDF hash when PDF
is requested, and zero high findings. Medium findings warn; low findings are
informational. An editor may document a medium waiver in
`reports/art-direction-waivers.yaml`:

```yaml
waivers:
  - category: visual_monotony
    page: 42
    component: warning
    reason: The repeated warning treatment is deliberate in this appendix.
```

The report retains the finding and records the waiver; a waiver never clears a
high finding. `tools/style-specimen.py` builds medical science and criticism
PDFs and writes per-genre QA reports plus a cross-genre check. The comparison
fails when differences are limited to palette instead of component, hierarchy,
rhythm, table, diagram, chart, caption and opener grammar. It also checks that
the two measured PDFs differ in font sizes, line widths or vector treatment,
independently of their colors.
