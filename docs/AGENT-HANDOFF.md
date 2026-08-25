# Agent environment handoff

This guide lets another coding agent recreate the Windows development environment for the AVR-MT128 player-piano repository. Run commands from the repository root in Windows PowerShell 5.1 unless a section says otherwise.

## Repository and ownership boundaries

```text
Repository: https://github.com/codenotes666-blip/avr-mt128-player-piano
Branch:     main
```

The MT128 firmware owner works in `projects/piano-hall-sensor/dallas_d0_display.c` and device documentation under `docs/`. The Pi client at `projects/piano-hall-sensor/pi/pianoctl.py` is owned separately. Do not edit, deploy, install, test, or SSH into the Pi client environment unless the user explicitly assigns that work. Communicate device-interface changes through [UART-PROTOCOL.md](UART-PROTOCOL.md).

Before and after MT128 work, prove the Pi client is untouched:

```powershell
git diff --exit-code -- .\projects\piano-hall-sensor\pi\pianoctl.py
```

## Verified host baseline

The current environment was recreated and checked with:

| Component | Verified version |
| --- | --- |
| OS | Windows 11 Pro, 64-bit, build 26200 |
| PowerShell | 5.1.26100.9168 |
| Python | CPython 3.12.10, 64-bit |
| Git | 2.53.0.windows.1 |
| GitHub CLI | 2.87.3 |
| Arduino CLI | 1.5.1, bundled with Arduino IDE |
| AVR-GCC | 7.3.0 |
| AVRDUDE | 6.3.0-arduino17 |

Newer compatible versions may work, but these are the known baseline. Install Git, Python 3.12, GitHub CLI, and Arduino IDE 2.x. Open Arduino IDE once and install Arduino AVR Boards so the packaged AVR tools exist beneath `%LOCALAPPDATA%\Arduino15\packages\arduino\tools`.

## Clone and inspect

```powershell
git clone https://github.com/codenotes666-blip/avr-mt128-player-piano.git
Set-Location .\avr-mt128-player-piano
git status --short
git log -1 --oneline
```

A fresh clone should have an empty `git status --short` result.

## Recreate `.venv`

`.venv` is machine-specific, intentionally ignored by Git, and must never be committed or copied between machines. Create it from the local Python installation:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r .\web-ide\requirements-lock.txt
```

Use the interpreter path directly in automation. This avoids PowerShell execution-policy issues around `Activate.ps1`. Interactive users may activate it instead:

```powershell
.\.venv\Scripts\Activate.ps1
```

If script execution is blocked, do not weaken machine-wide policy; continue with `.\.venv\Scripts\python.exe`.

`web-ide/requirements.txt` pins the three direct application dependencies. `web-ide/requirements-lock.txt` records the complete environment, including transitive packages, for exact recreation. Regenerate the lock only after an intentional dependency update:

```powershell
.\.venv\Scripts\python.exe -m pip freeze | Set-Content .\web-ide\requirements-lock.txt
```

Verify imports and isolation:

```powershell
.\.venv\Scripts\python.exe -c "import flask, fitz, PIL; print('environment ready')"
git check-ignore -v .\.venv\pyvenv.cfg
```

## Web workbench

Run the Flask application with the project interpreter:

```powershell
.\.venv\Scripts\python.exe .\web-ide\app.py
```

It binds only to `127.0.0.1:8765`, with debug mode disabled and threaded request handling enabled. Verify it from another PowerShell terminal:

```powershell
$response = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/
$response.StatusCode
```

Expected result: HTTP `200`. The controller guide is at `http://127.0.0.1:8765/projects/player-piano-controller.html`.

The PDF conversion packages are needed by `web-ide/generate_docs.py`. Generated pages under `web-ide/static/docs-html/` are ignored and can be rebuilt with:

```powershell
.\.venv\Scripts\python.exe .\web-ide\generate_docs.py
```

## AVR toolchain discovery

`OlimexProgrammer.ps1` discovers AVR-GCC and AVRDUDE from Arduino's package directory. It identifies the AVR-ISP500-TINY by USB ID `VID_15BA/PID_000C`, so COM numbers may change.

```powershell
.\OlimexProgrammer.ps1 doctor
```

The verified machine resolves:

```text
Programmer: Olimex AVR-ISP500-TINY, usually COM4
Protocol:   STK500v2
Target:     ATmega128 / m128
Clock:      16 MHz
ISP period: 10 microseconds
Signature:  0x1E9702
```

The programmer does not power the target. Connect ICSP, power the USB programmer first, then apply the MT128's separate power. Use the `ICSP` header, not `JTAG`.

## Build and flash MT128 firmware

Build is non-destructive and does not require connected hardware:

```powershell
.\OlimexProgrammer.ps1 compile `
  -Source .\projects\piano-hall-sensor\dallas_d0_display.c `
  -OutputDirectory .\build\player-piano
```

The expected image is `build/player-piano/dallas_d0_display.hex`. `build/` is ignored.

Before writing hardware:

```powershell
.\OlimexProgrammer.ps1 signature
```

Only continue when the signature is `0x1E9702` and communication is stable. Flashing erases and verifies program memory:

```powershell
.\OlimexProgrammer.ps1 flash `
  -HexFile .\build\player-piano\dallas_d0_display.hex
```

The verified high fuse is `0x09`, so `EESAVE` is not programmed. A chip erase clears EEPROM. Firmware then applies safe defaults: `AUTO RELEASE ON` and `DEBUG OFF`. The script intentionally provides no fuse-writing command.

## Current MT128 behavior

- UART: USART1, 115200 8N1, newline-terminated ASCII.
- Hall active: `STATUS HALL TRIP`; Hall inactive: `STATUS HALL CLEAR`.
- LCD pages: `MAIN`, `AUTO RELEASE`, and `DEBUG`.
- Left/right navigate; middle toggles a displayed Boolean.
- Debug defaults OFF. With debug ON and Hall clear, top latches relay ON.
- Bottom, Hall during debug, `RELAY_OFF`, or disabling debug releases the relay.
- Auto release defaults ON. With auto release OFF and debug OFF, Hall reports the trip but leaves externally engaged relay policy to the controller.
- `STATUS` emits relay, Hall, auto-release, and debug lines in that order, followed by `OK`.

Use [UART-PROTOCOL.md](UART-PROTOCOL.md) as the authoritative wire contract and [WIRING.md](WIRING.md) as the authoritative physical connection guide.

## Validation before commit

Run the narrow checks that apply:

```powershell
.\OlimexProgrammer.ps1 compile `
  -Source .\projects\piano-hall-sensor\dallas_d0_display.c `
  -OutputDirectory .\build\player-piano

.\.venv\Scripts\python.exe -m py_compile `
  .\web-ide\app.py `
  .\tools\avr_reconstruct.py

git diff --check
git diff --exit-code -- .\projects\piano-hall-sensor\pi\pianoctl.py
git status --short
```

Do not use Windows Python to execute `pianoctl.py`; it imports Linux-only `termios`. Syntax compilation is portable, but runtime testing belongs to the separately owned Pi environment.

## Ignored and generated state

Do not commit `.venv/`, `build/`, `__pycache__/`, flash backups, `reconstructed/`, downloaded `reference-source/`, or generated `web-ide/static/docs-html/`. Do not commit credentials, `.env` files, SSH material, or machine-specific COM-port assumptions.

## Commit and publish

After validation, stage only intended files, inspect them, then publish:

```powershell
git add <intended-files>
git diff --cached --check
git diff --cached --stat
git commit -m "Describe the change"
git push
git status --short
```

The final status should be empty, and local `HEAD` should match `origin/main`.