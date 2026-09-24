"""CircuitPython deployment for FeatherS2 and Adafruit Feather ESP32 V2."""

import argparse
import ast
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time

import serial
from serial.tools import list_ports

ESP32_BOARD = "adafruit_feather_esp32_v2"
S2_BOARD = "unexpectedmaker_feathers2"
S3_BOARD = "adafruit_feather_esp32s3_reverse_tft"
ROOT = Path(__file__).resolve().parents[1]
try:
    from tools.bundle import deployment_contents, BASE_FILES, APP_FILES as SLOT_FILES
except ImportError:
    from bundle import deployment_contents, BASE_FILES, APP_FILES as SLOT_FILES
APP_FILES = ("node_config.py",) + tuple("recovery/" + name for name in SLOT_FILES) + BASE_FILES

# Executed on the device, not imported by host Python. Works with the existing
# producer app; no deployment is needed to inspect the physical button first.
BUTTON_TEST_SOURCE = """
import board, digitalio, time
from ota_bootstrap import load_app
load_app()
from config import CONFIG
from effects import DebouncedButton
def inspect_buttons():
    inputs = []
    extra_next = getattr(CONFIG, 'button_extra_next_gpio', None)
    print('BUTTON TEST role=%s next=%s extra_next=%s previous=%s' %
          (CONFIG.radio_role, CONFIG.button_next_gpio, extra_next, CONFIG.button_previous_gpio))
    try:
        reverse = board.board_id == 'adafruit_feather_esp32s3_reverse_tft'
        gpios = (0,1,2) if reverse else (CONFIG.button_next_gpio, extra_next, CONFIG.button_previous_gpio)
        for gpio in gpios:
            if gpio is None:
                continue
            pin = digitalio.DigitalInOut(getattr(board, ('D%d' if reverse else 'IO%d') % gpio))
            inputs.append([gpio, pin, DebouncedButton(CONFIG.button_debounce_s), None, 0, 0, reverse and gpio != 0])
            pin.switch_to_input(pull=digitalio.Pull.DOWN if reverse and gpio != 0 else digitalio.Pull.UP)
        started = time.monotonic()
        while time.monotonic() - started < 20:
            now = time.monotonic()
            for row in inputs:
                gpio, pin, button, previous, transitions, presses, active_high = row
                level = pin.value
                if level != previous:
                    print('BUTTON GPIO%d level=%d (%s) t=%.2f' %
                          (gpio, level, 'pressed' if level == active_high else 'released', now-started))
                    row[3] = level
                    if previous is not None:
                        row[4] += 1
                if button.update(level == active_high, now):
                    row[5] += 1
                    print('BUTTON GPIO%d accepted press=%d' % (gpio, row[5]))
            time.sleep(0.005)
        for gpio, pin, button, previous, transitions, presses, active_high in inputs:
            print('BUTTON RESULT GPIO%d transitions=%d presses=%d final_level=%d' %
                  (gpio, transitions, presses, pin.value))
        if not inputs:
            print('BUTTON RESULT no controls configured')
    finally:
        for row in inputs:
            row[1].deinit()
inspect_buttons()
"""


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
        # A deliberately interrupted field app must not reset during USB work.
        self.execute("import microcontroller; microcontroller.watchdog.mode = None")

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
        markers = ("Rainbow frames: 256",) if legacy else ("AUDIO rms=", "LIGHTS frame=", "SETUP role unconfigured")
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


