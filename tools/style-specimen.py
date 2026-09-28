"""Render paired StyleBible specimens with identical semantic content and LayoutSpec."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "job-template/scripts"))
import design
import layout_spec
import style_bible
import art_direction_qa
from common import write_yaml


def source(style, layout):
    p = style["palette"]; t = style["typography"]; ln = style["lines"]; sp = style["spacing"]
    grammar = style["visual_grammar"]
    comps = grammar["components"]
    treatments = {"key": comps["key_point"]["treatment"], "warning": comps["warning"]["treatment"],
                  "definition": comps["definition"]["treatment"], "counterpoint": comps["counterpoint"]["treatment"],
                  "pull_quote": comps["pull_quote"]["treatment"]}
    treatment_typst = ", ".join(f'"{key}": "{value}"' for key, value in treatments.items())
    table_row_pt = {"compact": 2.5, "regular": 4, "generous": 6}.get(grammar["table"]["row_spacing"], 4)
    table_rule = 0 if grammar["table"]["border_density"] == "minimal" else ln["hairline_pt"]
    node_radius = "0pt" if grammar["diagram"]["node_shape"] == "rectangle" else "8pt"
    chart_grid = grammar["chart"]["grid_intensity"] != "none"
    source_size = max(6.5, t["caption"]["size_pt"] * (.95 if grammar["components"]["source_note"]["priority"] == "supporting" else .85))
    source_gap = .5 if grammar["caption"]["figure_relationship"] == "tight" else 1.5
    chapter_size = (t["chapter_number"]["size_pt"] * (.55 if grammar["chapter_opener"]["number_prominence"] == "quiet" else .75
                    if grammar["chapter_opener"]["number_prominence"] == "medium" else 1))
    page = layout["page"]
    return f'''// Generated from StyleBible; page dimensions are from the shared LayoutSpec.
#set page(width: {page["width_mm"]}mm, height: {page["height_mm"]}mm,
  margin: (top: {page["margin_top_mm"]}mm, bottom: {page["margin_bottom_mm"]}mm,
    left: {page["margin_inner_mm"]}mm, right: {page["margin_outer_mm"]}mm))
#let ink = rgb("{p["ink"]}")
#let muted = rgb("{p["muted"]}")
#let accent = rgb("{p["accent"]}")
#let secondary = rgb("{p["secondary_accent"]}")
#let surface = rgb("{p["surface"]}")
#let warning = rgb("{p["warning"]}")
#let treatments = ({treatment_typst})
#set text(lang: "ja", font: "Noto Sans JP", size: {t["body"]["size_pt"]}pt, fill: ink)
#set par(justify: true, leading: 0.48em)
#let section(name) = block(above: {sp["section_gap_mm"]}mm, below: 2mm,
  text(size: {t["heading_2"]["size_pt"]}pt, weight: {t["heading_2"]["weight"]}, fill: secondary, name))
#let sub(name) = block(above: 3mm, below: 1mm,
  text(size: {t["heading_3"]["size_pt"]}pt, weight: {t["heading_3"]["weight"]}, fill: secondary, name))
#let cap(name) = block(above: {sp["caption_gap_mm"]}mm,
  text(size: {t["caption"]["size_pt"]}pt, fill: muted, name))
#let source-note(body) = block(above: {source_gap}mm,
  text(size: {source_size}pt, fill: muted, body))
#let box-note(kind, title, body) = {{
  let treatment = treatments.at(kind)
  let line-color = if kind == "warning" {{ warning }} else {{ secondary }}
  let contents = if kind == "pull_quote" {{ body }} else {{ [#text(weight: 700, fill: line-color, title) #h(.5em) #body] }}
  if treatment == "filled-box" {{
    block(width: 100%, above: 2mm, below: 2mm, inset: {sp["medium_mm"]}mm,
      fill: surface, stroke: (left: {ln["strong_pt"]}pt + line-color), breakable: false, contents)
  }} else if treatment == "side-rule" {{
    block(width: 100%, above: 3mm, below: 3mm, inset: (left: 3mm, y: 1mm),
      stroke: (left: {ln["normal_pt"]}pt + line-color), breakable: false, contents)
  }} else if treatment == "top-rule" {{
    block(width: 100%, above: 5mm, below: 5mm, inset: (top: 2mm),
      stroke: (top: {ln["normal_pt"]}pt + line-color), breakable: false, contents)
  }} else if treatment == "inset-paragraph" {{
    block(width: 100%, above: 4mm, below: 4mm, inset: (left: 5mm),
      text(style: "italic", contents))
  }} else if treatment == "pull-quote" {{
    block(width: 100%, above: 8mm, below: 8mm, inset: (x: 4mm, y: 2mm),
      stroke: (y: {ln["hairline_pt"]}pt + muted),
      align(center, text(size: {t["heading_3"]["size_pt"] + 1}pt, fill: secondary, contents)))
  }} else {{ block(width: 100%, above: 2mm, below: 2mm, contents) }}
}}
#let sample = [
  #section[比較条件を揃える]
  出版物の図表を評価するときは、表示領域と印刷寸法を先に固定する。色や線の選択は、同じ情報を異なる読者へ伝えるための編集判断である。本文と図表の役割を分け、近くに説明を置く。
  #sub[観察から主張へ]
  観察値は条件とともに示す。差が見えた場合でも、原因を断定する前に代替説明を確かめる。短い節見出しと適切な余白は、狭い段での読書を助ける。
  #box-note("key", "要点", [比較条件を揃え、図表と本文で異なる情報を担わせる。])
  #box-note("warning", "注意", [相関を因果関係として読まない。])
  #box-note("definition", "定義", [印刷寸法とは、PDFを実際の紙面に置いたときの大きさをいう。])
  #box-note("counterpoint", "反論", [同じ値でも、集め方が異なれば解釈は変わる。])
  #box-note("pull_quote", "引用", [測定値は、条件を離れて独り歩きしない。])
]
#v(6mm)
#text(size: {t["caption"]["size_pt"]}pt, fill: accent, weight: 700, "CHAPTER 02")
#v(2mm)
#text(size: {chapter_size}pt, fill: muted, "02")
#v(1mm)
#text(size: {t["heading_1"]["size_pt"]}pt, weight: 700, fill: ink, "証拠の見せ方")
#v(2mm)
#line(length: 100%, stroke: {ln["normal_pt"]}pt + secondary)
#v(4mm)
一つの議論を、本文・図・表・注意書きで支える。情報の順序と強弱をそろえ、読者が根拠へ戻れるようにする。#footnote[出典は各図表の直後にも記す。]
#section[一段本文と資料]
#sample
#v(3mm)
#table(columns: (1.1fr, 1fr, 1.5fr), inset: (x: 4pt, y: {table_row_pt}pt),
  stroke: (x, y) => if y == 0 {{ (bottom: {ln["strong_pt"]}pt + secondary) }} else if {table_rule}pt == 0pt {{ none }} else {{ (bottom: {table_rule}pt + muted) }},
  fill: (x, y) => if y == 0 {{ surface }} else {{ none }},
  [*資料*], [*条件*], [*読み取り*],
  [観察A], [同じ期間], [比較可能],
  [観察B], [異なる期間], [補正が必要])
#cap[表2.1　比較条件の整理]
#source-note[出典：架空の標本。]
#v(8mm)
#text(size: {t["heading_1"]["size_pt"]}pt, weight: 700, "二段本文と図版")
#v(2mm)
#line(length: 100%, stroke: {ln["normal_pt"]}pt + secondary)
#columns(2, gutter: {layout["body"]["gutter_mm"]}mm)[
  #sample
  #section[比較の図]
  #block(width: 100%, inset: 4mm, fill: surface, breakable: false)[
    #if {str(chart_grid).lower()} {{ line(length: 100%, stroke: {ln["hairline_pt"]}pt + muted) }}
    #text(size: {t["figure_label"]["size_pt"]}pt, fill: secondary, [観察A])
    #h(2mm) #rect(width: 23mm, height: 2.5mm, fill: accent)
    #linebreak()
    #text(size: {t["figure_label"]["size_pt"]}pt, fill: secondary, [観察B])
    #h(2mm) #rect(width: 15mm, height: 2.5mm, fill: muted)
  ]
  #cap[図2.1　値の比較。]
  #source-note[出典：架空の標本。]
  #section[推論の流れ]
  #block(width: 100%, inset: 3mm, fill: surface, breakable: false)[
    #box(stroke: {ln["normal_pt"]}pt + secondary, inset: 2mm, radius: {node_radius})[観察]
    #h(2mm) #text(fill: accent, [→]) #h(2mm)
    #box(stroke: {ln["normal_pt"]}pt + secondary, inset: 2mm, radius: {node_radius})[検証]
    #h(2mm) #text(fill: accent, [→]) #h(2mm)
    #box(stroke: {ln["normal_pt"]}pt + secondary, inset: 2mm, radius: {node_radius})[主張]
  ]
  #cap[図2.2　証拠から主張まで。]
  #source-note[出典：本書作成。]
]
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "publish")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    spec = design.load_design()
    project = {"book": {"language": "ja"}, "style_bible": {}}
    profile = {"genre": "medical_science", "art_direction": {}}
    layout = layout_spec.resolve(project, profile, spec, override={"body": {"columns": 2, "gutter_mm": 6}})
    typst = os.environ.get("TYPST") or "typst"
    comparison = {"schema": "bookorder/style-grammar-comparison@1", "layout_id": layout["id"], "genres": {}}
    resolved_styles = {}
    qa_reports = {}
    for genre in ("medical_science", "criticism"):
        profile["genre"] = genre
        style = style_bible.resolve(project, profile, spec)
        resolved_styles[genre] = style
        grammar = style["visual_grammar"]
        comparison["genres"][genre] = {
            "components": {name: {"treatment": item["treatment"], "priority": item["priority"]}
                           for name, item in grammar["components"].items()},
            "rhythm": grammar["rhythm"], "table": grammar["table"], "diagram": grammar["diagram"],
            "chart": grammar["chart"], "caption": grammar["caption"], "chapter_opener": grammar["chapter_opener"]}
        src = args.output_dir / f"style-specimen-{genre}.typ"
        pdf = src.with_suffix(".pdf")
        src.write_text(source(style, layout), encoding="utf-8")
        subprocess.run([typst, "compile", str(src), str(pdf)], check=True)
        tokens = style_bible.compile_tokens(style, layout, {"colors": {}, "typography": {}})
        qa = art_direction_qa.audit(style, tokens, pdf_path=pdf, root=args.output_dir)
        qa_reports[genre] = qa
        write_yaml(args.output_dir / f"art-direction-check-{genre}.yaml", qa,
                   "Style specimen QA: measured PDF vectors and resolved visual grammar.")
        if qa["summary"]["high"]:
            raise RuntimeError(f"{genre} specimen has {qa['summary']['high']} high art-direction findings")
        print(pdf)
    write_yaml(args.output_dir / "style-grammar-comparison.yaml", comparison,
               "Same semantic content and LayoutSpec; only StyleBible genre grammar differs.")
    cross = art_direction_qa.compare_genres(resolved_styles, qa_reports)
    write_yaml(args.output_dir / "art-direction-comparison-check.yaml", cross,
               "Cross-genre QA requires non-palette grammar differences.")
    if cross["summary"]["high"]: raise RuntimeError("Specimens differ mainly by palette")


if __name__ == "__main__": main()
