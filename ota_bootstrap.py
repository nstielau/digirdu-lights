"""USB-managed boot maintenance, isolated app loading, health trial and rollback."""
import gc
import json
import os
import sys
import time

from ota_manifest import APP_API, BASE_VERSION, BOARDS, MAX_MANIFEST, validate
from ota_store import UpdateStore
from ota_http import DeviceHTTP
from battery import read_battery

TRIAL_SECONDS = 30
NVM_MARKER = b"DGO1"  # Reserved bytes 0..4; never store device secrets in NVM.
OTA_PIXEL_COUNT = 32
OTA_PIXEL_BRIGHTNESS = 0.03
OTA_PIXEL_STEP_S = 0.5


class OTAIndicator:
    """One cyan pixel advances while boot-time networking services its watchdog.

    This is activity, not a download percentage. Blocking Wi-Fi/TLS calls leave
    the current pixel lit until they return. No application modules are loaded.
    """
    def __init__(self):
        import board
        import digitalio
        from neopixel_write import neopixel_write
        pins = {"unexpectedmaker_feathers2": "IO38",
                "adafruit_feather_esp32_v2": "D32"}
        self.pin = digitalio.DigitalInOut(getattr(board, pins[board.board_id]))
        self.write = neopixel_write
        self.pixels = bytearray(OTA_PIXEL_COUNT * 3)
        self.index = -1
        self.next_step = 0.0
        try:
            self.pin.switch_to_output(value=False)
            self.update()
        except BaseException:
            self.pin.deinit()
            raise

    def update(self):
        now = time.monotonic()
        if now < self.next_step:
            return
        self.pixels[:] = bytes(len(self.pixels))
        self.index = (self.index + 1) % OTA_PIXEL_COUNT
        level = int(255 * OTA_PIXEL_BRIGHTNESS)
        # GRB: a dim cyan status pixel, independent of the app's brightness.
        self.pixels[self.index * 3] = level
        self.pixels[self.index * 3 + 2] = level
        self.write(self.pin, self.pixels)
        self.next_step = now + OTA_PIXEL_STEP_S

    def close(self):
        try:
            self.write(self.pin, bytes(len(self.pixels)))
        finally:
            self.pin.deinit()


def load_app(directory="/recovery"):
    # Load node identity before removing root from app import paths. This is
    # trusted code isolation against accidental mixed versions, not a sandbox.
    import node_config
    sys.path[:] = [directory, "/lib"]
    import app_version
    import lights_app
    if app_version.APP_API_VERSION != APP_API:
        raise ValueError("app_api_mismatch")
    return lights_app, app_version.APP_VERSION


def settings():
    import board
    import microcontroller
    import node_config
    role = node_config.OVERRIDES.get("radio_role", "consumer")
    role = {"leader": "producer", "follower": "consumer", "off": "producer"}.get(role, role)
    uid = microcontroller.cpu.uid.hex().lower()
    result = {"id": uid, "board": board.board_id, "role": role,
              "api": os.getenv("OTA_API_BASE") or "", "token": os.getenv("OTA_DEVICE_TOKEN") or "",
              "ssid": os.getenv("OTA_WIFI_SSID") or "openwireless.org"}
    if os.getenv("OTA_DEVICE_ID") != uid:
        raise ValueError("device_identity_mismatch")
    if result["board"] not in BOARDS or (result["board"] == BOARDS[1] and role != "consumer"):
        raise ValueError("unsupported_board_role")
    return result


def report_body(store, cfg, version, session, sequence, health=None):
    return {"device_id": cfg["id"], "board": cfg["board"], "role": cfg["role"],
            "version": version, "base_version": BASE_VERSION,
            "circuitpython": ".".join(str(v) for v in sys.implementation.version[:3]),
            "protocol_send": 3, "protocol_receive": [3], "session": session,
            "report_sequence": sequence, "state": store.state["outcome"],
            "deployment_sequence": store.state["floor"], "error": store.state["error"],
            "health": health or {}, "battery": read_battery()}


def nvm_flag(value=None):
    import microcontroller
    nvm = microcontroller.nvm
    if value is not None:
        nvm[:5] = NVM_MARKER + bytes((int(value),))
    return bytes(nvm[:4]) == NVM_MARKER and nvm[4] == 1


