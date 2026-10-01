# Writing, design and rendering

New WebUI jobs set `workflow.separated: true`. Existing jobs keep the legacy phase order unless a stage command
is used. The existing `goal` command still runs the whole publication. Agents are executed by the host;
BookOrder persists tasks and role assignments, not model API calls or credentials.

```sh
bookorder write --agent writer=my-writer --agent reviewer=my-reviewer
bookorder done <task-id>
# repeat until STATUS: STAGE_COMPLETE
bookorder handoff --export manuscript-handoff.zip
# extract on another host, then:
bookorder design --agent designer=my-designer
bookorder done <task-id>
bookorder render
bookorder pages
```

Windows uses `bookorder.cmd`; without a bundled launcher use `python scripts/cli.py`.
`done` resumes the selected stage. `next` resumes it too; `goal` selects all stages again.
`--json` emits one JSON object on stdout; build diagnostics go to stderr.

Writing completes research, architecture, chapter text, citations, tables/equations, visual content specifications,
figure links/IDs/captions, integration and manuscript audits. It does not generate diagrams or render outputs.
Specify diagram nodes, labels and relations in the asset's `content` or a Diagram IR file; save chart data under
`source/assets/data/`. The designer later produces the visual files at the preassigned paths.

Design covers the Design Spec, typography, geometry and visual generation. Render covers proof builds, layout
review, validation and packaging. Both preserve manuscript text, citations and factual chart data. The handoff
also checks planned visual content separately from editable geometry/style. Layout and image/figure QA remain
active in the later stages; manuscript citation checks remain active in writing and final validation.

At the writing boundary, `handoff/manifest.json` records file hashes, chapter structure, citation/source ID
locations, visual content/intents, design requirements and prohibited changes, with copies of canonical inputs.
The exported ZIP includes source, input, research, plans, scripts, configuration, state and original runtime
archives so another agent/model/host can resume. Select a compatible runtime when moving between operating
systems; BookOrder cannot make host-specific tools portable. `handoff --restore` restores frozen inputs.

```json
{
  "workflow": {
    "separated": true,
    "agents": {
      "writer": {"model": "your-model", "host": "your-host"},
      "designer": "your-design-agent",
      "reviewer": "your-review-agent"
    },
    "protected_sections": ["sec-locked"]
  },
  "page_feedback": {"enabled": true, "tolerance_ratio": 0.15, "tolerance_pages": 3, "max_rounds": 3}
}
```

Agent assignment values are opaque routing metadata. CLI `--agent ROLE=ASSIGNMENT` overrides configuration and
persists across resumes. Tasks expose `stage`, `role` and `agent` for the host to dispatch; no provider/model
names are hardcoded. Protected section IDs must identify Markdown headings; their text, including descendant
sections, is preserved during writer revisions.

Use `write --restart`, `design --restart` or `render --restart` to rerun a stage and its dependent stages. A
design restart retains completed writing. A render restart retains writing/design. No completed PDF alone
counts as publication completion.

# Page counts and revisions

`scale.chars_per_text_page` is an explicit profile override and takes precedence over the legacy effective
characters-per-page input. Without an override, new jobs estimate capacity from usable page dimensions, column
gutter, body font size and line height. Estimates guide initial character budgets; two columns do not double
usable page area. Resolved geometry/type changes invalidate rendering, without silently rewriting completed
manuscript contracts.

Every PDF build reads actual PDF page dictionaries (including front/back matter and blank pages), stores
`reports/page-count.json` and includes the count in `reports/build-report.json` and `execution-summary.json`.
`pages`, `status` and build output show target, actual count, signed difference and percentage. The bundled
Typst PDF format is supported without additional tools; other compressed PDF encodings require `pdfinfo`.
Failure to measure a generated PDF fails the build rather than inventing a count.

The default acceptable difference is the greater of three pages and 15% of the target. Larger deviations create
`plan/manuscript-revision-request.json` and return to the writer. The writer compresses redundant prose or adds
source-supported material, updates chapter budgets and summaries, then submits `done manuscript-revision`.
BookOrder adjusts character contracts from the measured ratio, reruns chapter/integration/citation/prose audits,
refreshes the handoff, and requires a new design/render pass. Protected sections and required topics remain
binding. Three submitted page revisions are allowed by default; unresolved deviations then block with a report.
`page_feedback.enabled: false` keeps measurement/reporting but disables automatic page-driven revision requests.

For any other necessary text change, the designer/reviewer runs:

```sh
bookorder revision request --reason "Explain what must change and why" --chapter ch-example
bookorder write
```

The designer does not edit canonical prose directly. Unauthorized changes stop later stages; restore the
snapshot or explicitly restart writing. Page feedback does not waive citation, source-role or factual checks.
Source roles remain `evidence`, `background`, `further_reading`, etc.; `guideline` is an authority value.