def deploy_s2(repl, mount, node_config=None, base_only=False, board_id=S2_BOARD):
    drive = find_drive("CIRCUITPY", mount)
    boot_info = (drive / "boot_out.txt").read_text()
    uid = repl.execute("import microcontroller; print(microcontroller.cpu.uid.hex())")
    if (f"Board ID:{board_id}" not in boot_info.splitlines()
            or uid.lower() not in boot_info.lower()):
        raise RuntimeError("CIRCUITPY drive does not match the connected native USB board.")
    if repl.execute("import storage; print(storage.getmount('/').readonly)") != "True":
        raise RuntimeError("Board is in OTA field mode. Reset, then press BOOT during the blue startup window for USB maintenance.")
    # Python must not remount a drive that the USB host also writes.
    repl.execute("import supervisor; supervisor.runtime.autoreload = False")
    contents = deployment_contents()
    if base_only:
        contents = {name: contents[name] for name in BASE_FILES}
    sources = tuple(contents)
    if node_config:
        contents["node_config.py"] = Path(node_config).read_bytes()
    elif not base_only and (drive / "node_config.py").is_file():
        contents["node_config.py"] = (drive / "node_config.py").read_bytes()
        print("Preserving this board's saved role and configuration.")
    elif not base_only and board_id == S3_BOARD:
        contents["node_config.py"] = b"OVERRIDES = {}\n"
    backup = ROOT / ".artifacts" / "app-backups" / f"native-usb-{time.time_ns()}"
    backup.mkdir(parents=True)
    for source in sources:
        data = contents[source]
        if source.endswith(".py"):
            compile(data, source, "exec")
        destination = drive / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            saved = backup / source
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(destination, saved)
        temporary = drive / (source + ".tmp")
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary.read_bytes() != data:
            raise RuntimeError(f"Readback failed for {source}")
    for source in sources:
        (drive / (source + ".tmp")).replace(drive / source)
    os.sync()
    for source in sources:
        if (drive / source).read_bytes() != contents[source]:
            raise RuntimeError(f"Final readback failed for {source}")
    print("Verified %d base/recovery files; restarting." % len(contents))


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


def flash_native(firmware, mount, board_id):
    if board_id == S2_BOARD:
        return flash_s2(firmware,mount)
    import re
    firmware=Path(firmware)
    if board_id != S3_BOARD or board_id not in firmware.name or firmware.suffix!='.uf2':
        raise RuntimeError('Supply official Reverse TFT .uf2 firmware')
    drive=find_drive('FTHRS3BOOT',mount)
    info=(drive/'INFO_UF2.TXT').read_text()
    if 'Reverse TFT' not in info and 'revTFT' not in info:
        raise RuntimeError('Bootloader does not identify Reverse TFT')
    version=re.search(r'(?:TinyUF2|UF2) Bootloader[^0-9]*(\d+)\.(\d+)\.(\d+)',info)
    if not version or tuple(map(int,version.groups()))<(0,33,0):
        raise RuntimeError('CircuitPython 10 requires TinyUF2 0.33.0+; back up and update the bootloader first')
    backup=ROOT/'.artifacts/app-backups'/('s3-uf2-'+str(time.time_ns()))
    backup.mkdir(parents=True)
    (backup/'INFO_UF2.TXT').write_text(info)
    current=drive/'CURRENT.UF2'
    if not current.exists():
        raise RuntimeError('Bootloader provides no readable firmware backup. Use make flash-rom in ROM recovery for a full verified backup before installation')
    shutil.copyfile(current,backup/'CURRENT.UF2')
    if current.stat().st_size!=(backup/'CURRENT.UF2').stat().st_size:
        raise RuntimeError('Incomplete firmware backup')
    shutil.copyfile(firmware,drive/'firmware.uf2');os.sync()
    print('Firmware backed up and UF2 sent; wait for CIRCUITPY')


