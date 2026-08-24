from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


INSTRUCTION_PATTERN = re.compile(
    r"^\s*([0-9a-fA-F]+):\s+((?:[0-9a-fA-F]{2}\s+)+)\s*([a-zA-Z.]+)\s*(.*?)\s*$"
)
TARGET_PATTERN = re.compile(r"(?:0x)?([0-9a-fA-F]+)")


def parse_intel_hex(path: Path) -> dict[int, int]:
    memory: dict[int, int] = {}
    base_address = 0
    for line_number, raw_line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise ValueError(f"Line {line_number} is not Intel HEX")
        record = bytes.fromhex(line[1:])
        length = record[0]
        address = int.from_bytes(record[1:3], "big")
        record_type = record[3]
        data = record[4 : 4 + length]
        if sum(record) & 0xFF:
            raise ValueError(f"Line {line_number} has an invalid checksum")
        if record_type == 0x00:
            for offset, value in enumerate(data):
                memory[base_address + address + offset] = value
        elif record_type == 0x01:
            break
        elif record_type == 0x02:
            base_address = int.from_bytes(data, "big") << 4
        elif record_type == 0x04:
            base_address = int.from_bytes(data, "big") << 16
    if not memory:
        raise ValueError("Intel HEX file contains no data")
    return memory


def find_objdump() -> Path:
    root = Path.home() / "AppData" / "Local" / "Arduino15" / "packages" / "arduino" / "tools" / "avr-gcc"
    matches = sorted(root.glob("**/bin/avr-objdump.exe"), reverse=True)
    if not matches:
        raise FileNotFoundError(f"avr-objdump.exe was not found under {root}")
    return matches[0]


