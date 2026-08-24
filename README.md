# AVR-MT128 Player Piano Controller

This repository contains the complete hardware and software environment developed for an AVR-MT128 player-piano controller. An ATmega128 watches a digital Hall endpoint, controls the piano relay, drives the onboard LCD and buzzer, and exchanges newline-delimited commands with a Raspberry Pi 5 over a protected 115200-baud TTL UART link.

It also retains the supporting AVR programming tools, diagnostic firmware, hardware web workbench, and earlier Hall-sensor experiments used to reach the verified design.

## Verified state

- AVR-MT128 firmware builds for an ATmega128 at 16 MHz and flashes through an Olimex AVR-ISP500-TINY.
- Raspberry Pi 5 UART is `/dev/serial0` at 115200 8N1 with the serial console disabled.
- Pi-to-MT128 commands `BEEP` and `LCD HI THERE` have been verified on hardware.
- MT128-to-Pi startup message `STATUS READY` has been verified on hardware.
- Relay and `PLAY` command paths are implemented; perform the live safety checklist before connecting the piano mechanism.

## Start here

1. Follow [docs/REPRODUCE.md](docs/REPRODUCE.md) to install the Windows AVR toolchain, build and flash the controller, configure the Pi, and start the web guide.
2. Wire the boards exactly as shown in [docs/WIRING.md](docs/WIRING.md). The MT128 transmits 5 V logic, so its TX path must use the documented divider before reaching the Pi.
3. Use [docs/UART-PROTOCOL.md](docs/UART-PROTOCOL.md) for commands, responses, and test order.

The active firmware is `projects/piano-hall-sensor/dallas_d0_display.c`; the historical filename is retained to preserve the development trail. The Pi client is `projects/piano-hall-sensor/pi/pianoctl.py`.

## Repository layout

| Path | Purpose |
| --- | --- |
| `projects/piano-hall-sensor/` | Active controller, Pi CLI, and earlier sensor diagnostics |
| `OlimexProgrammer.ps1` | ATmega128 discovery, build, backup, and flash wrapper |
| `web-ide/` | Flask hardware workbench and complete graphical build guide |
| `firmware/` | Minimal ATmega128 smoke-test firmware |
| `tools/` | Offline AVR firmware analysis tooling |
| `ArduinoTool.ps1`, `Blink/` | Supporting SparkFun RedBoard workflow |
| `docs/` | Reproduction, wiring, and protocol documentation |

## Supporting toolset

Both programming scripts locate tools bundled with Arduino IDE, so no global `PATH` changes are required. The hardware reference also covers the KY-024 Hall module and the earlier analog experiments.

## Connected hardware

- SparkFun RedBoard (classic FTDI generation): currently `COM3` (`VID_0403`, `PID_6015`, FT231X-family bridge). It uses an ATmega328P at 5 V and 16 MHz. SparkFun specifies selecting Arduino Uno, so the tool uses `arduino:avr:uno`. Arduino CLI reports the generic FTDI USB bridge as unknown because it does not carry Arduino's official USB IDs.
- Olimex AVR-ISP500-TINY: currently `COM4` (`VID_15BA`, `PID_000C`), verified STK500v2 protocol and firmware 2.10.
- Olimex target: AVR-MT128 with ATmega128, signature `0x1E9702`.

COM numbers can change after reconnecting USB devices. `OlimexProgrammer.ps1` normally finds its programmer from the stable Olimex USB hardware ID. Specify the RedBoard port explicitly when more than one serial device is connected.

## SparkFun RedBoard commands

Run these from PowerShell in this directory:

```powershell
.\ArduinoTool.ps1 doctor
.\ArduinoTool.ps1 detect
.\ArduinoTool.ps1 compile -Sketch .\Blink
.\ArduinoTool.ps1 upload -Sketch .\Blink -Port COM3
.\ArduinoTool.ps1 monitor -Port COM3 -BaudRate 9600
```

The default board profile is `arduino:avr:uno`, as required by SparkFun's RedBoard guide. `compile` is non-destructive. `upload` compiles and writes through the RedBoard bootloader. Close every serial monitor before uploading because only one program can own the COM port.

For another supported board, pass its fully qualified board name:

```powershell
.\ArduinoTool.ps1 compile -Sketch .\MySketch -Board arduino:avr:nano
```

List installed board definitions with:

```powershell
& 'C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe' board listall
```