def deploy_serial(repl, node_config=None, legacy=False, base_only=False):
    """Back up, stage and verify files on boards without USB mass storage."""
    names = ("code.py",) if legacy else (BASE_FILES if base_only else APP_FILES)
    contents = ({"code.py": (ROOT / "examples/esp32_rainbow.py").read_bytes()}
                if legacy else deployment_contents())
    contents = {name: contents[name] for name in names}
    repl.execute("import supervisor, storage, os; supervisor.runtime.autoreload = False; storage.remount('/', readonly=False)")
    backup = ROOT / ".artifacts" / "app-backups" / f"esp32-{time.time_ns()}"
    backup.mkdir(parents=True)
    repl.execute("def _exists(path):\n try:\n  os.stat(path)\n  return True\n except OSError:\n  return False")
    for name in names:
        if repl.execute(f"print(_exists('/{name}'))") == "True":
            previous = ast.literal_eval(repl.execute(f"print(repr(open('/{name}', 'rb').read()))"))
            saved = backup / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(previous)
            if name == "node_config.py" and not node_config:
                contents[name] = previous
                print("Preserving this board's saved role and configuration.", flush=True)
    if node_config and not legacy:
        contents["node_config.py"] = Path(node_config).read_bytes()
    for name, data in contents.items():
        if name.endswith(".py"):
            compile(data, name, "exec")
    for name, data in contents.items():
        if "/" in name:
            parent = name.rsplit("/", 1)[0]
            repl.execute(f"if not _exists('/{parent}'):\n os.mkdir('/{parent}')")
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
    # Verify the newly installed recovery app in maintenance mode. A hard reset
    # restores normal field ownership and the existing confirmed OTA selection.
    repl.execute("storage.remount('/', readonly=True)")
    print(f"Verified {len(names)} application files; restarting.", flush=True)


def deploy(port, board_id, mount=None, node_config=None, legacy=False, base_only=False):
    repl = Repl(port)
    try:
        repl.enter()
        identity = repl.execute("import board, sys; print(board.board_id); print(sys.implementation)")
        print(identity, flush=True)
        detected = identity.splitlines()[0].strip()
        if board_id == "auto":
            if detected not in (S2_BOARD, ESP32_BOARD, S3_BOARD):
                raise RuntimeError(f"No verified wiring profile for {detected}; add one before deployment.")
            board_id = detected
        if legacy and board_id != ESP32_BOARD:
            raise RuntimeError("Legacy rainbow is only configured for ESP32 V2")
        if (identity.splitlines()[0].strip() != board_id
                or "circuitpython" not in identity.lower()):
            raise RuntimeError(f"Wrong board or firmware; expected {board_id}.")
        if not legacy:
            if not re.search(r"version=\(10,\s*3,\s*1[,) ]", identity):
                raise RuntimeError("Shared app requires pinned CircuitPython 10.3.1")
            repl.execute("import espnow; from ulab import numpy, utils")
        if board_id in (S2_BOARD, S3_BOARD):
            repl.execute("import audioi2sin")
            native_options = {"board_id": board_id} if board_id == S3_BOARD else {}
            if board_id == S3_BOARD:
                repl.execute("import displayio, terminalio; from board import DISPLAY")
            if base_only:
                deploy_s2(repl, mount, base_only=True, **native_options)
            else:
                deploy_s2(repl, mount, node_config, **native_options)
        else:
            if base_only:
                deploy_serial(repl, base_only=True)
            else:
                deploy_serial(repl, node_config, legacy)
        repl.restart(board_id, legacy=legacy)
    finally:
        repl.serial.close()


def configuration_bytes(previous, data):
    """Preserve literal per-node tuning; refuse executable/dynamic profiles."""
    tree = ast.parse(previous or 'OVERRIDES = {}')
    values = None
    for statement in tree.body:
        if isinstance(statement,ast.Assign) and len(statement.targets)==1 and isinstance(statement.targets[0],ast.Name) and statement.targets[0].id=='OVERRIDES':
            values = ast.literal_eval(statement.value)
        elif not isinstance(statement,ast.Expr) or not isinstance(statement.value,ast.Constant) or not isinstance(statement.value.value,str):
            raise ValueError('Dynamic node_config.py: use an explicit reviewed NODE_CONFIG profile')
    if type(values) is not dict:
        raise ValueError('Expected literal OVERRIDES dict')
    values.update({key:value for key,value in data.items() if key!='schema'})
    return ('# Per-device tuning and confirmed identity.\nOVERRIDES = '+repr(values)+'\n').encode()


