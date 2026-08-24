from __future__ import annotations

import json
import re
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, request
from werkzeug.exceptions import HTTPException


APP_DIR = Path(__file__).resolve().parent
WORKSPACE = APP_DIR.parent
EDITABLE_SUFFIXES = {".ino", ".c", ".cpp", ".h", ".hpp"}
EDITABLE_ROOTS = (
    WORKSPACE / "Blink",
    WORKSPACE / "firmware",
    WORKSPACE / "projects",
    WORKSPACE / "reconstructed",
)
POWERSHELL = "powershell.exe"
CREATE_NO_WINDOW = 0x08000000

app = Flask(__name__, static_folder="static", static_url_path="")
jobs: dict[str, dict[str, Any]] = {}
job_processes: dict[str, subprocess.Popen[str]] = {}
jobs_lock = threading.Lock()


@app.errorhandler(HTTPException)
def handle_http_error(error: HTTPException) -> Any:
    return jsonify({"error": error.name, "description": error.description}), error.code


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative_source(path_value: str) -> tuple[Path, str]:
    candidate = (WORKSPACE / path_value).resolve()
    try:
        relative = candidate.relative_to(WORKSPACE)
    except ValueError:
        abort(400, "Path must remain inside the workspace")
    in_editable_root = any(candidate == root or root in candidate.parents for root in EDITABLE_ROOTS)
    if not in_editable_root or candidate.suffix.lower() not in EDITABLE_SUFFIXES:
        abort(400, "Only workspace C, C++, header, and Arduino source files are editable")
    return candidate, relative.as_posix()


def workspace_file(path_value: str, suffixes: set[str]) -> Path:
    candidate = (WORKSPACE / path_value).resolve()
    try:
        candidate.relative_to(WORKSPACE)
    except ValueError:
        abort(400, "Path must remain inside the workspace")
    if candidate.suffix.lower() not in suffixes or not candidate.is_file():
        abort(400, "File does not exist or has an unsupported type")
    return candidate


def powershell_script(script_name: str, command: str, arguments: list[str]) -> list[str]:
    return [
        POWERSHELL,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(WORKSPACE / script_name),
        command,
        *arguments,
    ]


def validate_port(value: Any) -> str | None:
    if value in (None, ""):
        return None
    port = str(value).upper()
    if not re.fullmatch(r"COM\d+", port):
        abort(400, "Port must use the COM<number> format")
    return port


def build_action(action: str, payload: dict[str, Any]) -> tuple[list[str], bool]:
    port = validate_port(payload.get("port"))
    destructive = False

    if action in {"arduino.doctor", "arduino.detect"}:
        return powershell_script("ArduinoTool.ps1", action.split(".")[1], []), False
    if action in {"arduino.compile", "arduino.upload"}:
        source, _ = relative_source(str(payload.get("path", "")))
        if source.suffix.lower() != ".ino":
            abort(400, "Arduino actions require an .ino source file")
        arguments = ["-Sketch", str(source.parent)]
        if port:
            arguments.extend(["-Port", port])
        destructive = action == "arduino.upload"
        return powershell_script("ArduinoTool.ps1", action.split(".")[1], arguments), destructive
    if action == "arduino.monitor":
        if not port:
            abort(400, "Serial monitor requires a port")
        baud_rate = int(payload.get("baudRate", 9600))
        if not 300 <= baud_rate <= 2_000_000:
            abort(400, "Baud rate is out of range")
        return powershell_script(
            "ArduinoTool.ps1", "monitor", ["-Port", port, "-BaudRate", str(baud_rate)]
        ), False
    if action in {"olimex.doctor", "olimex.signature", "olimex.backup"}:
        arguments = [] if not port else ["-Port", port]
        return powershell_script("OlimexProgrammer.ps1", action.split(".")[1], arguments), False
    if action == "olimex.decompile":
        image = workspace_file(str(payload.get("path", "")), {".hex"})
        return powershell_script("OlimexProgrammer.ps1", "decompile", ["-HexFile", str(image)]), False
    if action == "olimex.compile":
        source, _ = relative_source(str(payload.get("path", "")))
        if source.suffix.lower() not in {".c", ".cpp"}:
            abort(400, "Olimex compilation requires a C or C++ source file")
        arguments = ["-Source", str(source)]
        return powershell_script("OlimexProgrammer.ps1", "compile", arguments), False
    if action == "olimex.flash":
        image = workspace_file(str(payload.get("path", "")), {".hex"})
        arguments = ["-HexFile", str(image)]
        if port:
            arguments.extend(["-Port", port])
        destructive = True
        return powershell_script("OlimexProgrammer.ps1", "flash", arguments), destructive
    abort(400, f"Unknown action: {action}")


