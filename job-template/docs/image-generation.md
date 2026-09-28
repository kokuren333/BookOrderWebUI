# Generative image assets (P1-4)

The visual review decides whether a proposed asset is accepted. Comparisons,
quantities, hierarchies and factual relations remain tables, charts or diagrams.
Only accepted abstract/pictorial `type: image` candidates enter image generation.
Their `factuality` is decorative, illustrative or conceptual. A factual image
request is rejected; source-grounded visuals use the appropriate renderer.

An accepted image carries `subject`, `role`, `information_shape: {kind: abstract}`,
`factual_basis: illustrative`, `path: source/assets/images/<id>.png`, and print
`geometry`. The editorial device ID can be linked with `device`. The renderer
prints the caption and any labels; `typography_policy` is always `forbidden`.

At asset generation and build, BookOrder writes:

- `source/assets/generated/<id>.request.json`: normalized `ImageGenerationRequest`
  with StyleBible art direction, LayoutSpec print geometry, source IDs, provider
  status, prompt version and final size.
- `source/assets/generated/<id>.json`: `VisualAsset` provenance, dimensions,
  provider/model/seed, prompt hash, generation and QA status, effective DPI.
- `reports/image-assets-check.yaml`: routing and print QA. It names candidates
  sent to imagegen and those kept on other routes.

`project.image_generation.provider` defaults to unset. This records
`pending_provider` and produces no placeholder. A required unresolved image
blocks completion; an optional unused image produces a warning. `fake` creates
a deterministic patterned PNG for offline tests. It never calls an external
service. No real provider adapter or credentials are bundled.

The print threshold is 300 effective DPI, matching chartkit's raster output.
Adapters currently return non-interlaced 8-bit PNGs. QA checks image validity,
pixels, aspect ratio, request/asset provenance,
duplicate bytes and actual print size. Art Direction QA also compares the
request to the current StyleBible and measures the placed PDF image XObject
bbox and embedded pixel dimensions against the planned width and DPI.
