"""USB-managed boot maintenance, isolated app loading, health trial and rollback."""
import gc
import json
import os
import sys
import time

from ota_manifest import APP_API, BASE_VERSION, BOARDS, CONTRACTS, MAX_MANIFEST, validate, valid_protocol, valid_targets
from ota_store import UpdateStore
from ota_http import DeviceHTTP
from battery import read_battery
import hardware
import node_state
import ota_status
from telemetry_store import TelemetryQueue

TRIAL_SECONDS = 30
NVM_MARKER = b"DGO1"  # Reserved bytes 0..4; never store device secrets in NVM.
OTA_PIXEL_COUNT = 32
OTA_PIXEL_BRIGHTNESS = 0.03
OTA_PIXEL_STEP_S = 0.5


class OTAIndicator:
    """One dim pixel advances during network checks or USB maintenance loading.

    This is activity, not a download percentage. Blocking Wi-Fi/TLS calls leave
    the current pixel lit until they return. The pin is released before app.main.
    """
    def __init__(self, color=None, phase="Checking for updates"):
        import board
        import digitalio
        from neopixel_write import neopixel_write
        self.pin = digitalio.DigitalInOut(getattr(board, hardware.profile(board.board_id)["wing"]))
        self.screen = hardware._boot_screen
        self.owns_screen = self.screen is None
        if self.owns_screen:self.screen=hardware.BootScreen()
        self.screen.phase(phase)
        self.write = neopixel_write
        level = int(255 * OTA_PIXEL_BRIGHTNESS)
        self.color = color if color is not None else (level, 0, level)  # GRB cyan.
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
        self.screen.tick()
        now = time.monotonic()
        if now < self.next_step:
            return
        self.pixels[:] = bytes(len(self.pixels))
        self.index = (self.index + 1) % OTA_PIXEL_COUNT
        # GRB: one dim status pixel, independent of the app's brightness.
        self.pixels[self.index * 3:self.index * 3 + 3] = bytes(self.color)
        self.write(self.pin, self.pixels)
        self.next_step = now + OTA_PIXEL_STEP_S

    def close(self):
        if getattr(self,'owns_screen',True):self.screen.close()
        try:
            self.write(self.pin, bytes(len(self.pixels)))
        finally:
            self.pin.deinit()


def load_app(directory="/recovery"):
    # Load node identity before removing root from app import paths. This is
    # trusted code isolation against accidental mixed versions, not a sandbox.
    import node_config
    sys.path[:] = [directory, "/lib"]
    import board
    if board.board_id == hardware.S3:
        import device_setup
        device_setup.ensure_configured()
    import app_version
    import lights_app
    if app_version.APP_API_VERSION != APP_API:
        raise ValueError("app_api_mismatch")
    return lights_app, app_version.APP_VERSION


def settings():
    import board
    import microcontroller
    import node_config
    role = node_state.current().get("radio_role")
    role = {"leader": "producer", "follower": "consumer", "off": "producer"}.get(role, role)
    enrolled_role = os.getenv('OTA_DEVICE_ROLE')
    if enrolled_role and enrolled_role != role:
        raise ValueError('enrolled_role_mismatch')
    if role not in ('producer', 'consumer'):
        raise ValueError('role_not_configured')
    uid = microcontroller.cpu.uid.hex().lower()
    result = {"id": uid, "board": board.board_id, "role": role,
              "api": os.getenv("OTA_API_BASE") or "", "token": os.getenv("OTA_DEVICE_TOKEN") or "",
              "ssid": os.getenv("OTA_WIFI_SSID") or "openwireless.org"}
    if os.getenv("OTA_DEVICE_ID") != uid:
        raise ValueError("device_identity_mismatch")
    if result["board"] not in BOARDS or (result["board"] == BOARDS[1] and role != "consumer"):
        raise ValueError("unsupported_board_role")
    return result


def app_protocol(identity=None):
    identity = identity or {}
    send = identity.get("PROTOCOL_SEND", 3)
    receive = identity.get("PROTOCOL_RECEIVE", (3,))
    if type(receive) not in (tuple, list):
        raise ValueError("invalid_app_protocol")
    receive = list(receive)
    if not valid_protocol(send, receive):
        raise ValueError("invalid_app_protocol")
    return send, receive


