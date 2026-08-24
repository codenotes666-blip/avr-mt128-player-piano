# UART protocol

The controller uses USART1 at 115200 baud, 8 data bits, no parity, and 1 stop bit. Messages are ASCII lines terminated by LF; the firmware also accepts CR or CRLF.

## Commands

| Command | Behavior | Terminal response |
| --- | --- | --- |
| `BEEP` | Sound the onboard buzzer | `STATUS BEEP`, `OK` |
| `RELAY_ON` | Energize relay when Hall input is inactive | `STATUS RELAY ON`, `OK` |
| `RELAY_OFF` | Release relay and cancel play state | `STATUS RELAY OFF`, `OK` |
| `AUTO_RELEASE_ON` | Persist automatic Hall-trip relay release | `STATUS AUTO RELEASE ON`, `OK` |
| `AUTO_RELEASE_OFF` | Persist command-controlled relay release | `STATUS AUTO RELEASE OFF`, `OK` |
| `LCD <text>` | Replace the 32-character LCD screen | `STATUS LCD UPDATED`, `OK` |
| `PLAY [song]` | Energize relay and wait for Hall completion | `STATUS RELAY ON`, `STARTED`, then `COMPLETE` |
| `STATUS` | Report relay, Hall, and auto-release states | Three `STATUS ...` lines, then `OK` |

Commands longer than 39 characters return `ERROR COMMAND TOO LONG`. Unknown commands return `ERROR UNKNOWN COMMAND`. `RELAY_ON` and `PLAY` return `ERROR MAGNET ACTIVE` if the Hall input is already active.

The optional `song` argument is accepted for orchestration but is not interpreted by the current AVR firmware.

The auto-release setting is stored in MT128 EEPROM and survives power cycles. Erased or unrecognized EEPROM defaults to `AUTO_RELEASE_ON`. With auto release OFF, a Hall trip does not change the relay; the external controller must send `RELAY_OFF`. Reflashing may erase EEPROM depending on the ATmega128 fuse configuration, in which case the safe default applies again.

## Local LCD menu

The AVR-MT128 buttons configure the same EEPROM setting without a serial controller:

| Button | MCU input | Menu behavior |
| --- | --- | --- |
| Left | `PA1` | Previous page, wrapping through settings and the main screen |
| Middle | `PA2` | Toggle the Boolean option shown on a settings page |
| Right | `PA3` | Next page, wrapping through settings and the main screen |
| Down | `PA4` | Emergency relay release from any page |

The current pages are `MAIN` and `AUTO RELEASE`. On the `AUTO RELEASE` page, middle toggles `ON`/`OFF`, updates EEPROM immediately, redraws the LCD, and emits `STATUS AUTO RELEASE ON` or `STATUS AUTO RELEASE OFF`. The middle button no longer engages the relay. The up button is currently unused.

## Asynchronous messages

- `STATUS READY` after controller startup
- `STATUS HALL TRIP` when the held Hall state becomes active
- `STATUS HALL CLEAR` when the held Hall state clears
- `STATUS RELAY ON` and `STATUS RELAY OFF` when relay state changes
- `STATUS AUTO RELEASE ON` or `STATUS AUTO RELEASE OFF` after a local menu change
- `COMPLETE` when Hall activation ends an active `PLAY` operation

Consumers must tolerate status lines before the terminal response to a command.

## Pi CLI examples

```bash
pianoctl status
pianoctl monitor
pianoctl beep
pianoctl lcd "HI THERE"
pianoctl command STATUS
pianoctl relay-on
pianoctl relay-off
pianoctl play demo
```

To test the Pi UART independently, power down and disconnect the MT128, jumper Pi physical pins 8 and 10, then run:

```bash
pianoctl loopback
```

Remove the loopback jumper before restoring normal wiring.

## Verified bench sequence

1. Connect shared ground and the blue Pi TX to MT128 RX conductor only.
2. Send `BEEP`, then `LCD HI THERE`.
3. Power down and replace the blue conductor with the yellow MT128 TX path through its divider.
4. Start `pianoctl monitor`, reset the MT128, and confirm `STATUS READY`.
5. Power down and connect both directions for normal operation.

This direction-by-direction sequence distinguishes wiring errors from firmware and UART-ownership errors.