from __future__ import annotations

import html
import json
import re
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
SOURCE_DIR = STATIC_DIR / "docs"
OUTPUT_DIR = STATIC_DIR / "docs-html"

DOCUMENTS = [
  {
    "id": "ky-024-datasheet",
    "title": "KY-024 Linear Magnetic Hall Sensor Datasheet",
    "device": "KY-024",
    "category": "Datasheet",
    "source": "ky-024-datasheet.pdf",
  },
  {
    "id": "ky-024-manual",
    "title": "KY-024 Linear Magnetic Hall Sensor Manual",
    "device": "KY-024",
    "category": "Manual",
    "source": "ky-024-manual.pdf",
  },
  {
    "id": "sparkfun-redboard-v22-schematic",
    "title": "SparkFun RedBoard V22 Schematic",
    "device": "SparkFun RedBoard",
    "category": "Schematic",
    "source": "sparkfun-redboard-v22-schematic.pdf",
  },
    {
        "id": "arduino-uno-r3-pinout",
        "title": "Arduino Uno R3 Pinout",
        "device": "Arduino Uno R3",
        "category": "Pinout",
        "source": "arduino-uno-r3-pinout.pdf",
    },
    {
        "id": "arduino-uno-r3-schematic",
        "title": "Arduino Uno R3 Schematics",
        "device": "Arduino Uno R3",
        "category": "Schematic",
        "source": "arduino-uno-r3-schematic.pdf",
    },
    {
        "id": "arduino-uno-r3-datasheet",
        "title": "Arduino Uno R3 Datasheet",
        "device": "Arduino Uno R3",
        "category": "Datasheet",
        "source": "arduino-uno-r3-datasheet.pdf",
    },
    {
        "id": "olimex-avr-mt128-manual",
        "title": "Olimex AVR-MT128 User Manual",
        "device": "Olimex AVR-MT128",
        "category": "Manual",
        "source": "olimex-avr-mt128-manual.pdf",
    },
    {
        "id": "olimex-avr-mt128-schematic",
        "title": "Olimex AVR-MT128 Schematic",
        "device": "Olimex AVR-MT128",
        "category": "Schematic",
        "source": "olimex-avr-mt128-schematic.pdf",
    },
    {
        "id": "olimex-avr-isp500-tiny-manual",
        "title": "Olimex AVR-ISP500-TINY User Manual",
        "device": "Olimex AVR-ISP500-TINY",
        "category": "Manual",
        "source": "olimex-avr-isp500-tiny-manual.pdf",
    },
]


def page_html(document: dict[str, object], page_number: int, page_count: int, text: str) -> str:
    document_id = str(document["id"])
    title = str(document["title"])
    safe_text = html.escape(text)
    previous_page = max(1, page_number - 1)
    next_page = min(page_count, page_number + 1)
    return f"""<!doctype html>
<html lang="en" data-document="{document_id}" data-page="{page_number}" data-pages="{page_count}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} · Page {page_number}</title>
  <link rel="stylesheet" href="../../document-viewer.css">
</head>
<body>
  <header class="viewer-bar">
    <a class="back-link" href="/" title="Back to AVR Workbench">← <span>Workbench</span></a>
    <div class="document-identity"><strong>{html.escape(title)}</strong><span>{html.escape(str(document['device']))}</span></div>
    <div class="page-controls">
      <a href="page-{previous_page:03}.html" aria-label="Previous page">←</a>
      <label>Page <input id="pageNumber" type="number" min="1" max="{page_count}" value="{page_number}"> of {page_count}</label>
      <a href="page-{next_page:03}.html" aria-label="Next page">→</a>
    </div>
    <div class="viewer-actions">
      <button id="zoomOut" title="Zoom out">−</button>
      <output id="zoomValue">100%</output>
      <button id="zoomIn" title="Zoom in">+</button>
      <button id="fitPage" title="Fit page">Fit</button>
      <button id="toggleText" title="Toggle extracted text">Text</button>
    </div>
  </header>
  <main class="document-shell">
    <aside class="document-sidebar">
      <div class="search-box"><input id="documentSearch" type="search" placeholder="Search this document"><button id="searchButton">Search</button></div>
      <div id="searchResults" class="search-results"></div>
      <nav class="thumbnail-list" aria-label="Document pages" id="thumbnailList"></nav>
    </aside>
    <section class="page-stage" id="pageStage">
      <article class="rendered-page" id="renderedPage" data-hook="document-page">
        <img src="page-{page_number:03}.webp" alt="{html.escape(title)}, page {page_number}">
        <div class="annotation-layer" data-hook="annotations" aria-hidden="true"></div>
      </article>
    </section>
    <aside class="text-panel" id="textPanel">
      <div class="text-heading"><strong>Extracted text</strong><button id="copyText">Copy</button></div>
      <pre>{safe_text}</pre>
    </aside>
  </main>
  <script src="../../document-viewer.js"></script>
</body>
</html>
"""


def render_document(metadata: dict[str, str]) -> dict[str, object]:
    source_path = SOURCE_DIR / metadata["source"]
    output_path = OUTPUT_DIR / metadata["id"]
    output_path.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open(source_path)
    pages: list[dict[str, object]] = []

    for index, page in enumerate(document):
        page_number = index + 1
        text = page.get_text("text").strip()
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.7, 1.7), alpha=False)
        image = Image.open(BytesIO(pixmap.tobytes("png")))
        image_path = output_path / f"page-{page_number:03}.webp"
        image.save(image_path, "WEBP", quality=90, method=6)

        text_path = output_path / f"page-{page_number:03}.txt"
        text_path.write_text(text, encoding="utf-8", newline="\n")
        html_path = output_path / f"page-{page_number:03}.html"
        html_path.write_text(page_html(metadata, page_number, len(document), text), encoding="utf-8", newline="\n")

        summary = re.sub(r"\s+", " ", text)[:180]
        pages.append(
            {
                "number": page_number,
                "html": f"/docs-html/{metadata['id']}/page-{page_number:03}.html",
                "image": f"/docs-html/{metadata['id']}/page-{page_number:03}.webp",
                "text": f"/docs-html/{metadata['id']}/page-{page_number:03}.txt",
                "summary": summary,
            }
        )

    return {**metadata, "pageCount": len(document), "pages": pages}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"documents": [render_document(document) for document in DOCUMENTS]}
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8", newline="\n"
    )
    page_total = sum(int(document["pageCount"]) for document in manifest["documents"])
    print(f"Generated {page_total} HTML pages across {len(manifest['documents'])} documents.")


if __name__ == "__main__":
    main()