def app_targets(identity, schema):
    identity = identity or {}
    boards = identity.get("APP_BOARDS", CONTRACTS[schema][0])
    roles = identity.get("APP_ROLES", ("producer", "consumer"))
    if type(boards) not in (tuple, list) or type(roles) not in (tuple, list):
        raise ValueError("invalid_app_targets")
    boards, roles = list(boards), list(roles)
    if not valid_targets(boards, CONTRACTS[schema][0]) or not valid_targets(roles, ("producer", "consumer")):
        raise ValueError("invalid_app_targets")
    return boards, roles


def validate_app_manifest(manifest, identity, board_id, role, cp_version):
    validate(manifest, board_id, role, cp_version)
    boards, roles = app_targets(identity, manifest["schema"])
    send, receive = app_protocol(identity)
    if manifest["boards"] != boards or manifest["roles"] != roles:
        raise ValueError("manifest_targets_mismatch")
    if manifest["protocol_send"] != send or manifest["protocol_receive"] != receive:
        raise ValueError("manifest_protocol_mismatch")
    return manifest


def report_body(store, cfg, version, session, sequence, health=None, identity=None):
    protocol_send, protocol_receive = app_protocol(identity)
    return {"device_id": cfg["id"], "board": cfg["board"], "role": cfg["role"],
            "version": version, "base_version": BASE_VERSION,
            "circuitpython": ".".join(str(v) for v in sys.implementation.version[:3]),
            "protocol_send": protocol_send, "protocol_receive": protocol_receive, "session": session,
            "report_sequence": sequence, "state": store.state["outcome"],
            "deployment_sequence": store.state["floor"], "error": store.state["error"],
            "health": health or {}, "battery": read_battery()}


def nvm_flag(value=None):
    import microcontroller
    nvm = microcontroller.nvm
    if value is not None:
        nvm[:5] = NVM_MARKER + bytes((int(value),))
    return bytes(nvm[:4]) == NVM_MARKER and nvm[4] == 1


def upload_telemetry(client, service, limit=1):
    try:
        os.stat("/telemetry")
    except OSError:
        return 0
    queue = TelemetryQueue()
    if not queue.has_pending():
        return 0
    return queue.flush(lambda batch: client.request(
        "telemetry", service, lambda response: response.json(), limit=256, body=batch), limit)


def telemetry_on_sleep(record, cfg, watchdog):
    """Persist after app cleanup, then try one bounded HTTPS upload."""
    try:
        queue = TelemetryQueue()
        queue.enqueue(cfg["id"], record)
    except Exception as error:
        print("TELEMETRY storage unavailable: " + type(error).__name__)
        return
    import wifi
    import socketpool
    deadline = time.monotonic() + 18
    def service():
        if time.monotonic() >= deadline:
            raise OSError("telemetry_deadline")
        watchdog.feed()
    try:
        nvm_flag(True)
        wifi.radio.enabled = True
        service()
        wifi.radio.connect(cfg["ssid"], timeout=8)
        client = DeviceHTTP(socketpool.SocketPool(wifi.radio), cfg["id"], cfg["token"], cfg["api"])
        upload_telemetry(client, service)
    except Exception as error:
        print("TELEMETRY queued for next boot: " + type(error).__name__)
    finally:
        try:
            wifi.radio.stop_station()
        finally:
            nvm_flag(False)