def run_job(job_id: str, command: list[str]) -> None:
    with jobs_lock:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["startedAt"] = utc_now()
    try:
        process = subprocess.Popen(
            command,
            cwd=WORKSPACE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
        with jobs_lock:
            job_processes[job_id] = process
        assert process.stdout is not None
        for line in iter(process.stdout.readline, ""):
            with jobs_lock:
                jobs[job_id]["output"] += line
        return_code = process.wait()
        with jobs_lock:
            jobs[job_id]["exitCode"] = return_code
            jobs[job_id]["status"] = "succeeded" if return_code == 0 else "failed"
    except Exception as error:  # noqa: BLE001
        with jobs_lock:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["output"] += f"\nServer error: {error}\n"
    finally:
        with jobs_lock:
            jobs[job_id]["finishedAt"] = utc_now()
            job_processes.pop(job_id, None)


@app.get("/")
def index() -> Any:
    return app.send_static_file("index.html")


@app.get("/api/capabilities")
def capabilities() -> Any:
    return jsonify(
        {
            "name": "AVR Workbench",
            "version": "0.1.0",
            "workspace": str(WORKSPACE),
            "actions": {
                "arduino": ["doctor", "detect", "compile", "upload", "monitor"],
                "olimex": ["doctor", "signature", "backup", "decompile", "compile", "flash"],
            },
            "hardwareProfiles": {
                "sparkfunRedBoard": {
                    "model": "SparkFun RedBoard (classic FTDI generation)",
                    "configuredFqbn": "arduino:avr:uno",
                    "mcu": "ATmega328P",
                    "logicVoltage": "5 V",
                    "clock": "16 MHz",
                    "detectedInterface": "FTDI FT231X-family USB bridge 0403:6015",
                    "verification": "user-identified RedBoard; USB bridge matches classic FTDI generation; SparkFun specifies Arduino Uno board selection",
                },
                "avrMt128": {
                    "model": "Olimex AVR-MT128",
                    "mcu": "ATmega128-16AI",
                    "logicVoltage": "5 V",
                    "clock": "16 MHz",
                    "signature": "0x1E9702",
                    "verification": "signature read successfully over ISP",
                },
                "avrIsp500Tiny": {
                    "model": "Olimex AVR-ISP500-TINY",
                    "usbId": "15BA:000C",
                    "protocol": "STK500v2",
                    "firmware": "2.10",
                    "targetPower": "senses target voltage; does not supply target power",
                    "verification": "USB identity and programmer handshake verified",
                },
                "ky024": {
                    "model": "KY-024 linear magnetic Hall sensor module",
                    "sensor": "49E/AH49E linear Hall element",
                    "comparator": "LM393",
                    "operatingVoltage": "3-5 V; manufacturer Arduino example uses 5 V",
                    "outputs": ["analog magnetic-field voltage", "adjustable digital threshold"],
                    "picturedPinOrder": "A0, GND, +V, D0 from left to right with sensor at top and header at bottom",
                    "verification": "Joy-IT SEN-KY024LM documentation; passive module is not USB-detectable",
                },
            },
            "safety": {
                "confirmationRequired": ["arduino.upload", "olimex.flash"],
                "fuseWritingSupported": False,
            },
            "endpoints": {
                "files": "GET /api/files",
                "file": "GET|PUT /api/file?path=<workspace-relative path>",
                "devices": "GET /api/devices",
                "startJob": "POST /api/jobs",
                "jobs": "GET /api/jobs",
                "job": "GET /api/jobs/<id>",
                "stopJob": "POST /api/jobs/<id>/stop",
            },
        }
    )


@app.get("/api/files")
def list_files() -> Any:
    files = []
    for root in EDITABLE_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in EDITABLE_SUFFIXES:
                files.append(path.relative_to(WORKSPACE).as_posix())
    return jsonify({"files": sorted(files)})


@app.route("/api/file", methods=["GET", "PUT"])
def source_file() -> Any:
    path, relative = relative_source(request.args.get("path", ""))
    if request.method == "GET":
        if not path.is_file():
            abort(404)
        return jsonify({"path": relative, "content": path.read_text(encoding="utf-8")})
    payload = request.get_json(force=True)
    content = payload.get("content")
    if not isinstance(content, str):
        abort(400, "content must be a string")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return jsonify({"path": relative, "saved": True, "bytes": len(content.encode("utf-8"))})


@app.get("/api/devices")
def devices() -> Any:
    command = (
        "Get-CimInstance Win32_PnPEntity | "
        "Where-Object { $_.Name -match '\\(COM\\d+\\)' } | "
        "Select-Object Name,Manufacturer,DeviceID,Status | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    if result.returncode != 0:
        return jsonify({"devices": [], "error": result.stderr.strip()}), 500
    parsed = json.loads(result.stdout or "[]")
    return jsonify({"devices": parsed if isinstance(parsed, list) else [parsed]})


@app.route("/api/jobs", methods=["GET", "POST"])
def job_collection() -> Any:
    if request.method == "GET":
        with jobs_lock:
            return jsonify({"jobs": list(reversed(list(jobs.values())))})

    payload = request.get_json(force=True)
    action = str(payload.get("action", ""))
    command, destructive = build_action(action, payload)
    if destructive and payload.get("confirmed") is not True:
        abort(409, "This action writes device memory; send confirmed=true")
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "action": action,
        "status": "queued",
        "output": "",
        "exitCode": None,
        "createdAt": utc_now(),
        "startedAt": None,
        "finishedAt": None,
    }
    with jobs_lock:
        jobs[job_id] = job
    threading.Thread(target=run_job, args=(job_id, command), daemon=True).start()
    return jsonify(job), 202


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str) -> Any:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            abort(404)
        return jsonify(job)


@app.post("/api/jobs/<job_id>/stop")
def stop_job(job_id: str) -> Any:
    with jobs_lock:
        process = job_processes.get(job_id)
        job = jobs.get(job_id)
    if not job:
        abort(404)
    if process and process.poll() is None:
        process.terminate()
        with jobs_lock:
            job["output"] += "\nStopped by user.\n"
            job["status"] = "stopped"
        return jsonify(job)
    return jsonify(job)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False, threaded=True)