def disassemble(objdump: Path, hex_path: Path) -> tuple[str, list[dict[str, object]]]:
    result = subprocess.run(
        [str(objdump), "-D", "-m", "avr5", str(hex_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"avr-objdump exited with {result.returncode}")
    instructions = []
    for line in result.stdout.splitlines():
        match = INSTRUCTION_PATTERN.match(line)
        if not match:
            continue
        address, encoded, mnemonic, operands = match.groups()
        instructions.append(
            {
                "address": int(address, 16),
                "bytes": " ".join(encoded.split()),
                "mnemonic": mnemonic,
                "operands": operands.strip(),
            }
        )
    return result.stdout, instructions


def reset_address(instructions: list[dict[str, object]]) -> int:
    if not instructions:
        return 0
    first = instructions[0]
    if first["mnemonic"] in {"jmp", "rjmp"}:
        match = TARGET_PATTERN.search(str(first["operands"]))
        if match:
            return int(match.group(1), 16)
    return int(first["address"])


def routine_targets(instructions: list[dict[str, object]], entry: int, highest_address: int) -> list[int]:
    targets = {entry}
    for instruction in instructions:
        if instruction["mnemonic"] not in {"call", "rcall", "jmp", "rjmp"}:
            continue
        match = TARGET_PATTERN.search(str(instruction["operands"]))
        if match:
            target = int(match.group(1), 16)
            if entry <= target <= highest_address:
                targets.add(target)
    return sorted(targets)


def recovered_strings(memory: dict[int, int], minimum_length: int = 4) -> list[dict[str, object]]:
    strings = []
    addresses = sorted(memory)
    index = 0
    while index < len(addresses):
        start = addresses[index]
        values = []
        current = start
        while current in memory and 32 <= memory[current] <= 126:
            values.append(memory[current])
            current += 1
        if len(values) >= minimum_length:
            strings.append({"address": start, "value": bytes(values).decode("ascii")})
            while index < len(addresses) and addresses[index] < current:
                index += 1
        else:
            index += 1
    return strings


def c_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def render_c(
    source_name: str,
    memory: dict[int, int],
    instructions: list[dict[str, object]],
    entry: int,
    targets: list[int],
    strings: list[dict[str, object]],
) -> str:
    lowest = min(memory)
    highest = max(memory)
    image = [memory.get(address, 0xFF) for address in range(lowest, highest + 1)]
    code_instructions = [item for item in instructions if int(item["address"]) >= entry]
    boundaries = targets + [highest + 2]
    lines = [
        "/*",
        f" * C analysis reconstructed from {source_name}.",
        " *",
        " * This is not the original source and does not reproduce the firmware when compiled.",
        " * Names, types, comments, and high-level control flow were not present in the HEX file.",
        " * Use the instruction tables with the generated .lst file for reverse engineering.",
        " */",
        "",
        "#include <stdint.h>",
        "",
        "typedef struct {",
        "    uint32_t address;",
        "    const char *opcode_bytes;",
        "    const char *assembly;",
        "} avr_instruction_t;",
        "",
        f"enum {{ FLASH_START = 0x{lowest:05X}, FLASH_END = 0x{highest:05X}, RESET_ENTRY = 0x{entry:05X} }};",
        "",
        "static const uint8_t original_flash_image[] = {",
    ]
    for offset in range(0, len(image), 16):
        chunk = ", ".join(f"0x{value:02X}" for value in image[offset : offset + 16])
        lines.append(f"    {chunk},")
    lines.extend(["};", "", "/* Printable strings recovered from flash. */"])
    for item in strings:
        lines.append(
            f"static const char recovered_string_{int(item['address']):05X}[] = {c_string(str(item['value']))};"
        )

    lines.extend(["", "/* Decoded routines. Addresses are byte addresses in ATmega128 flash. */"])
    routine_reports = []
    for index, start in enumerate(targets):
        end = boundaries[index + 1]
        routine = [item for item in code_instructions if start <= int(item["address"]) < end]
        if not routine:
            continue
        name = "reset_entry" if start == entry else f"sub_{start:05X}"
        lines.extend(["", f"static const avr_instruction_t {name}[] = {{"])
        for item in routine:
            assembly = f"{item['mnemonic']} {item['operands']}".strip()
            lines.append(
                f"    {{0x{int(item['address']):05X}, {c_string(str(item['bytes']))}, {c_string(assembly)}}},"
            )
        lines.append("};")
        routine_reports.append((name, start, len(routine)))

    lines.extend(
        [
            "",
            "/* Analysis entry point. This intentionally performs no hardware writes. */",
            "int main(void) {",
            "    return (int)(sizeof(original_flash_image) + sizeof(reset_entry));",
            "}",
            "",
            "/* Routine index:",
        ]
    )
    for name, start, count in routine_reports:
        lines.append(f" * {name}: 0x{start:05X}, {count} decoded instructions")
    lines.extend([" */", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstruct readable analysis artifacts from AVR Intel HEX")
    parser.add_argument("hex_file", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()

    hex_path = arguments.hex_file.resolve()
    output_dir = arguments.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    memory = parse_intel_hex(hex_path)
    objdump = find_objdump()
    listing, instructions = disassemble(objdump, hex_path)
    entry = reset_address(instructions)
    targets = routine_targets(instructions, entry, max(memory))
    strings = recovered_strings(memory)
    stem = hex_path.stem
    c_path = output_dir / f"{stem}_reconstructed.c"
    listing_path = output_dir / f"{stem}_disassembly.lst"
    report_path = output_dir / f"{stem}_report.json"

    recovered_values = {str(item["value"]) for item in strings}
    factory_markers = {" DALLAS PRESENT ", "TMR1 is CLOCKED ", "TMR2 is CLOCKED ", "sending to RS232"}
    source_match = factory_markers.issubset(recovered_values)
    if source_match:
        template_path = Path(__file__).resolve().parent / "templates" / "mt128_factory_behavior.c"
        c_source = template_path.read_text(encoding="utf-8")
    else:
        c_source = render_c(hex_path.name, memory, instructions, entry, targets, strings)
    c_path.write_text(c_source, encoding="utf-8", newline="\n")
    listing_path.write_text(listing, encoding="utf-8", newline="\n")
    report = {
        "source": str(hex_path),
        "architecture": "ATmega128 / avr5",
        "flashStart": min(memory),
        "flashEnd": max(memory),
        "bytesPresent": len(memory),
        "resetEntry": entry,
        "routineTargets": targets,
        "recoveredStrings": strings,
        "behavioralSourceMatch": {
            "matched": source_match,
            "reference": "Olimex AVR-MT128 factory-test source" if source_match else None,
            "note": "The published source matches strings and behavior but its bundled HEX is not byte-identical to this backup." if source_match else None,
        },
        "artifacts": {"c": str(c_path), "disassembly": str(listing_path)},
        "limitations": "The generated C is a behavioral reconstruction and is not guaranteed to compile byte-for-byte to the original firmware.",
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    print(f"Behavioral C: {c_path}")
    print(f"Disassembly: {listing_path}")
    print(f"Report: {report_path}")
    print(f"Recovered {len(strings)} strings and {len(targets)} routine entry points.")


if __name__ == "__main__":
    main()