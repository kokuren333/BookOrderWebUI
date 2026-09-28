# StyleBible (P1-1)

`plan/style-bible.yaml` is the resolved visual language for one book. Its schema is
`bookorder/style-bible@1`. The first orchestrator step and every PDF build resolve it
from BookOrder visual defaults, the selected `styles/genres/<genre>.yaml` template,
`PublicationProfile.art_direction`, then `project.json.style_bible`. An existing
artifact with the same `inputs_fingerprint` is retained so an editor can revise it.
Upstream input changes re-resolve it. Semantic edits invalidate downstream work
through the existing fingerprint, reopen, and ledger process.

The artifact has three layers:

- **Tokens:** palette, typography, lines, spacing, radius, print minima, and visual
  treatment for diagrams, charts, tables, callouts, captions, chapter openers and imagery.
- **Grammar:** rules for meaningful accent, heading hierarchy, labeled relationships,
  color independent chart encoding, header rules, callout variants, and source notes.
- **Exemplars:** canonical samples for chapter opener, headings, body, table, chart,
  diagram, key point, warning, definition, and caption.

`LayoutSpec` remains the only source for page size, margins, writing mode, columns,
spans, and regions. The build compiles StyleBible into `design-tokens.json` with a
column width adaptation. A narrow column may lower H2/H3, caption, and table text
within the printed minimum and tighten callout padding. The semantic StyleBible
itself does not acquire any LayoutSpec geometry. The lint reports likely ugly
Japanese heading wraps; an editor can rephrase or break at a meaningful unit.

Diagram IR and chartkit receive figure tokens from the compiled style. Typst
reads the same compiled style for its chapter opener, table, caption, heading and
callout appearance. Without a StyleBible, the P0-5 figure defaults remain valid.
Figure text below 6.5pt is still rejected. `reports/style-check.yaml` records
mechanical low, medium and high findings; it is revision evidence, not an
automatic verdict on visual taste.

Edit `project.json.style_bible` for stable overrides, for example:

```json
{"style_bible":{"palette":{"accent":"#8C4E35"},"spacing":{"section_gap_mm":7}}}
```

An editor may also adjust the resolved file while its inputs stay constant.
Run `python tools/style-specimen.py` from the source repository to build paired
medical science and criticism PDFs using identical content and LayoutSpec.
Imagery settings are provider independent; image generation and vertical writing
rendering are outside P1-1.

## P1-2 visual grammar

`visual_grammar` in the resolved StyleBible describes the presentation of an
already planned device. The canonical component registry is in
`scripts/visual_grammar.py`: key point, warning, definition, glossary,
counterpoint, case study, pull quote, checklist, chapter summary, further
reading, evidence note, and source note. Each records its semantic role,
priority, preferred placement/span, break behavior, title/icon policy,
treatment, border/fill policy, spacing, and use policy. Priorities are primary,
secondary, tertiary, supporting, and quiet. Treatments include filled box,
side/top rule, inset paragraph, margin label, pull quote, and plain emphasis.
The default rhythm rule avoids adjacent filled boxes.

Genre templates override this grammar. Medical science emphasizes evidence,
compact tables and a high contrast warning; criticism emphasizes prose,
counterpoint and pull quotes with more whitespace. Technical, practical and
essay templates have their own grammar. This changes how an EditorialPlan
device appears; it does not change which devices are planned. Span preferences
are advisory metadata: only LayoutSpec and authored placement choose geometry.

The PDF build emits `reports/style-grammar-report.yaml` with all resolved
component, hierarchy, rhythm, table, diagram, chart, caption and opener values.
Typst uses component treatments and table/caption/rhythm rules; numeric columns
are right-aligned when detected, preserving authored alignment (decimal tab stops
are not yet supported). Diagram IR uses
node shape, whitespace, edge emphasis and annotation style. Chartkit resolves
grid, axis and baseline styles and retains direct label and uncertainty policy
in its render metadata. The specimen generator writes paired PDFs and a
`style-grammar-comparison.yaml` with the same LayoutSpec and semantic content.
Visual rejection remains upstream of asset generation.

## Presets and high-level controls (P1-UI)

`project.style_preset` chooses the genre template (`styles/genres/<template>.yaml`) independently of the profile
genre: technical-clean → technical, medical-evidence → medical_science, practical-guide → practical,
critical-editorial → criticism, essay → essay. Without it the profile genre's template is used, as before. The
resolved file records `preset`.

`project.style_controls` maps a few editorial choices onto existing StyleBible fields (definitions in
`schemas/publication-presets.json`): `visual_density` (tone, spacing scale, visual_grammar.rhythm.section_space),
`typography_scale` (all type roles ±6 %, never below the 6.5 pt minimum), `callout_intensity` (key point / warning /
definition treatments), `table_density` (table and visual_grammar row spacing), `chapter_opener`
(chapter_opener.title_style: editorial, academic, minimal) and `visual_tone` (tone.restraint, tone.ornament).
Controls apply after the template and art direction and before `project.style_bible`, which still wins. Preset and
controls enter `inputs_fingerprint` only when present, so existing jobs keep their fingerprint.

The WebUI shows one control per concept. Density, chapter opener and accent colour are Design Spec settings; when
the user changes one of them from the theme default, the WebUI also writes the matching request —
`style_controls.visual_density` (compact→compact, standard→balanced, spacious→airy), `style_controls.chapter_opener`
and `style_bible.palette.accent` — so the PDF follows the same choice and an explicit accent wins over the style
preset's palette. `typography_scale` is no longer offered in the WebUI (font sizes are set directly) but remains
valid in hand-written project.json files.