def configure_node(port, role, group, leader_mac=None, mount=None):
    import json
    from node_state import validate
    data={'schema':1,'radio_role':role,'radio_group':group}
    if leader_mac:data['leader_mac']=leader_mac.lower()
    validate(data)
    repl=Repl(port)
    try:
        repl.enter()
        identity=ast.literal_eval(repl.execute('import board,microcontroller; print(repr((board.board_id,microcontroller.cpu.uid.hex().lower())))'))
        board_id,uid=identity
        if board_id not in (S2_BOARD,S3_BOARD,ESP32_BOARD) or (board_id==ESP32_BOARD and role!='consumer'):
            raise ValueError('Unsupported board role')
        enrolled,locked=ast.literal_eval(repl.execute("import os; print(repr((bool(os.getenv('OTA_DEVICE_TOKEN')),os.getenv('OTA_DEVICE_ROLE'))))"))
        if enrolled and locked is None:
            locked=ast.literal_eval(repl.execute("from node_state import current; print(repr(current().get('radio_role')))"))
        if enrolled and locked!=role:
            raise ValueError('Role locked to enrolled identity; re-enroll and provision a reviewed profile')
        native=board_id in (S2_BOARD,S3_BOARD)
        if native:
            drive=find_drive('CIRCUITPY',mount)
            info=(drive/'boot_out.txt').read_text()
            if ('Board ID:'+board_id) not in info.splitlines() or uid not in info.lower():
                raise ValueError('CIRCUITPY identity mismatch')
            if repl.execute("import storage; print(storage.getmount('/').readonly)")!='True':
                raise ValueError('USB host does not own filesystem; enter maintenance')
            previous=(drive/'node_config.py').read_text() if (drive/'node_config.py').exists() else ''
        else:
            previous=ast.literal_eval(repl.execute("try:\n print(repr(open('/node_config.py').read()))\nexcept OSError:\n print(repr(''))"))
            repl.execute("import storage; storage.remount('/',readonly=False)")
        files={'node_state.json':json.dumps(data).encode(),'node_config.py':configuration_bytes(previous,data)}
        backup=ROOT/'.artifacts/app-backups'/('configuration-'+uid+'-'+str(time.time_ns()))
        backup.mkdir(parents=True)
        (backup/'node_config.py').write_text(previous)
        repl.execute('import supervisor; supervisor.runtime.autoreload=False')
        for name,contents in files.items():
            if native:
                target=drive/name
                if target.exists():(backup/name).write_bytes(target.read_bytes())
                temporary=drive/(name+'.tmp')
                with temporary.open('wb') as stream:
                    stream.write(contents);stream.flush();os.fsync(stream.fileno())
                if temporary.read_bytes()!=contents:raise ValueError('Configuration readback failed')
                temporary.replace(target);os.sync()
                if target.read_bytes()!=contents:raise ValueError('Configuration final readback failed')
            else:
                repl.execute("f=open('/%s.tmp','wb'); f.write(%r); f.close(); os.sync()"%(name,contents))
                actual=ast.literal_eval(repl.execute("print(repr(open('/%s.tmp','rb').read()))"%name))
                if actual!=contents:raise ValueError('Configuration readback failed')
                repl.execute("os.rename('/%s.tmp','/%s'); os.sync()"%(name,name))
        print('Verified node identity: role=%s group=%d source=%s. Reset to apply.'%(role,group,leader_mac or 'local microphone'))
    finally:
        repl.serial.close()


