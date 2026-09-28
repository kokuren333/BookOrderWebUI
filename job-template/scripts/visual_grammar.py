"""Renderer-independent component semantics and genre visual grammar.

The registry describes how an already planned device is presented. It never creates
devices, changes EditorialPlan counts, or overrides LayoutSpec geometry.
"""
import copy

from common import ROOT, write_yaml

SCHEMA = "bookorder/visual-grammar@1"
PRIORITIES = ("primary", "secondary", "tertiary", "supporting", "quiet")
TREATMENTS = ("filled-box", "side-rule", "top-rule", "inset-paragraph", "margin-label",
              "pull-quote", "plain-emphasis")
COMPONENTS = ("key_point", "warning", "definition", "glossary", "counterpoint",
              "case_study", "pull_quote", "checklist", "chapter_summary",
              "further_reading", "evidence_note", "source_note")
FIELDS = {"semantic_role", "priority", "placement", "span_preference", "break_behavior",
          "title_required", "icon_policy", "treatment", "border_policy", "fill_policy",
          "space_before_mm", "space_after_mm", "use_policy"}


def _component(role, priority, treatment, *, placement="after-anchor", span="inherit",
               break_behavior="keep-together", title=True, icon="none", border="semantic",
               fill="none", before=3, after=3, use="allowed"):
    return {"semantic_role": role, "priority": priority, "placement": placement,
            "span_preference": span, "break_behavior": break_behavior,
            "title_required": title, "icon_policy": icon, "treatment": treatment,
            "border_policy": border, "fill_policy": fill,
            "space_before_mm": before, "space_after_mm": after, "use_policy": use}


def defaults():
    return {
        "components": {
            "key_point": _component("synthesis", "secondary", "side-rule"),
            "warning": _component("risk", "primary", "filled-box", fill="surface"),
            "definition": _component("term-definition", "tertiary", "inset-paragraph"),
            "glossary": _component("terminology", "supporting", "margin-label", title=False),
            "counterpoint": _component("alternative-argument", "secondary", "top-rule", before=5, after=5),
            "case_study": _component("grounded-example", "secondary", "side-rule", before=5, after=5),
            "pull_quote": _component("editorial-emphasis", "primary", "pull-quote", title=False, before=6, after=6),
            "checklist": _component("action-verification", "secondary", "side-rule"),
            "chapter_summary": _component("chapter-synthesis", "secondary", "top-rule", placement="chapter-end"),
            "further_reading": _component("reading-navigation", "supporting", "plain-emphasis", placement="chapter-end"),
            "evidence_note": _component("evidence-context", "supporting", "inset-paragraph", title=False),
            "source_note": _component("attribution", "quiet", "plain-emphasis", placement="adjacent-to-figure",
                                      title=False, before=1, after=2),
        },
        "hierarchy": {"heading_2": "secondary", "heading_3": "tertiary", "caption": "supporting",
                      "source_note": "quiet"},
        "rhythm": {"pattern": "balanced", "interruption": "occasional", "section_space": "regular",
                   "box_budget": "avoid-adjacent-filled-boxes"},
        "table": {"border_density": "horizontal", "header_emphasis": "rule-and-weight",
                  "row_spacing": "regular", "numeric_alignment": "decimal", "zebra": False,
                  "source_note": "adjacent", "mode": "auto"},
        "diagram": {"node_shape": "rounded-rectangle", "edge_emphasis": "directional",
                    "hierarchy": "levels", "label_placement": "inside", "whitespace": "regular",
                    "annotation_style": "near-edge"},
        "chart": {"grid_intensity": "light", "axis_emphasis": "regular", "direct_labels": True,
                  "legend_use": "only-if-needed", "annotation": "outside-data", "baseline_emphasis": "regular",
                  "uncertainty": "label-or-interval"},
        "caption": {"figure_relationship": "adjacent", "weight": "supporting", "source_binding": "same-block"},
        "chapter_opener": {"hierarchy": "editorial", "lead": "quiet", "number_prominence": "large"},
    }


def validate(grammar):
    if set(grammar) != set(defaults()):
        raise ValueError("VisualGrammar sections must match the semantic registry")
    if set(grammar["components"]) != set(COMPONENTS):
        raise ValueError("VisualGrammar must define all canonical components")
    for name, component in grammar["components"].items():
        if set(component) != FIELDS: raise ValueError(f"VisualGrammar {name} has missing/unknown fields")
        if component["priority"] not in PRIORITIES: raise ValueError(f"VisualGrammar {name} priority invalid")
        if component["treatment"] not in TREATMENTS: raise ValueError(f"VisualGrammar {name} treatment invalid")
        if component["span_preference"] not in ("inherit", "local", "full-preferred"):
            raise ValueError(f"VisualGrammar {name} span preference invalid")
        if component["use_policy"] not in ("allowed", "deemphasize", "avoid"):
            raise ValueError(f"VisualGrammar {name} use policy invalid")
        if component["break_behavior"] not in ("keep-together", "allow-break", "keep-with-next"):
            raise ValueError(f"VisualGrammar {name} break behavior invalid")
        for key in ("space_before_mm", "space_after_mm"):
            component[key] = float(component[key])
            if not 0 <= component[key] <= 30: raise ValueError(f"VisualGrammar {name} {key} invalid")
    for section in ("hierarchy", "rhythm", "table", "diagram", "chart", "caption", "chapter_opener"):
        if set(grammar[section]) != set(defaults()[section]):
            raise ValueError(f"VisualGrammar {section} fields invalid")
    if grammar["rhythm"]["box_budget"] != "avoid-adjacent-filled-boxes":
        raise ValueError("VisualGrammar must prevent adjacent filled boxes")
    if not grammar["chart"]["direct_labels"] and grammar["chart"]["legend_use"] == "none":
        raise ValueError("Chart categories need labels or a legend")
    return grammar


def component(grammar, name):
    key = name.replace("-", "_")
    if key == "summary": key = "chapter_summary"
    if key == "glossary_term": key = "glossary"
    return grammar["components"].get(key)


def report(style, path=None):
    grammar = style["visual_grammar"]
    result = {"schema": SCHEMA, "style_id": style["id"], "genre": style["genre"],
              "components": copy.deepcopy(grammar["components"]),
              "hierarchy": grammar["hierarchy"], "rhythm": grammar["rhythm"],
              "table": grammar["table"], "diagram": grammar["diagram"],
              "chart": grammar["chart"], "caption": grammar["caption"],
              "chapter_opener": grammar["chapter_opener"],
              "note": "Presentation only; EditorialPlan device counts and LayoutSpec geometry are unchanged."}
    write_yaml(path or ROOT / "reports/style-grammar-report.yaml", result,
               "Resolved component presentation grammar; does not create editorial devices.")
    return result
