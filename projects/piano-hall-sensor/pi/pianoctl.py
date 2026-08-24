#!/usr/bin/env python3
"""Control the AVR-MT128 player-piano controller over the Pi UART."""

from __future__ import annotations

import argparse
import os
import select
import sys
import termios
import time


DEFAULT_DEVICE = "/dev/serial0"
DEFAULT_BAUD = 115200


class SerialPort:
    def __init__(self, device: str, baud: int) -> None:
        speeds = {
            9600: termios.B9600,
            19200: termios.B19200,
            38400: termios.B38400,
            57600: termios.B57600,
            115200: termios.B115200,
        }
        if baud not in speeds:
            raise ValueError(f"Unsupported baud rate: {baud}")

        self.fd = os.open(device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attributes = termios.tcgetattr(self.fd)
        attributes[0] = 0
        attributes[1] = 0
        attributes[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attributes[3] = 0
        attributes[4] = speeds[baud]
        attributes[5] = speeds[baud]
        attributes[6][termios.VMIN] = 0
        attributes[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, attributes)
        termios.tcflush(self.fd, termios.TCIOFLUSH)
        self.buffer = bytearray()

    def close(self) -> None:
        os.close(self.fd)

    def send(self, message: str) -> None:
        data = f"{message.rstrip()}\n".encode("ascii")
        while data:
            _, writable, _ = select.select([], [self.fd], [], 1.0)
            if not writable:
                raise TimeoutError("UART write timed out")
            written = os.write(self.fd, data)
            data = data[written:]
        termios.tcdrain(self.fd)

    def receive(self, timeout: float) -> str | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if b"\n" in self.buffer:
                line, _, remainder = self.buffer.partition(b"\n")
                self.buffer = bytearray(remainder)
                return line.rstrip(b"\r").decode("ascii", errors="replace")

            readable, _, _ = select.select([self.fd], [], [], deadline - time.monotonic())
            if readable:
                chunk = os.read(self.fd, 256)
                if chunk:
                    self.buffer.extend(chunk)
        return None

    def __enter__(self) -> SerialPort:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def wait_for(port: SerialPort, expected: set[str], timeout: float) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = port.receive(deadline - time.monotonic())
        if message is None:
            break
        print(message, flush=True)
        if message in expected or message.startswith("ERROR"):
            return message
    raise TimeoutError(f"No response within {timeout:g} seconds")


def send_command(port: SerialPort, command: str, timeout: float) -> int:
    port.send(command)
    response = wait_for(port, {"OK"}, timeout)
    return 0 if response == "OK" else 2


def run(args: argparse.Namespace) -> int:
    args.command = args.command.lower().replace("_", "-")

    if args.command == "status" and not os.path.exists(args.device):
        print(f"missing: {args.device}")
        return 1

    with SerialPort(args.device, args.baud) as port:
        if args.command == "status":
            print(f"ready: {args.device} at {args.baud} 8N1")
            return 0

        if args.command == "monitor":
            while True:
                message = port.receive(1.0)
                if message is not None:
                    print(message, flush=True)

        if args.command == "send":
            message = " ".join(args.words)
            port.send(message)
            print(f"sent: {message}")
            return 0

        if args.command == "loopback":
            token = f"PIANO_LOOPBACK_{time.monotonic_ns()}"
            port.send(token)
            response = port.receive(args.timeout)
            print(f"sent: {token}")
            print(f"received: {response or '<nothing>'}")
            return 0 if response == token else 1

        if args.command == "beep":
            return send_command(port, "BEEP", args.timeout)

        if args.command == "relay-on":
            return send_command(port, "RELAY_ON", args.timeout)

        if args.command == "relay-off":
            return send_command(port, "RELAY_OFF", args.timeout)

        if args.command == "lcd":
            return send_command(port, f"LCD {args.text}", args.timeout)

        if args.command == "command":
            return send_command(port, " ".join(args.words), args.timeout)

        port.send("PLAY" if args.song is None else f"PLAY {args.song}")
        response = wait_for(port, {"STARTED"}, args.start_timeout)
        if response != "STARTED":
            return 2
        response = wait_for(port, {"COMPLETE"}, args.complete_timeout)
        return 0 if response == "COMPLETE" else 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="verify that the UART can be opened")
    subparsers.add_parser("monitor", help="print messages received from the MT128")
    send = subparsers.add_parser("send", help="send one command without waiting for a reply")
    send.add_argument("words", nargs="+", help="command and arguments")
    loopback = subparsers.add_parser(
        "loopback", help="test Pi UART with physical pins 8 and 10 jumpered"
    )
    loopback.add_argument("--timeout", type=float, default=2.0)
    for name, help_text in (
        ("beep", "make the MT128 beep"),
        ("relay-on", "energize the MT128 relay"),
        ("relay-off", "release the MT128 relay"),
    ):
        command = subparsers.add_parser(
            name,
            aliases=[name.upper().replace("-", "_")],
            help=help_text,
        )
        command.add_argument("--timeout", type=float, default=3.0)
    lcd = subparsers.add_parser(
        "lcd", aliases=["LCD"], help="write up to 32 characters to the MT128 LCD"
    )
    lcd.add_argument("text", help="LCD text, for example: 'HI THERE'")
    lcd.add_argument("--timeout", type=float, default=3.0)
    command = subparsers.add_parser("command", help="send a raw newline-terminated command")
    command.add_argument("words", nargs="+", help="command and arguments")
    command.add_argument("--timeout", type=float, default=3.0)
    play = subparsers.add_parser("play", help="start one piano song and wait for completion")
    play.add_argument("song", nargs="?", help="optional song identifier")
    play.add_argument("--start-timeout", type=float, default=3.0)
    play.add_argument("--complete-timeout", type=float, default=300.0)
    return parser.parse_args()


if __name__ == "__main__":
    try:
        raise SystemExit(run(parse_args()))
    except (OSError, TimeoutError, ValueError) as error:
        print(f"pianoctl: {error}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)