def flash(port, firmware, board_id=ESP32_BOARD):
    firmware = Path(firmware)
    if board_id not in firmware.name or firmware.suffix != ".bin" or not firmware.is_file():
        raise RuntimeError(f"Supply the downloaded {board_id} .bin firmware.")
    s2 = board_id == S2_BOARD
    native = board_id in (S2_BOARD,S3_BOARD)
    chip, megabytes, baud = (("esp32s2", 16, "115200") if s2 else
                             ("esp32s3", 4, "115200") if board_id==S3_BOARD else ("esp32", 8, "115200"))
    command = [sys.executable, "-m", "esptool", "--chip", chip, "--port", port, "--baud", baud]
    if native:
        command += ["--before", "no-reset", "--after", "no-reset-stub"]
    result = subprocess.run(command + ["flash-id"], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    identity = result.stdout
    print(identity, flush=True)
    expected_chip = "ESP32-S2" if s2 else "ESP32-S3" if board_id==S3_BOARD else "ESP32-PICO-V3-02"
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
    if native:
        print("Firmware verified. Press RESET once to leave recovery and start CircuitPython.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("ports", "deploy", "flash", "flash-rom", "console", "test-mic", "test-buttons", "benchmark", "configure-node"))
    parser.add_argument("--board", choices=("auto", S2_BOARD, ESP32_BOARD, S3_BOARD), default=S2_BOARD)
    parser.add_argument("--port", default="")
    parser.add_argument("--mount")
    parser.add_argument("--node-config", help="Explicitly replace saved node configuration")
    parser.add_argument("--firmware")
    parser.add_argument("--role", choices=("producer","consumer"),default="consumer")
    parser.add_argument("--group",type=int,default=1)
    parser.add_argument("--leader-mac")
    parser.add_argument("--base-only", action="store_true", help="Update USB base while preserving recovery app and OTA slots")
    parser.add_argument("--legacy-rainbow", action="store_true", help="Deploy the original ESP32 V2 rainbow example")
    args = parser.parse_args()
    if args.base_only and (args.action != "deploy" or args.node_config or args.legacy_rainbow):
        parser.error("--base-only requires deploy without node-config or legacy-rainbow")
    if args.board == "auto" and args.action not in ("deploy", "configure-node"):
        parser.error("Automatic board selection is supported only for deploy")
    if args.action == "ports":
        for port in list_ports.comports():
            if port.vid:
                print(port.device, port.description, port.hwid)
        return
    if args.action == "flash" and args.board in (S2_BOARD,S3_BOARD):
        if not args.firmware:
            parser.error("flash requires --firmware")
        flash_native(args.firmware, args.mount, args.board)
        return
    port = find_port(args.port)
    print(f"Using {port}", flush=True)
    if args.action == "configure-node":
        configure_node(port,args.role,args.group,args.leader_mac,args.mount)
    elif args.action == "deploy":
        deploy(port, args.board, args.mount, args.node_config, args.legacy_rainbow, args.base_only)
    elif args.action in ("test-mic", "test-buttons", "benchmark"):
        if args.board not in (S2_BOARD,S3_BOARD):
            parser.error("Producer diagnostics require FeatherS2 or Reverse TFT")
        repl = Repl(port)
        try:
            repl.enter()
            if repl.execute("import board; print(board.board_id)") != args.board:
                raise RuntimeError("Connected board does not match BOARD")
            try:
                if args.action == "test-buttons":
                    print("Press/release BOOT and configured external buttons over the next 20 seconds. "
                          "Audio and lighting are paused; results appear when the test ends.", flush=True)
                    print(repl.execute(BUTTON_TEST_SOURCE, timeout=30))
                else:
                    command = "app.test_microphone(10)" if args.action == "test-mic" else "app.benchmark(5)"
                    print(repl.execute("from ota_bootstrap import load_app; app, _ = load_app(); " + command, timeout=25))
            finally:
                repl.restart(args.board)
        finally:
            repl.serial.close()
    elif args.action in ("flash", "flash-rom"):
        if not args.firmware:
            parser.error("flash requires --firmware")
        flash(port, args.firmware, args.board)
    else:
        dtr = "1" if args.board in (S2_BOARD,S3_BOARD) else "0"
        subprocess.run([sys.executable, "-m", "serial.tools.miniterm", "--dtr", dtr,
                        "--rts", "0", port, "115200"], check=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))