def network(store, cfg, version, session, sequence, watchdog, report_only=False, health=None):
    """Run only outside audio/LED processing. Every exit disconnects the AP."""
    import wifi
    import socketpool
    started = time.monotonic()
    deadline = started + 90
    indicator = None
    def service():
        if time.monotonic() >= deadline:
            raise OSError("maintenance_deadline")
        watchdog.feed()
        if indicator is not None:
            indicator.update()
    try:
        indicator = OTAIndicator()
        nvm_flag(True)  # Watchdog/reset in network phase skips it once next boot.
        time.sleep(int.from_bytes(os.urandom(2), "little") / 65535 * 2)
        service()
        wifi.radio.enabled = True
        wifi.radio.connect(cfg["ssid"], timeout=8)
        client = DeviceHTTP(socketpool.SocketPool(wifi.radio), cfg["id"], cfg["token"], cfg["api"])
        body = report_body(store, cfg, version, session, sequence, health)
        result = client.request("report" if report_only else "check-in", service,
                                lambda response: response.json() if response.status == 200 else None,
                                limit=MAX_MANIFEST, body=body)
        if store.state["report_pending"]:
            store.save(dict(store.state, report_pending=False))
        if not report_only and result and result.get("manifest"):
            manifest = validate(result["manifest"], cfg["board"], cfg["role"], body["circuitpython"])
            if manifest["version"] == version:
                return False
            def download(m, f, consume):
                client.request("artifacts/" + m["sha256"] + "/" + f["name"], service,
                               lambda response: consume(response.chunks()), limit=f["size"])
            staged = store.stage(manifest, download, service)
            print("OTA staged=%s version=%s" % (staged, manifest["version"]))
            return staged
        print("OTA check-in complete version=" + version)
    except Exception as error:
        # Never print endpoint response bodies, credentials or raw socket objects.
        print("OTA unavailable: " + type(error).__name__)
    finally:
        try:
            wifi.radio.stop_station()
            gc.collect()
            nvm_flag(False)
        finally:
            if indicator is not None:
                indicator.close()
    return False


class TrialReady(Exception):
    pass


class Health:
    def __init__(self, watchdog, trial):
        self.watchdog = watchdog
        self.trial = trial
        self.started = time.monotonic()
        self.healthy_since = None
        self.checked = -1
        self.frames = 0
        self.summary = {}

    def __call__(self, features, radio):
        self.watchdog.feed()
        self.frames += 1
        now = time.monotonic()
        if now - self.checked < 1:
            return
        self.checked = now
        import math
        from radio_protocol import FIELDS
        if any(not math.isfinite(getattr(features, name)) or not 0 <= getattr(features, name) <= 1
               for name in FIELDS) or any(not math.isfinite(v) or not 0 <= v <= 1 for v in features.spectrum):
            raise ValueError("invalid_audio_features")
        if not features.calibrating:
            if self.healthy_since is None:
                self.healthy_since = now
            self.summary = {"frames": self.frames, "active": features.active,
                            "received": radio.receiver.accepted if radio and radio.receiver else 0,
                            "sent": radio.sent if radio else 0}
            if self.trial and now - self.healthy_since >= TRIAL_SECONDS:
                raise TrialReady()
        if self.trial and now - self.started > 120:
            raise ValueError("trial_health_timeout")


def main():
    import board
    import storage
    import microcontroller
    from watchdog import WatchDogMode
    field = os.getenv("OTA_ENABLED") == "1" and not storage.getmount("/").readonly
    if not field:
        app, version = load_app()
        print("OTA mode=maintenance app=%s base=%s" % (version, BASE_VERSION))
        app.main()
        return
    # Fail back to normal lighting when enrollment is missing; do not network.
    try:
        cfg = settings()
    except ValueError as error:
        print("OTA disabled: " + str(error))
        app, _ = load_app()
        app.main()
        return
    watchdog = microcontroller.watchdog
    watchdog.timeout = 20
    watchdog.mode = WatchDogMode.RESET
    store = UpdateStore()
    generation = store.state["generation"]
    selected = store.select()
    trial = store.state["trial"] is not None
    # Resume lighting first after an interrupted trial or corrupt active slot.
    # Do not immediately exercise Wi-Fi/TLS again following a watchdog reset.
    recovered = store.state["generation"] != generation and not trial
    directory = store.path(selected) if selected else "/recovery"
    with open(directory + "/app_version.py") as f:
        identity = {}
        exec(f.read(), identity)
    version = identity["APP_VERSION"]
    session = os.urandom(8).hex()
    skip = nvm_flag() or recovered
    nvm_flag(False)
    print("OTA app=%s base=%s state=%s" % (version, BASE_VERSION, store.state["outcome"]))
    if not trial and not skip and network(store, cfg, version, session, 1, watchdog):
        microcontroller.reset()
    # A fresh VM ensures no old slot modules survive selection.
    health = Health(watchdog, trial)
    try:
        app, imported_version = load_app(directory)
        if imported_version != version:
            raise ValueError("app_version_mismatch")
        if selected and version != selected["manifest"]["version"]:
            raise ValueError("manifest_version_mismatch")
        app.main(health=health)
        raise RuntimeError("application_returned")
    except TrialReady:
        store.confirm()
        print("OTA confirmed version=" + version)
        network(store, cfg, version, session, 2, watchdog, report_only=True, health=health.summary)
        # Skip the redundant boot check after this deliberate confirmation reset.
        nvm_flag(True)
        microcontroller.reset()
    except Exception as error:
        print("OTA app failed: " + type(error).__name__)
        if selected:
            store.rollback(type(error).__name__, active_failed=not trial)
            nvm_flag(True)
            microcontroller.reset()
        raise
