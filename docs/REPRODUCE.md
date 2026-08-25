# Recreate the development environment

This guide recreates the verified Windows-to-AVR and Raspberry-Pi-to-AVR workflow. COM port names and Linux device aliases may differ after reconnecting hardware.

## Hardware

- Olimex AVR-MT128 with ATmega128-16AI, powered from a suitable 12 VDC supply
- Olimex AVR-ISP500-TINY and its ICSP ribbon cable
- Raspberry Pi 5 with Debian/Raspberry Pi OS and GPIO access
- KY-024-compatible module whose digital device is an A3144-style Hall switch
- 1 kOhm and 2 kOhm resistors for the MT128 TX level divider
- Jumper wires and a common ground

Do not power the Pi from the MT128 TTL header. See [WIRING.md](WIRING.md) before connecting UART.

## Windows prerequisites

1. Install Git, Python 3.12 or later, and Arduino IDE 2.x.
2. Open Arduino IDE once and install the Arduino AVR Boards package. The verified package supplied AVR-GCC 7.3 and AVRDUDE 6.3.
3. Clone this repository and enter it in PowerShell.

```powershell
git clone https://github.com/codenotes666-blip/avr-mt128-player-piano.git
Set-Location .\avr-mt128-player-piano
```

The scripts discover Arduino's packaged tools beneath `%LOCALAPPDATA%\Arduino15` and the IDE install directory. No global AVR toolchain path is required.

## Verify and build the AVR firmware

The AVR-ISP500-TINY does not power the target. Connect the ICSP ribbon, power the programmer from USB first, and then power the AVR-MT128 separately.

```powershell
.\OlimexProgrammer.ps1 doctor
.\OlimexProgrammer.ps1 signature
.\OlimexProgrammer.ps1 compile -Source .\projects\piano-hall-sensor\dallas_d0_display.c -OutputDirectory .\build\player-piano
```

A successful signature is `0x1E9702`. Do not flash until repeated signature reads work reliably.

Back up the installed firmware before the first write, then flash the newly built image:

```powershell
.\OlimexProgrammer.ps1 backup
.\OlimexProgrammer.ps1 flash -HexFile .\build\player-piano\dallas_d0_display.hex
```

The script intentionally has no fuse-writing command. Incorrect fuse values can remove the target clock or disable ISP access.

## Configure Raspberry Pi UART

On Raspberry Pi OS, use `raspi-config` to disable the serial login shell and enable the serial hardware. The equivalent boot configuration must include UART enablement:

```text
enable_uart=1
```

Reboot, then verify that the stable alias resolves to a hardware UART:

```bash
readlink -f /dev/serial0
ls -l /dev/serial0
```

The verified Pi 5 resolved `/dev/serial0` to `/dev/ttyAMA0`. Add the controlling user to the serial-access group if needed, then sign out and back in:

```bash
sudo usermod -aG dialout "$USER"
```

Install the dependency-free CLI:

```bash
sudo install -m 0755 projects/piano-hall-sensor/pi/pianoctl.py /usr/local/bin/pianoctl
pianoctl status
```

Wire only after both boards are powered down. Follow [WIRING.md](WIRING.md), then test one direction at a time using [UART-PROTOCOL.md](UART-PROTOCOL.md).

## Run the web workbench

Create an isolated Python environment on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r .\web-ide\requirements-lock.txt
.\.venv\Scripts\python.exe .\web-ide\app.py
```

Open `http://127.0.0.1:8765/projects/player-piano-controller.html`. The server binds to localhost and exposes compile/flash operations through a fixed action registry; flash actions require explicit confirmation.

The `.venv` directory is ignored and must be recreated rather than committed or copied. `requirements.txt` pins direct dependencies; `requirements-lock.txt` pins the complete verified environment. See [AGENT-HANDOFF.md](AGENT-HANDOFF.md) for a clean-room agent workflow, exact baseline versions, validation commands, generated paths, and ownership boundaries.

## Verification checklist

1. `signature` reports ATmega128 signature `0x1E9702`.
2. Firmware compiles without warnings or errors.
3. On reset, `pianoctl monitor` receives `STATUS READY`.
4. `pianoctl beep` sounds the onboard buzzer and ends with `OK`.
5. `pianoctl lcd "HI THERE"` updates the LCD and ends with `OK`.
6. With the piano mechanism isolated, test `relay-on` and `relay-off` while observing the onboard relay.
7. Test `play` only after confirming the Hall switch forces the relay off and produces `COMPLETE`.

Items 1 through 5 represent the core bench workflow. Relay and full `PLAY` behavior require a deliberate live regression test for each installation.

## Troubleshooting

- AVR signature timeout: leave programmer USB powered, cycle target power, confirm the cable is on `ICSP`, then retry with `-BitClockMicroseconds 250`.
- No Pi UART device: confirm the serial console is disabled, UART is enabled, and the Pi has rebooted.
- Pi receives nothing: check the MT128 yellow TX conductor, divider midpoint, Pi physical pin 10, and common ground.
- MT128 receives nothing: check Pi physical pin 8 to the MT128 blue RX conductor.
- LCD fails only after cold start: retain the firmware's conservative 2 ms LCD write timing.