"""CircuitPython deployment for FeatherS2 and Adafruit Feather ESP32 V2."""

import argparse
import ast
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import serial
from serial.tools import list_ports

ESP32_BOARD = "adafruit_feather_esp32_v2"
S2_BOARD = "unexpectedmaker_feathers2"
ROOT = Path(__file__).resolve().parents[1]
APP_FILES = ("node_config.py", "config.py", "sound_reactive.py", "audio_spectrum.py",
             "audio_features.py", "animation.py", "effects.py", "radio_protocol.py",
             "wireless.py", "code.py")


def find_port(explicit):
    if explicit:
        return explicit
    ports = [p.device for p in list_ports.comports()
             if p.vid in (0x1A86, 0x10C4, 0x239A, 0x303A)]
    if len(ports) != 1:
        raise RuntimeError("Expected one USB serial board; use PORT=/dev/cu.usbserial-... . Found: " + repr(ports))
    return ports[0]


class Repl:
    def __init__(self, port):
        self.serial = serial.Serial(port=None, baudrate=115200, timeout=0.1, write_timeout=5)
        # Native USB CircuitPython consoles require DTR; USB-UART bridges reset
        # ESP32 boards when their control lines change, so leave those low.
        native_usb = any(p.device == port and p.vid == 0x239A
                         for p in list_ports.comports())
        self.serial.dtr = native_usb
        self.serial.rts = False
        self.serial.port = port
        self.serial.open()

    def until(self, marker, timeout=10):
        data = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data.extend(self.serial.read(1))
            if data.endswith(marker):
                return bytes(data[:-len(marker)])
        raise RuntimeError(f"Serial timeout waiting for {marker!r}: {bytes(data)!r}")

    def enter(self):
        # Opening the USB bridge can reset the ESP32; let CircuitPython boot.
        time.sleep(2)
        self.serial.reset_input_buffer()
        for attempt in range(5):
            # Ctrl-B also recovers a raw REPL left by a failed previous upload.
            self.serial.write(b"\x02\r\x03\x03")
            try:
                self.until(b">>> ", timeout=2)
                break
            except RuntimeError:
                if attempt == 4:
                    raise
        self.serial.write(b"\x01")
        self.until(b"raw REPL; CTRL-B to exit")
        self.until(b">")

    def execute(self, source, timeout=10):
        payload = source.encode("utf-8")
        for offset in range(0, len(payload), 128):
            self.serial.write(payload[offset:offset + 128])
            time.sleep(0.01)
        self.serial.write(b"\x04")
        acknowledgement = self.until(b"OK")
        if acknowledgement:
            raise RuntimeError(f"Unexpected REPL response: {acknowledgement!r}")
        output = self.until(b"\x04", timeout=timeout)
        error = self.until(b"\x04")
        self.until(b">")
        if error:
            raise RuntimeError(error.decode("utf-8", "replace"))
        return output.decode("utf-8", "replace").strip()

    def restart(self, board_id=ESP32_BOARD, legacy=False):
        self.serial.write(b"\x02")
        self.until(b">>> ")
        self.serial.write(b"\x04")
        output = bytearray()
        deadline = time.monotonic() + 9
        while time.monotonic() < deadline:
            output.extend(self.serial.read(1024))
        text = output.decode("utf-8", "replace")
        print(text)
        markers = ("Rainbow frames: 256",) if legacy else ("AUDIO rms=", "LIGHTS frame=")
        if "Traceback" in text or not any(marker in text for marker in markers):
            raise RuntimeError("App startup check failed. Inspect with make console.")


def find_drive(name, explicit=None):
    labels = ("FTHRS2BOOT", "UFTHRS2BOOT") if name == "FTHRS2BOOT" else (name,)
    candidates = [Path(explicit)] if explicit else []
    if not explicit:
        for label in labels:
            candidates.extend([Path("/Volumes") / label,
                               *Path("/media").glob(f"*/{label}"),
                               *Path("/run/media").glob(f"*/{label}")])
    found = [path for path in candidates if path.is_dir()]
    if len(found) != 1:
        raise RuntimeError(f"Expected one {name} drive. Found {found}; use --mount PATH.")
    return found[0]


