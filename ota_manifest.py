"""USB-managed release contract, shared by device and host tooling."""
import hashlib

BASE_VERSION = "1.0.5"
# App compatibility is independent of optional USB-base improvements.
APP_MINIMUM_BASE = "1.0.5"  # Sleep telemetry uses the USB-base outbox and uploader.
APP_API = 1
BOARDS = ("unexpectedmaker_feathers2", "adafruit_feather_esp32_v2")
LEGACY_APP_FILES = ("animation.py", "app_version.py", "audio_features.py", "audio_spectrum.py",
             "config.py", "effects.py", "lights_app.py", "radio_protocol.py",
             "sound_reactive.py", "wireless.py")
APP_FILES = LEGACY_APP_FILES[:-1] + ("telemetry.py",) + LEGACY_APP_FILES[-1:]
MAX_FILE = 65536
MAX_TOTAL = 262144
MAX_MANIFEST = 8192
MAX_FILES = 24
REQUIRED_APP_FILES = ("app_version.py", "lights_app.py")
# App files are written only inside an inactive slot. Keep base, identity and
# boot names out of that slot so a release cannot accidentally shadow them.
RESERVED_APP_FILES = ("boot.py", "code.py", "node_config.py", "battery.py",
                      "ota_manifest.py", "ota_store.py", "ota_http.py",
                      "ota_bootstrap.py", "telemetry_store.py", "settings.toml",
                      "secrets.py")


def safe_app_name(name):
    # The slot may hold code or opaque data. A single safe basename keeps both
    # device writes and cloud artifact URLs inside the selected app slot.
    if type(name) is not str or not 3 <= len(name) <= 49:
        return False
    parts = name.split(".")
    if len(parts) != 2:
        return False
    stem, extension = parts
    return (1 <= len(stem) <= 40 and 1 <= len(extension) <= 8
            and "a" <= stem[0] <= "z"
            and all("a" <= c <= "z" or "0" <= c <= "9" or c == "_" for c in stem)
            and all("a" <= c <= "z" or "0" <= c <= "9" for c in extension)
            and name not in RESERVED_APP_FILES)


def sha256(data):
    h = hashlib.new("sha256")
    h.update(data)
    return "".join("%02x" % b for b in h.digest())


def version_tuple(value):
    if type(value) is not str:
        raise ValueError("invalid_version")
    parts = value.split(".")
    if len(parts) != 3 or any(not p.isdigit() or str(int(p)) != p or len(p) > 6 for p in parts):
        raise ValueError("invalid_version")
    return tuple(int(p) for p in parts)


def is_digest(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def bundle_digest(files):
    return sha256("".join("%s:%d:%s\n" % (f["name"], f["size"], f["sha256"])
                          for f in sorted(files, key=lambda f: f["name"])).encode())


def validate(m, board_id=None, role=None, cp_version="10.3.1", require_sequence=True):
    keys = {"schema", "version", "git_commit", "app_api", "minimum_base", "circuitpython",
            "boards", "roles", "protocol_send", "protocol_receive", "files", "sha256"}
    if require_sequence:
        keys.add("sequence")
    if type(m) is not dict or set(m) != keys:
        raise ValueError("manifest_fields")
    if (type(m["schema"]) is not int or m["schema"] != 1 or type(m["app_api"]) is not int
            or m["app_api"] != APP_API or version_tuple(m["minimum_base"]) > version_tuple(BASE_VERSION)
            or m["circuitpython"] != cp_version or m["boards"] != list(BOARDS)
            or m["roles"] != ["producer", "consumer"] or m["protocol_send"] != 3
            or m["protocol_receive"] != [3]):
        raise ValueError("incompatible_manifest")
    version_tuple(m["version"])
    if (type(m["git_commit"]) is not str or len(m["git_commit"]) != 40
            or any(c not in "0123456789abcdef" for c in m["git_commit"])):
        raise ValueError("invalid_commit")
    if board_id is not None and board_id not in m["boards"]:
        raise ValueError("unsupported_board")
    if role is not None and (role not in m["roles"] or
                            (board_id == BOARDS[1] and role != "consumer")):
        raise ValueError("unsupported_role")
    if require_sequence and (type(m["sequence"]) is not int or not 0 < m["sequence"] <= 2147483647):
        raise ValueError("invalid_sequence")
    files = m["files"]
    if type(files) is not list or not len(REQUIRED_APP_FILES) <= len(files) <= MAX_FILES:
        raise ValueError("file_list")
    names = []
    total = 0
    for f in files:
        if type(f) is not dict or set(f) != {"name", "size", "sha256"}:
            raise ValueError("file_fields")
        if (not safe_app_name(f["name"]) or f["name"] in names or type(f["size"]) is not int
                or not 0 < f["size"] <= MAX_FILE or not is_digest(f["sha256"])):
            raise ValueError("invalid_file")
        names.append(f["name"])
        total += f["size"]
    if (any(name not in names for name in REQUIRED_APP_FILES) or total > MAX_TOTAL
            or not is_digest(m["sha256"]) or bundle_digest(files) != m["sha256"]):
        raise ValueError("invalid_bundle")
    return m
