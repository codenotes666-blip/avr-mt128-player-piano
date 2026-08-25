# AVR Workbench web IDE

## Start

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\web-ide\requirements-lock.txt
.\.venv\Scripts\python.exe .\web-ide\app.py
```

Open `http://127.0.0.1:8765`.

The ignored `.venv` is local build state. Recreate it from `requirements-lock.txt`; do not commit or copy it between machines. The shorter `requirements.txt` contains only direct dependencies.

The server binds only to localhost. It wraps the workspace's `ArduinoTool.ps1` and `OlimexProgrammer.ps1` scripts through a fixed action registry. Upload and flash requests require explicit confirmation. Source reads and writes are confined to supported files inside the workspace.

The first target is a classic SparkFun RedBoard using an FTDI `0403:6015` bridge. SparkFun specifies the Arduino Uno board selection, so the server compiles it with `arduino:avr:uno`; Arduino CLI reports the generic FTDI interface as unknown rather than naming the board. The Olimex programmer is independently identified by `15BA:000C`.

For the AVR-MT128, connect ICSP and power the AVR-ISP500-TINY first, then apply target power. Confirm `olimex.signature` succeeds before using `olimex.flash`.

The MT128 **Reconstruct** action analyzes the saved flash backup without contacting the device. Recognized factory firmware produces readable behavioral AVR-GCC C with LCD, UART, buttons, relay, buzzer, Dallas input, and timer logic. Exact disassembly and a JSON report are also written under `reconstructed\atmega128`.

See [static/API.md](static/API.md) for the agent-facing API.

## HTML hardware documents

Official PDFs in `static\docs` are conversion sources only. Every page is rendered as an individual HTML page with a high-resolution image, extracted text, document search, thumbnails, zoom, keyboard navigation, and an annotation-layer hook.

Regenerate all document pages after replacing a source PDF:

```powershell
python .\web-ide\generate_docs.py
```

The generated index is `static\docs-html\manifest.json`. Viewer extensions can listen for the `avr-document-ready` browser event and use `window.AVRDocument.annotationLayer` without changing generated pages.

The AVR-MT128 also has a dedicated rear connector reference at `/pinouts/avr-mt128.html`, built from the official component-side photograph and the manual's connector tables.

The companion `/descriptions/avr-mt128.html` page inventories onboard hardware and external interfaces, including MCU connections and explicit clarification where a connector does not include a fitted sensor.

The KY-024 profile at `/descriptions/ky-024.html` includes its official image/pinout, operating behavior, RedBoard and AVR-MT128 wiring, sample code, and locally rendered manufacturer manual/datasheet.

The Projects section currently includes `/projects/piano-hall-sensor.html`, a complete AVR-MT128 + KY-024 circuit, schematic, voltage analysis, staged wiring procedure, calibration, and compilable firmware.