def deploy_s2(repl, mount, node_config=None):
    drive = find_drive("CIRCUITPY", mount)
    boot_info = (drive / "boot_out.txt").read_text()
    uid = repl.execute("import microcontroller; print(microcontroller.cpu.uid.hex())")
    if (f"Board ID:{S2_BOARD}" not in boot_info.splitlines()
            or uid.lower() not in boot_info.lower()):
        raise RuntimeError("CIRCUITPY drive does not match the connected FeatherS2.")
    # Python must not remount a drive that the USB host also writes.
    repl.execute("import supervisor; supervisor.runtime.autoreload = False")
    sources = [ROOT / name for name in APP_FILES]
    # Snapshot once so edits during a slow USB copy cannot mix file generations.
    contents = {source.name: source.read_bytes() for source in sources}
    if node_config:
        contents["node_config.py"] = Path(node_config).read_bytes()
    elif (drive / "node_config.py").is_file():
        contents["node_config.py"] = (drive / "node_config.py").read_bytes()
        print("Preserving this board's saved role and configuration.")
    backup = ROOT / ".artifacts" / "app-backups" / f"feathers2-{time.time_ns()}"
    backup.mkdir(parents=True)
    for source in sources:
        data = contents[source.name]
        compile(data, source.name, "exec")
        destination = drive / source.name
        if destination.exists():
            shutil.copyfile(destination, backup / source.name)
        temporary = drive / (source.name + ".tmp")
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary.read_bytes() != data:
            raise RuntimeError(f"Readback failed for {source.name}")
    for source in sources:
        (drive / (source.name + ".tmp")).replace(drive / source.name)
    os.sync()
    for source in sources:
        if (drive / source.name).read_bytes() != contents[source.name]:
            raise RuntimeError(f"Final readback failed for {source.name}")
    print("Verified all ten application files; restarting.")


def flash_s2(firmware, mount):
    firmware = Path(firmware)
    if S2_BOARD not in firmware.name or firmware.suffix != ".uf2":
        raise RuntimeError("Supply the official Unexpected Maker FeatherS2 .uf2 file.")
    drive = find_drive("FTHRS2BOOT", mount)
    info = (drive / "INFO_UF2.TXT").read_text()
    if "FeatherS2" not in info or "Neo" in info:
        raise RuntimeError("Bootloader drive does not identify the original FeatherS2.")
    print(info)
    # Bootloader validates and programs UF2 blocks, then disconnects/reboots.
    shutil.copyfile(firmware, drive / "firmware.uf2")
    os.sync()
    print("UF2 sent. Wait for CIRCUITPY, then run make deploy.")


def deploy_serial(repl, node_config=None, legacy=False):
    """Back up, stage and verify files on boards without USB mass storage."""
    names = ("code.py",) if legacy else APP_FILES
    contents = {name: (ROOT / ("examples/esp32_rainbow.py" if legacy else name)).read_bytes()
                for name in names}
    repl.execute("import supervisor, storage, os; supervisor.runtime.autoreload = False; storage.remount('/', readonly=False)")
    backup = ROOT / ".artifacts" / "app-backups" / f"esp32-{time.time_ns()}"
    backup.mkdir(parents=True)
    existing = ast.literal_eval(repl.execute("print(repr(os.listdir('/')))"))
    for name in names:
        if name in existing:
            previous = ast.literal_eval(repl.execute(f"print(repr(open('/{name}', 'rb').read()))"))
            (backup / name).write_bytes(previous)
            if name == "node_config.py" and not node_config:
                contents[name] = previous
                print("Preserving this board's saved role and configuration.", flush=True)
    if node_config and not legacy:
        contents["node_config.py"] = Path(node_config).read_bytes()
    for name, data in contents.items():
        compile(data, name, "exec")
    for name, data in contents.items():
        repl.execute(f"f = open('/{name}.tmp', 'wb')")
        for offset in range(0, len(data), 1024):
            repl.execute(f"f.write({data[offset:offset + 1024]!r})")
        repl.execute("f.close(); os.sync()")
        uploaded = ast.literal_eval(repl.execute(f"print(repr(open('/{name}.tmp', 'rb').read()))"))
        if uploaded != data:
            raise RuntimeError(f"Upload readback differs for {name}; existing app preserved.")
        print(f"Staged and verified {name}: {len(data)} bytes", flush=True)
    for name in names:
        repl.execute(f"os.rename('/{name}.tmp', '/{name}')")
    repl.execute("os.sync()")
    for name, data in contents.items():
        uploaded = ast.literal_eval(repl.execute(f"print(repr(open('/{name}', 'rb').read()))"))
        if uploaded != data:
            raise RuntimeError(f"Final readback failed for {name}")
    print(f"Verified {len(names)} application files; restarting.", flush=True)