def network(store, cfg, version, session, sequence, watchdog, report_only=False, health=None, identity=None):
    """Run only outside audio/LED processing. Every exit disconnects the AP."""
    import wifi
    import socketpool
    if not report_only:ota_status.reset('checking')
    started = time.monotonic()
    deadline = started + 90
    indicator = None
    phase = 'startup'
    def service():
        if time.monotonic() >= deadline:
            raise OSError("maintenance_deadline")
        watchdog.feed()
        if indicator is not None:
            indicator.update()
    try:
        indicator = OTAIndicator()
        indicator.screen.version(version)
        nvm_flag(True)  # Watchdog/reset in network phase skips it once next boot.
        time.sleep(int.from_bytes(os.urandom(2), "little") / 65535 * 2)
        service()
        wifi.radio.enabled = True
        if indicator:indicator.screen.phase("Joining Wi-Fi")
        phase = 'wifi'
        wifi.radio.connect(cfg["ssid"], timeout=8)
        if indicator:indicator.screen.phase("Checking updates")
        phase = 'http'
        client = DeviceHTTP(socketpool.SocketPool(wifi.radio), cfg["id"], cfg["token"], cfg["api"])
        body = report_body(store, cfg, version, session, sequence, health, identity)
        result = client.request("report" if report_only else "check-in", service,
                                lambda response: response.json() if response.status == 200 else None,
                                limit=MAX_MANIFEST, body=body)
        if not report_only:ota_status.accept(result, version)
        if store.state["report_pending"]:
            store.save(dict(store.state, report_pending=False))
        try:
            telemetry_deadline = time.monotonic() + 12
            def telemetry_service():
                if time.monotonic() >= telemetry_deadline:
                    raise OSError("telemetry_deadline")
                service()
            upload_telemetry(client, telemetry_service)
        except Exception as error:
            print("TELEMETRY boot retry deferred: " + type(error).__name__)
        if not report_only and result and result.get("manifest"):
            manifest = validate(result["manifest"], cfg["board"], cfg["role"], body["circuitpython"])
            if manifest["version"] == version:
                return False
            def download(m, f, consume):
                if indicator:indicator.screen.phase("Download " + f["name"])
                client.request("artifacts/" + m["sha256"] + "/" + f["name"], service,
                               lambda response: consume(response.chunks()), limit=f["size"])
            staged = store.stage(manifest, download, service)
            print("OTA staged=%s version=%s" % (staged, manifest["version"]))
            return staged
        print("OTA check-in complete version=" + version)
    except Exception as error:
        # Never print endpoint response bodies, credentials or raw socket objects.
        reason = ota_status.failure_reason(error, phase)
        if not report_only:ota_status.reset('unavailable', reason)
        print("OTA unavailable: %s reason=%s" % (type(error).__name__, reason))
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
    screen=hardware.start_boot()
    try:
        _main(screen)
    finally:
        hardware.close_boot()


def selected_identity(directory):
    # Read only the selected slot identity, without importing app modules early.
    with open(directory + '/app_version.py') as f:
        identity={}
        exec(f.read(),identity)
    return identity


def selected_version(directory):
    return selected_identity(directory)['APP_VERSION']


def start_app(directory,screen):
    screen.version(selected_version(directory))
    screen.phase('Loading application')
    app,version=load_app(directory)
    screen.phase('Listening for producer' if app.CONFIG.radio_role=='follower' else 'Starting audio')
    return app,version


def _main(screen):
    import board
    import storage
    import microcontroller
    from watchdog import WatchDogMode
    ota_status.reset()
    enabled = os.getenv("OTA_ENABLED") == "1"
    field = enabled and not storage.getmount("/").readonly
    if not field:
        ota_status.reset('maintenance' if enabled else 'disabled')
        if enabled:
            screen.maintenance()
        indicator = OTAIndicator(color=(3,8,0),phase='Loading application') if enabled else None
        try:
            app, version = start_app('/recovery',screen)
        finally:
            if indicator:indicator.close()
        print("OTA mode=maintenance app=%s base=%s" % (version, BASE_VERSION))
        app.main()
        return
    # Fail back to normal lighting when enrollment is missing; do not network.
    try:
        cfg = settings()
    except ValueError as error:
        ota_status.reset('disabled')
        print("OTA disabled: " + str(error))
        app, _ = start_app('/recovery',screen)
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
    identity = selected_identity(directory)
    version = identity['APP_VERSION']
    screen.version(version)
    session = os.urandom(8).hex()
    skip = nvm_flag() or recovered
    nvm_flag(False)
    print("OTA app=%s base=%s state=%s" % (version, BASE_VERSION, store.state["outcome"]))
    if not trial and not skip and network(store, cfg, version, session, 1, watchdog, identity=identity):
        microcontroller.reset()
    # A fresh VM ensures no old slot modules survive selection.
    health = Health(watchdog, trial)
    try:
        app, imported_version = start_app(directory,screen)
        if imported_version != version:
            raise ValueError("app_version_mismatch")
        if selected and version != selected["manifest"]["version"]:
            raise ValueError("manifest_version_mismatch")
        if selected:
            validate_app_manifest(selected["manifest"], identity, cfg["board"], cfg["role"],
                                  ".".join(str(v) for v in sys.implementation.version[:3]))
        if getattr(app, "TELEMETRY_API", 0) == 1:
            app.main(health=health, on_sleep=lambda record: telemetry_on_sleep(record, cfg, watchdog))
        else:
            app.main(health=health)
        raise RuntimeError("application_returned")
    except TrialReady:
        store.confirm()
        print("OTA confirmed version=" + version)
        network(store, cfg, version, session, 2, watchdog, report_only=True,
                health=health.summary, identity=identity)
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