## AVR-MT128 through Olimex ISP

The custom workflow targets the soldered ATmega128-16AI directly through the board header marked `ICSP`, not `JTAG`. The board runs at 5 V and 16 MHz and provides 128 KB flash, 4 KB EEPROM, and 4 KB SRAM. It uses AVRDUDE with `stk500v2` and AVR-GCC with `-mmcu=atmega128`.

### Required power sequence

The AVR-ISP500-TINY does not power the target. This exact sequence was verified on the attached hardware:

1. Connect the ribbon between the programmer and the AVR-MT128 `ICSP` header.
2. Connect USB and power the Olimex programmer first.
3. Apply separate power to the AVR-MT128 second.
4. Run `signature` before any backup or flash command.

Powering the target while the programmer is unpowered prevented reliable startup in this setup. A successful check reports approximately `4.6 V` and signature `0x1E9702`.

### Commands

```powershell
.\OlimexProgrammer.ps1 doctor
.\OlimexProgrammer.ps1 signature
.\OlimexProgrammer.ps1 backup
.\OlimexProgrammer.ps1 decompile
.\OlimexProgrammer.ps1 compile -Source .\firmware\atmega128_smoke.c
.\OlimexProgrammer.ps1 flash -HexFile .\build\atmega128\atmega128_smoke.hex
```

Command behavior:

- `doctor`: locates the programmer, compiler, uploader, and target settings without contacting the MCU.
- `signature`: reads identification and fuse values without modifying them.
- `backup`: reads existing flash into `build\atmega128\atmega128-flash-backup.hex`.
- `decompile`: reconstructs readable behavioral C, exact disassembly, and a JSON report from a HEX image without contacting the target. Recognized factory firmware includes named LCD, UART, button, relay, buzzer, Dallas, and timer routines.
- `compile`: builds a C source file into ELF and Intel HEX files without contacting the target.
- `flash`: erases and writes ATmega128 flash; AVRDUDE verifies the result.

The script deliberately has no fuse-writing command. Incorrect fuses can disable the target clock or ISP access.

### Safe programming workflow

```powershell
.\OlimexProgrammer.ps1 signature
.\OlimexProgrammer.ps1 backup
.\OlimexProgrammer.ps1 compile -Source .\firmware\atmega128_smoke.c
.\OlimexProgrammer.ps1 flash -HexFile .\build\atmega128\atmega128_smoke.hex
```

The default explicit ISP bit clock is `10` microseconds. For an unusually slow target clock, retry a read-only signature check with a slower value:

```powershell
.\OlimexProgrammer.ps1 signature -BitClockMicroseconds 250
```

If `signature` times out:

1. Remove target power, leave the programmer USB-powered, then reapply target power.
2. Confirm the cable is on `ICSP`, not the adjacent `JTAG` header.
3. Retry `signature` with `-BitClockMicroseconds 250`.
4. Do not use `flash` until `signature` succeeds consistently.

## Installed tool locations

- Arduino CLI: `C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe`
- Arduino AVR core: `%LOCALAPPDATA%\Arduino15\packages\arduino\hardware\avr\1.8.6`
- AVR-GCC: Arduino package `avr-gcc\7.3.0-atmel3.6.1-arduino7`
- AVRDUDE: Arduino package `avrdude\6.3.0-arduino17`

The scripts discover these paths dynamically where practical. Installed package versions may be updated by Arduino IDE.

## Web development environment

The Flask-based AVR Workbench provides a highlighted C/C++ editor, live device inventory, compile/program controls, job monitoring, agent-facing HTTP endpoints, and offline official hardware documentation rendered as searchable HTML pages.

```powershell
python -m pip install -r .\web-ide\requirements.txt
python .\web-ide\app.py
```

Open `http://127.0.0.1:8765`. See `web-ide\README.md` and `web-ide\static\API.md` for server and endpoint details.

## Project guides

- Current controller: `http://127.0.0.1:8765/projects/player-piano-controller.html`
- Earlier Hall-sensor exploration: `http://127.0.0.1:8765/projects/piano-hall-sensor.html`
- Active source: `projects\piano-hall-sensor\dallas_d0_display.c`
- Earlier ADC source: `projects\piano-hall-sensor\piano_hall_sensor.c`

The current controller uses the KY-024 digital output on `PD5`, not the earlier analog `ADC0/PF0` path. The Pi and MT128 share ground but do not power one another.