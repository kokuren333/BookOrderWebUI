"""Integration checks against the actual browser-generated template ZIP.

Run npm test first. Uses only stdlib; Pandoc/Typst are external prerequisites.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
PORTABLE = '--portable' in sys.argv
TEST_PARENT = ROOT / '.test-output' / 'portable test 日本語' if PORTABLE else ROOT / '.test-output'
WORK = TEST_PARENT / 'publishing-job'


def command(script, expected=0, *args):
    environment = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
    if PORTABLE:
        action = {'check_env.py': 'check', 'validate.py': 'source-check' if '--source-only' in args else 'validate', 'build.py': 'build', 'package.py': 'package'}[script]
        for key in ('PANDOC', 'TYPST', 'PYTHONHOME', 'PYTHONPATH'): environment.pop(key, None)
        environment.update(PORTABLE_TEST_LAUNCHER=str(WORK / 'run.cmd'), PORTABLE_TEST_ACTION=action,
                           PATH=os.environ['SystemRoot'] + '\\System32;' + os.environ['SystemRoot'])
        executable = [os.environ['SystemRoot'] + '\\System32\\WindowsPowerShell\\v1.0\\powershell.exe', '-NoProfile', '-Command', '& $env:PORTABLE_TEST_LAUNCHER $env:PORTABLE_TEST_ACTION; exit $LASTEXITCODE']
    else: executable = [sys.executable, str(WORK / 'scripts' / script), *args]
    result = subprocess.run(executable, cwd=WORK, capture_output=True, encoding='utf-8', env=environment)
    if result.returncode != expected:
        raise AssertionError(f"{script} expected {expected}, got {result.returncode}\n{result.stdout}\n{result.stderr}")
    return result


def write(relative, text):
    path = WORK / relative; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main():
    # This path is exclusively generated test output; verify it before removing a prior run.
    import shutil
    if not WORK.resolve().is_relative_to((ROOT / '.test-output').resolve()) or WORK.name != "publishing-job":
        raise RuntimeError("Unexpected integration-test workspace")
    if WORK.exists(): shutil.rmtree(WORK)
    with zipfile.ZipFile(ROOT / ('.test-output/portable-job.zip' if PORTABLE else '.test-output/generated-job.zip')) as archive: archive.extractall(TEST_PARENT)
    # A representative pipeline fixture, not a claim of completing a 50-page authored book.
    plan = {"chapters": [
        {"id": "ch-introduction", "title": "出版パイプライン", "file": "source/manuscript/01-introduction.md", "purpose": "Explain canonical source", "target_words": 300},
        {"id": "ch-publication", "title": "成果物の検証", "file": "source/manuscript/02-publication.md", "purpose": "Explain QA", "target_words": 300},
    ]}
    write("source/metadata/outline.yaml", json.dumps(plan, ensure_ascii=False))
    write("source/metadata/sources.yaml", json.dumps({"sources": [
        {"id": "source-001", "type": "pdf", "path": "input/sources/reference-1.pdf"},
        {"id": "source-002", "type": "pdf", "path": "input/sources/reference-2.pdf"},
        {"id": "source-003", "type": "markdown", "path": "input/sources/notes.md"},
        {"id": "source-004", "type": "web", "url": "https://pandoc.org/MANUAL.html"},
        {"id": "source-005", "type": "web", "url": "https://typst.app/docs/"},
    ]}))
    write("source/metadata/glossary.yaml", 'terms:\n  - canonical: canonical source\n    preferred: 正本\n')
    write("source/references/references.bib", '@online{pandoc,\n title = {Pandoc User’s Guide},\n author = {{Pandoc contributors}},\n url = {https://pandoc.org/MANUAL.html},\n urldate = {2026-09-27}\n}\n')
    figure = WORK / "source/assets/figures/pipeline.png"
    figure.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "tests/fixtures/pipeline.png", figure)
    write("source/metadata/figures.yaml", json.dumps({"figures": [{"id": "fig-pipeline", "chapter": "ch-introduction", "type": "diagram", "path": "source/assets/figures/pipeline.png", "caption": "Canonical source to publication"}]}))
    first = '''# 出版パイプライン {#ch-introduction}

正本は、読者向けの完成物を再生成するための編集可能な資料です。Pandocは文書変換を担当します [@pandoc]。

## 正本と変換 {#sec-canonical}

原稿は章ごとのMarkdownとして保存します。メタデータ、文献、図版を独立して維持することで、編集と出版を繰り返せます。[^source]

![Canonical source to publication](source/assets/figures/pipeline.png){#fig-pipeline}

| Layer | Purpose |
|:------|:--------|
| Source | Editable manuscript |
| Interchange | Word and DTP |
| Publication | Reader delivery |

Table: [Three publishing layers]{#tbl-layers}

> 正本からすべての出力を生成する。

```python
def build_book(source):
    return publish(source)
```

次の章の[検証方針](#sec-validation)も参照してください。

[^source]: 完成したPDFを正本の代わりにはしません。
'''
    second = '''# 成果物の検証 {#ch-publication}

## 検証方針 {#sec-validation}

構造検証と見た目の確認は別々に行います。[正本と変換](#sec-canonical)に戻って原稿を修正し、再ビルドします。[図](#fig-pipeline)と[表](#tbl-layers)も形式ごとに確認します。

### 完成プロジェクト {#sec-package}

章、資料、引用、図表、リンクの整合性を確認します。ウェブサイトには目次と前後章へのナビゲーション、ローカル検索を用意します。DOCXでは意味のあるスタイルを保ちます。

## 参考文献 {#sec-references}
'''
    write("source/manuscript/01-introduction.md", first)
    write("source/manuscript/02-publication.md", second)
    command("check_env.py")
    command("validate.py", 0, "--source-only")
    command("build.py")
    command("validate.py")
    # Confirm semantic styles exist and are actually applied to major paragraph categories.
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(WORK / "interchange/book.docx") as archive:
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        styles = ET.fromstring(archive.read("word/styles.xml"))
        style_names = {s.attrib[f'{{{ns["w"]}}}styleId']: s.find("w:name", ns).attrib[f'{{{ns["w"]}}}val'] for s in styles.findall("w:style", ns)}
        required = {"Book Title", "Chapter Title", "Section Heading", "Subsection Heading", "Body", "Block Quote", "Code Block", "Figure Caption", "Table Caption", "Bibliography"}
        assert required <= set(style_names.values()), required - set(style_names.values())
        document = ET.fromstring(archive.read("word/document.xml"))
        used = {style_names.get(p.attrib[f'{{{ns["w"]}}}val']) for p in document.findall(".//w:pStyle", ns)}
        assert required <= used, f"Unapplied styles: {required - used}"
    # Negative cases exercise independent failure conditions and restore canonical files.
    for suffix in ("\nTODO: unfinished\n", "\n[Broken](#missing-id)\n", "\n## Duplicate {#sec-validation}\n", "\n![Missing](source/assets/missing.png)\n", "\nUnknown claim [@nonexistent].\n"):
        write("source/manuscript/01-introduction.md", first + suffix)
        command("validate.py", 1, "--source-only")
    write("source/manuscript/01-introduction.md", first + "\nChanged after build.\n")
    command("validate.py", 1)
    command("package.py", 1)
    write("source/manuscript/01-introduction.md", first)
    command("validate.py")
    command("package.py", 1)  # QA inspection records are required.
    artifact = WORK / "publish/site/index.html"
    original_artifact = artifact.read_bytes()
    artifact.write_bytes(original_artifact + b"<!-- changed -->")
    command("validate.py", 1)
    artifact.write_bytes(original_artifact)
    command("validate.py")
    if PORTABLE:
        # Embeddable Python's fixed ._pth must not import the real book while previewing.
        preserved = {path: path.read_bytes() for path in [WORK / 'publish/book.pdf', *sorted((WORK / 'source/manuscript').glob('*.md'))]}
        environment = {**os.environ, 'PORTABLE_TEST_CLI': str(WORK / 'bookorder.cmd'), 'PYTHONIOENCODING': 'utf-8'}
        for key in ('PANDOC', 'TYPST', 'PYTHONHOME', 'PYTHONPATH'): environment.pop(key, None)
        environment['PATH'] = os.environ['SystemRoot'] + '\\System32;' + os.environ['SystemRoot']
        preview = subprocess.run([os.environ['SystemRoot'] + '\\System32\\WindowsPowerShell\\v1.0\\powershell.exe', '-NoProfile', '-Command', '& $env:PORTABLE_TEST_CLI theme preview modern-technical; exit $LASTEXITCODE'], cwd=WORK, capture_output=True, encoding='utf-8', env=environment)
        assert preview.returncode == 0, preview.stdout + preview.stderr
        assert (WORK / '.previews/modern-technical/publish/book.pdf').is_file()
        assert all(path.read_bytes() == data for path, data in preserved.items()), 'Preview overwrote the actual book'
    # Browser and PDF inspection happens separately; do not fabricate it here.
    print("PASS: all-format build, DOCX applied styles, source errors, freshness and QA packaging gates.")
    print(f"Inspect {WORK / 'publish'} and add actual review reports before packaging.")


if __name__ == "__main__": main()
