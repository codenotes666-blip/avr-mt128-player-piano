# AVR Workbench API

Base URL: `http://127.0.0.1:8765`

## Discovery

- `GET /api/capabilities` returns actions, audited hardware profiles, verification status, endpoints, and safety constraints.

Passive peripherals such as the KY-024 appear under `hardwareProfiles` but cannot be automatically detected over USB.
- `GET /api/devices` returns current Windows serial devices and hardware IDs.
- `GET /api/files` returns editable C, C++, header, and Arduino source files.

## Source files

Read a source file:

```http
GET /api/file?path=Blink%2FBlink.ino
```

Save a source file:

```http
PUT /api/file?path=Blink%2FBlink.ino
Content-Type: application/json

{"content":"void setup() {}\nvoid loop() {}\n"}
```

Paths are workspace-relative and restricted to `.ino`, `.c`, `.cpp`, `.h`, and `.hpp` files. Paths cannot escape the workspace or modify the web server.

## Jobs

Start a job with `POST /api/jobs`. Supported actions:

| Action | Required fields | Writes device memory |
| --- | --- | --- |
| `arduino.doctor` | none | No |
| `arduino.detect` | none | No |
| `arduino.compile` | `path` to `.ino` | No |
| `arduino.upload` | `path`, `port`, `confirmed: true` | Yes |
| `arduino.monitor` | `port`, optional `baudRate` | No |
| `olimex.doctor` | optional `port` | No |
| `olimex.signature` | optional `port` | No |
| `olimex.backup` | optional `port` | No |
| `olimex.decompile` | `path` to `.hex` | No |
| `olimex.compile` | `path` to `.c` or `.cpp` | No |
| `olimex.flash` | `path` to `.hex`, optional `port`, `confirmed: true` | Yes |

Example:

```json
{
  "action": "olimex.signature",
  "port": "COM4"
}
```

The server returns HTTP `202` and a job object. Poll `GET /api/jobs/<id>` for status and output. Stop a running monitor with `POST /api/jobs/<id>/stop`.

There is intentionally no arbitrary command endpoint and no fuse-writing action.

`olimex.decompile` fingerprints known firmware and produces behavioral AVR-GCC C, exact AVR disassembly, and a JSON report. The MT128 factory-test firmware is recognized from its recovered strings and matched to Olimex's published source behavior. The generated C is readable and compilable but is not guaranteed to reproduce the original binary byte-for-byte.