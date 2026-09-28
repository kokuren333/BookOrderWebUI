"""Read-only check of a project's publication request (tier/genre, layout, style) through the real resolvers.

The WebUI writes its choices into project.json (`profile`, `layout_preset`, `layout_spec`, `style_preset`,
`style_controls`). This module resolves them with publication_profile / layout_spec / style_bible exactly as the
orchestrator will, and reports field-level issues instead of a traceback. It writes nothing:
plan/profile.resolved.yaml, plan/layout-spec.yaml and plan/style-bible.yaml are still produced by the orchestrator.
"""
import layout_spec
import publication_profile
import style_bible

SCHEMA = "bookorder/publication-check@1"


def check(project, design=None):
    design = design or {}; issues = []; result = {}
    profile = None
    try:
        profile = publication_profile.resolve(project, design)
        result["profile"] = {"id": profile["id"], "tier": profile["tier"], "genre": profile["genre"],
                             "target_pages": profile["scale"]["target_pages"],
                             "chars_per_text_page": profile["scale"]["chars_per_text_page"],
                             "page_size": profile["scale"]["page_size"]}
    except ValueError as error:
        issues.append({"code": "profile_invalid", "field": "profile", "message": str(error)})
    try:
        spec = layout_spec.resolve(project, profile or {"genre": "general"}, design)
        result["layout"] = layout_spec.summary(spec)
        if (project.get("outputs") or {}).get("pdf", True): issues += layout_spec.renderer_issues(spec)
    except layout_spec.LayoutSpecError as error:
        issues += error.issues
    except ValueError as error:
        issues.append({"code": "layout_invalid", "field": "layout_spec", "message": str(error)})
    try:
        style = style_bible.resolve(project, profile or {"genre": "general"}, design)
        result["style"] = {"genre": style["genre"], "preset": style.get("preset"),
                           "template": style_bible.template_genre(project, profile or {}),
                           "controls": project.get("style_controls") or {}}
    except ValueError as error:
        issues.append({"code": "style_invalid", "field": "style_preset", "message": str(error)})
    return {"schema": SCHEMA, "ok": not issues, **result, "issues": issues}