def deploy(port, board_id, mount=None, node_config=None, legacy=False):
    repl = Repl(port)
    try:
        repl.enter()
        identity = repl.execute("import board, sys; print(board.board_id); print(sys.implementation)")
        print(identity, flush=True)
        detected = identity.splitlines()[0].strip()
        if board_id == "auto":
            if detected not in (S2_BOARD, ESP32_BOARD):
                raise RuntimeError(f"No verified wiring profile for {detected}; add one before deployment.")
            board_id = detected
        if legacy and board_id != ESP32_BOARD:
            raise RuntimeError("Legacy rainbow is only configured for ESP32 V2")
        if (identity.splitlines()[0].strip() != board_id
                or "circuitpython" not in identity.lower()):
            raise RuntimeError(f"Wrong board or firmware; expected {board_id}.")
        if not legacy:
            repl.execute("import espnow; from ulab import numpy, utils")
        if board_id == S2_BOARD:
            repl.execute("import audioi2sin")
            deploy_s2(repl, mount, node_config)
        else:
            deploy_serial(repl, node_config, legacy)
        repl.restart(board_id, legacy=legacy)
    finally:
        repl.serial.close()


def flash(port, firmware, board_id=ESP32_BOARD):
    firmware = Path(firmware)
    if board_id not in firmware.name or firmware.suffix != ".bin" or not firmware.is_file():
        raise RuntimeError(f"Supply the downloaded {board_id} .bin firmware.")
    s2 = board_id == S2_BOARD
    chip, megabytes, baud = ("esp32s2", 16, "115200") if s2 else ("esp32", 8, "115200")
    command = [sys.executable, "-m", "esptool", "--chip", chip, "--port", port, "--baud", baud]
    if s2:
        command += ["--before", "no-reset", "--after", "no-reset-stub"]
    result = subprocess.run(command + ["flash-id"], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    identity = result.stdout
    print(identity, flush=True)
    expected_chip = "ESP32-S2" if s2 else "ESP32-PICO-V3-02"
    if expected_chip not in identity or f"Detected flash size: {megabytes}MB" not in identity:
        raise RuntimeError(f"Hardware does not match the expected {megabytes} MB {board_id}.")
    backup = ROOT / ".artifacts" / f"flash-backup-{time.time_ns()}.bin"
    backup.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(command + ["read-flash", "0", "ALL", str(backup)], check=True)
    if backup.stat().st_size != megabytes * 1024 * 1024:
        raise RuntimeError("Incomplete flash backup; installation cancelled.")
    print(f"Existing flash backed up to {backup}", flush=True)
    subprocess.run(command + ["erase-flash"], check=True)
    subprocess.run(command + ["write-flash", "0x0", str(firmware)], check=True)
    if s2:
        print("Firmware verified. Press RESET once to leave recovery and start CircuitPython.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("ports", "deploy", "flash", "flash-rom", "console", "test-mic", "benchmark"))
    parser.add_argument("--board", choices=("auto", S2_BOARD, ESP32_BOARD), default=S2_BOARD)
    parser.add_argument("--port", default="")
    parser.add_argument("--mount")
    parser.add_argument("--node-config", help="Explicitly replace saved node configuration")
    parser.add_argument("--firmware")
    parser.add_argument("--legacy-rainbow", action="store_true", help="Deploy the original ESP32 V2 rainbow example")
    args = parser.parse_args()
    if args.board == "auto" and args.action != "deploy":
        parser.error("Automatic board selection is supported only for deploy")
    if args.action == "ports":
        for port in list_ports.comports():
            if port.vid:
                print(port.device, port.description, port.hwid)
        return
    if args.action == "flash" and args.board == S2_BOARD:
        if not args.firmware:
            parser.error("flash requires --firmware")
        flash_s2(args.firmware, args.mount)
        return
    port = find_port(args.port)
    print(f"Using {port}", flush=True)
    if args.action == "deploy":
        deploy(port, args.board, args.mount, args.node_config, args.legacy_rainbow)
    elif args.action in ("test-mic", "benchmark"):
        if args.board != S2_BOARD:
            parser.error("Audio diagnostics are configured for the FeatherS2 wiring")
        repl = Repl(port)
        try:
            repl.enter()
            if repl.execute("import board; print(board.board_id)") != S2_BOARD:
                raise RuntimeError("Expected an Unexpected Maker FeatherS2")
            try:
                command = "code.test_microphone(10)" if args.action == "test-mic" else "code.benchmark(5)"
                print(repl.execute("import code; " + command, timeout=25))
            finally:
                repl.restart(S2_BOARD)
        finally:
            repl.serial.close()
    elif args.action in ("flash", "flash-rom"):
        if not args.firmware:
            parser.error("flash requires --firmware")
        flash(port, args.firmware, args.board)
    else:
        dtr = "1" if args.board == S2_BOARD else "0"
        subprocess.run([sys.executable, "-m", "serial.tools.miniterm", "--dtr", dtr,
                        "--rts", "0", port, "115200"], check=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))
