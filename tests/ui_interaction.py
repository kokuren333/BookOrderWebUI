"""WebUI interaction test (headless Chromium): Information Architecture of section 05 and a Basic-only job ZIP.

Bundles the real src/ with tools/ui-bundle.cjs (no vite needed), then drives it with Playwright.
Skips when Node, the `playwright` Python package or a Chromium build is unavailable.
Run: python tests/ui_interaction.py   (PLAYWRIGHT_CHROMIUM=/path/to/chromium to choose the browser)
"""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

REPO = Path(__file__).resolve().parent.parent
try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None
CHROMIUM = os.environ.get("PLAYWRIGHT_CHROMIUM") or next((p for p in ("/opt/pw-browsers/chromium",) if Path(p).exists()), None)


@unittest.skipUnless(shutil.which("node") and sync_playwright, "node and playwright are required")
class WebUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp(prefix="ui-"))
        subprocess.run(["node", "tools/ui-bundle.cjs", str(cls.out)], cwd=REPO, check=True, capture_output=True)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(**({"executable_path": CHROMIUM} if CHROMIUM else {}))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop(); shutil.rmtree(cls.out, ignore_errors=True)

    def open(self, advanced=True):
        page = self.browser.new_page(viewport={"width": 1200, "height": 1600}, accept_downloads=True)
        self.errors = []; page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto((self.out / "index.html").as_uri()); page.wait_for_selector("section.architecture")
        if advanced: page.get_by_role("tab", name="Advanced publishing").click(); page.wait_for_selector("section.publication")
        return page

    def summary(self, page):
        return dict(zip(page.locator(".summary-card dt").all_inner_texts(), page.locator(".summary-card dd").all_inner_texts()))

    def select(self, page, label, value):
        page.locator("section.publication label", has_text=label).locator("select").first.select_option(value)

    def tab(self, page, name):
        page.get_by_role("tab", name=name).click()

    def test_single_control_per_concept(self):
        page = self.open()
        seen = {}
        for name in ("Basic", "Geometry", "Typography", "Visual grammar", "Expert"):
            self.tab(page, name)
            labels = page.locator("section.publication .publication-form label").all_inner_texts()
            for label in labels:
                head = label.split("\n")[0].strip()
                if head: seen.setdefault(head, []).append(name)
        for concept in ("Page size", "Orientation", "Density", "Chapter opener", "Accent color", "Theme", "Genre", "Layout"):
            owners = [tabs for head, tabs in seen.items() if head.startswith(concept)]
            self.assertEqual(sum(len(t) for t in owners), 1, f"{concept}: {owners}")
        self.assertEqual(page.locator("section").filter(has_text="書籍のデザイン").count(), 0)  # old separate design section is gone
        self.assertEqual(page.locator("select", has_text="Automatic · Target scale").count(), 1)   # tier lives only in 01
        self.assertFalse(self.errors, self.errors)

    def test_preset_roundtrip_theme_change_and_basic_only_zip(self):
        page = self.open()
        page.locator("label.preset", has_text="Medical / Scientific").click()
        s = self.summary(page)
        self.assertTrue(s["Layout"].startswith("Medical / Scientific")); self.assertIn("Medical Textbook", s["Theme"])
        self.assertIn("PDF #116B78", s["Accent"]); self.assertIn("Web #2F7D68", s["Accent"])  # PDF accent from the style template
        self.assertIn("B5", page.locator(".summary-size").inner_text())
        # Basic -> Geometry (edit gutter) -> Typography -> Basic: values survive, preset shows the deviation.
        self.tab(page, "Geometry")
        gutter = page.locator("label", has_text="Gutter").locator("input"); gutter.fill("9")
        self.tab(page, "Typography"); self.tab(page, "Visual grammar"); self.tab(page, "Basic")
        self.tab(page, "Geometry"); self.assertEqual(page.locator("label", has_text="Gutter").locator("input").input_value(), "9"); self.tab(page, "Basic")
        self.assertIn("段間 9 mm", self.summary(page)["Columns"])
        self.assertIn("変更あり", page.locator("label.preset.selected").inner_text())
        # Changing the theme keeps the user's layout override.
        self.select(page, "Theme", "academic-jp")
        s = self.summary(page)
        self.assertIn("段間 9 mm", s["Columns"]); self.assertIn("Academic JP", s["Theme"]); self.assertIn("B5", page.locator(".summary-size").inner_text())
        # Basic-only job: required text, runtime none, generate.
        page.get_by_label("Book title").fill("UI test"); page.get_by_label("Book description / goal").fill("goal"); page.get_by_label("Target readers").fill("readers")
        page.locator("label", has_text="OS / CPU").locator("select").select_option("none")
        with page.expect_download() as info: page.get_by_role("button", name="Generate Publishing Job").click()
        data = Path(info.value.path()).read_bytes()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            project = json.loads(z.read("publishing-job/project.json")); design = json.loads(z.read("publishing-job/book.design.yaml"))
        self.assertEqual(project["layout_preset"], "medical-scientific")
        self.assertEqual(project["layout_spec"], {"body": {"gutter_mm": 9}})
        self.assertEqual((project["profile"], project["style_preset"]), ({"genre": "medical_science"}, "medical-evidence"))
        self.assertEqual((design["theme"], design["page"]["size"]), ("academic-jp", "B5"))
        self.assertFalse(self.errors, self.errors)

    def test_untouched_basic_generates_the_legacy_job(self):
        page = self.open()
        page.get_by_label("Book title").fill("Legacy"); page.get_by_label("Book description / goal").fill("goal"); page.get_by_label("Target readers").fill("readers")
        page.locator("label", has_text="OS / CPU").locator("select").select_option("none")
        with page.expect_download() as info: page.get_by_role("button", name="Generate Publishing Job").click()
        with zipfile.ZipFile(io.BytesIO(Path(info.value.path()).read_bytes())) as z:
            project = json.loads(z.read("publishing-job/project.json")); design = json.loads(z.read("publishing-job/book.design.yaml"))
        golden = json.loads((REPO / "tests/fixtures/webui-compat/default.json").read_text(encoding="utf-8"))
        for key in ("profile", "layout_preset", "layout_spec", "style_preset", "style_controls", "style_bible"): self.assertNotIn(key, project)
        golden["design"]["theme"] = design["theme"]
        self.assertEqual(design, golden["design"])
        self.assertEqual(project["book"]["target_pages"], 150)

    def instructions(self, page):
        return page.locator("label", has_text="Additional user instructions")

    def test_user_instructions_field_explains_precedence_and_is_saved_verbatim(self):
        text = ("教科書的にせず、批評性を残す。\n各章末にまとめを付けない。反論を毎回併記しない。\n"
                "<script>alert('x')</script> & \"quotes\" `code` **bold**\n" + "長い指示の本文。" * 400 + "\n  末尾の空白も保持  \n")
        for width in (1200, 390):
            page = self.open(); page.set_viewport_size({"width": width, "height": 1600})
            field = self.instructions(page)
            head = field.inner_text().split("\n")[0]
            self.assertIn("本全体への優先指示", head)
            area = field.locator("textarea")
            placeholder = area.get_attribute("placeholder")
            for words in ("文体", "説明の濃さ", "章構成", "扱う／扱わないテーマ", "事例", "図表", "教科書的にしない"): self.assertIn(words, placeholder)
            self.assertNotIn("TASK.md", placeholder)
            hint = " ".join(field.locator("small").all_inner_texts())
            for words in ("優先指示", "原文のまま", "各工程", "既定方針", "上書きしません", "引用", "最終レポート"): self.assertIn(words, hint)
            self.assertNotIn("補足・追加の制約", hint)
            box = area.bounding_box(); page_width = page.evaluate("document.documentElement.scrollWidth")
            self.assertLessEqual(box["x"] + box["width"], width, "textarea fits the viewport")
            self.assertLessEqual(page_width, width, "no horizontal scroll")
        area.fill(text)
        self.assertEqual(area.input_value(), text)
        self.assertEqual(page.locator("script", has_text="alert('x')").count(), 0, "the text is not injected as HTML")
        page.get_by_label("Book title").fill("Intent"); page.get_by_label("Book description / goal").fill("goal"); page.get_by_label("Target readers").fill("readers")
        page.locator("label", has_text="OS / CPU").locator("select").select_option("none")
        with page.expect_download() as info: page.get_by_role("button", name="Generate Publishing Job").click()
        with zipfile.ZipFile(io.BytesIO(Path(info.value.path()).read_bytes())) as z:
            project = json.loads(z.read("publishing-job/project.json")); task = z.read("publishing-job/TASK.md").decode("utf-8")
            self.assertIn("publishing-job/docs/user-intent.md", z.namelist())
        self.assertEqual(project["user_instructions"], text)
        self.assertIn("## Additional user instructions (verbatim)\n" + text + "\n", task)
        self.assertIn("Do not improve the book against the user's explicit intent", task)
        self.assertFalse(self.errors, self.errors)

    def test_empty_user_instructions_still_generate(self):
        page = self.open()
        self.assertEqual(self.instructions(page).locator("textarea").input_value(), "")
        page.get_by_label("Book title").fill("Empty"); page.get_by_label("Book description / goal").fill("goal"); page.get_by_label("Target readers").fill("readers")
        page.locator("label", has_text="OS / CPU").locator("select").select_option("none")
        with page.expect_download() as info: page.get_by_role("button", name="Generate Publishing Job").click()
        with zipfile.ZipFile(io.BytesIO(Path(info.value.path()).read_bytes())) as z:
            project = json.loads(z.read("publishing-job/project.json")); task = z.read("publishing-job/TASK.md").decode("utf-8")
        self.assertEqual(project["user_instructions"], "")
        self.assertIn("## Additional user instructions (verbatim)\n\n\n## Precedence of settings", task)
        self.assertFalse(self.errors, self.errors)

    def test_quick_mode_roles_and_signals(self):
        """Quick mode: only the essentials are visible; files get estimated, editable roles; explicit wishes are shown."""
        page = self.open(advanced=False)
        self.assertFalse(page.locator("section.publication").is_visible(), "format details wait for Advanced publishing")
        self.instructions(page).locator("textarea").fill("章末問題はいらない。ケースを多く。")
        signals = page.locator(".signals").inner_text()
        self.assertIn("章末問題はいらない", signals); self.assertIn("入れない", signals)
        page.set_input_files("input.file-picker", files=[{"name": "layout-sample.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4"},
                                                         {"name": "ward-flow.png", "mimeType": "image/png", "buffer": b"\x89PNG"},
                                                         {"name": "nurse-blog.md", "mimeType": "text/markdown", "buffer": b"# x"}])
        roles = [page.get_by_label(f"{name}の役割").input_value() for name in ("layout-sample.pdf", "ward-flow.png", "nurse-blog.md")]
        self.assertEqual(roles, ["layout_reference", "asset", "background"])
        self.assertEqual(page.locator(".badge", has_text="推定").count(), 3)
        page.get_by_label("nurse-blog.mdの役割").select_option("evidence")      # the user corrects an estimate
        self.assertEqual(page.locator(".badge", has_text="推定").count(), 2)
        page.get_by_label("Book title").fill("Roles"); page.get_by_label("Book description / goal").fill("goal"); page.get_by_label("Target readers").fill("readers")
        page.locator("label", has_text="OS / CPU").locator("select").select_option("none")
        with page.expect_download() as info: page.get_by_role("button", name="Generate Publishing Job").click()
        with zipfile.ZipFile(io.BytesIO(Path(info.value.path()).read_bytes())) as z:
            project = json.loads(z.read("publishing-job/project.json")); names = z.namelist()
        self.assertEqual(project["publication_architecture"], {"mode": "auto"})
        self.assertEqual([(s["path"], s["usage"]["role"], s["usage"]["role_origin"]) for s in project["input"]["sources"]], [("input/sources/nurse-blog.md", "evidence", "user")])
        self.assertEqual([a["usage"]["role"] for a in project["input"]["assets"]], ["layout_reference", "asset"])
        self.assertIn("publishing-job/input/assets/layout-sample.pdf", names)
        self.assertFalse(self.errors, self.errors)

    def test_advanced_architecture_and_bibliography_settings(self):
        page = self.open()
        section = page.locator("section.architecture")
        section.get_by_role("button", name="GUIDED", exact=True).click()
        section.locator("label", has_text="Publication type").locator("select").select_option("exam_preparation")
        section.locator("details", has_text="Block policy").locator("summary").click()
        page.get_by_label("コラムの方針").select_option("forbidden")
        page.locator("label", has_text="In-text citation").locator("select").select_option("note")
        page.locator("label", has_text="Footnote style").locator("select").select_option("numbered_reference")
        page.set_input_files("input.file-picker", files=[{"name": "diagram.png", "mimeType": "image/png", "buffer": b"\x89PNG"}])
        page.locator("label.chip", has_text="情報構造だけ再作図").locator("input").check()
        page.locator("details.file-details summary").click()
        page.locator("details.file-details label", has_text="使う章").locator("input").fill("第3章")
        page.locator("details.file-details label", has_text="このファイルへの指示").locator("textarea").fill("そのまま貼らず、情報構造だけ再作図する")
        page.get_by_label("Book title").fill("Advanced"); page.get_by_label("Book description / goal").fill("goal"); page.get_by_label("Target readers").fill("readers")
        page.locator("label", has_text="OS / CPU").locator("select").select_option("none")
        with page.expect_download() as info: page.get_by_role("button", name="Generate Publishing Job").click()
        with zipfile.ZipFile(io.BytesIO(Path(info.value.path()).read_bytes())) as z:
            project = json.loads(z.read("publishing-job/project.json"))
        self.assertEqual(project["publication_architecture"], {"mode": "guided", "archetype": "exam_preparation", "block_policy": {"forbidden": ["column"]}})
        self.assertEqual((project["citations"]["in_text_citation_style"], project["citations"]["footnote_style"], project["citations"]["bibliography_numbering"]),
                         ("note", "numbered_reference", "numbered"))
        usage = project["input"]["sources"][0]["usage"]
        self.assertEqual((usage["role"], usage["asset_role"], usage["intended_chapter"], usage["use_verbatim"], usage["redraw_allowed"]),
                         ("redraw_source", "redraw_source", "第3章", False, True))
        self.assertEqual(usage["notes"], "そのまま貼らず、情報構造だけ再作図する")
        self.assertFalse(self.errors, self.errors)

    def test_pasted_urls_expand_into_cards_with_bulk_edit(self):
        """Paste many URLs at once -> one card per URL with an estimated role -> bulk edit -> roles in project.json."""
        page = self.open()
        urls = ["https://www.mhlw.go.jp/stf/guideline.html", "https://note.com/nurse/n/abc", "https://example.org/report", "https://example.com/layout-sample", "https://example.org/recommended"]
        page.locator("label", has_text="Reference URLs").locator("textarea").fill("\n".join(urls))
        self.assertEqual(page.locator(".url-card").count(), 5)
        roles = [page.get_by_label(f"{u}の役割").input_value() for u in urls]
        self.assertEqual(roles, ["evidence", "background", "evidence", "layout_reference", "evidence"])
        self.assertEqual(page.locator(".url-card .badge", has_text="推定").count(), 5)
        for u in urls[1:3]: page.get_by_label(f"{u}を選択").check()
        page.get_by_label("一括：役割").select_option("background")
        page.get_by_label("一括：本文での引用").select_option("no")
        page.get_by_label("一括：使う章").fill("第3章")
        page.get_by_label("一括：用途").fill("現場の観点")
        page.get_by_role("button", name="選択したURLに適用").click()
        self.assertEqual(page.get_by_label(f"{urls[2]}の役割").input_value(), "background")
        self.assertEqual(page.locator(".url-card .badge", has_text="推定").count(), 2)
        page.get_by_label(f"{urls[4]}の役割").select_option("further_reading")
        card = page.locator(".url-card").nth(0)
        card.locator("details summary").click()
        card.locator("label", has_text="Authority").locator("select").select_option("governmental")
        page.get_by_label("Book title").fill("URLs"); page.get_by_label("Book description / goal").fill("goal"); page.get_by_label("Target readers").fill("readers")
        page.locator("label", has_text="OS / CPU").locator("select").select_option("none")
        with page.expect_download() as info: page.get_by_role("button", name="Generate Publishing Job").click()
        with zipfile.ZipFile(io.BytesIO(Path(info.value.path()).read_bytes())) as z:
            project = json.loads(z.read("publishing-job/project.json"))
        usage = project["input"]["url_usage"]
        self.assertEqual(project["input"]["urls"], urls[:3] + [urls[4]])
        self.assertEqual((usage[urls[0]]["role"], usage[urls[0]]["authority"], usage[urls[0]]["role_origin"]), ("evidence", "governmental", "user"))
        for u in urls[1:3]:
            self.assertEqual((usage[u]["role"], usage[u]["citation_allowed"], usage[u]["intended_chapter"], usage[u]["intended_usage"]), ("background", False, "第3章", "現場の観点"))
        self.assertEqual(usage[urls[4]]["role"], "further_reading")
        self.assertEqual([(a["url"], a["usage"]["role"]) for a in project["input"]["assets"]], [(urls[3], "layout_reference")])
        self.assertFalse(self.errors, self.errors)


if __name__ == "__main__": unittest.main()
