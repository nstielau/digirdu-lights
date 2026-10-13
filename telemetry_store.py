"""Small durable RF telemetry outbox in the USB-managed base.

Only call after the music loop has unwound, or during boot maintenance.
"""
import json
import os

MAX_BATCH_BYTES = 49152
MAX_BATCHES = 4
ATTEMPT_STATES = ("queued", "uploaded", "failed")


def read_attempt(root="/telemetry"):
    """Read the last bounded upload result without changing filesystem ownership."""
    try:
        with open(root + "/status.json") as stream:
            raw = stream.read(129)
        if len(raw) > 128:
            return None
        record = json.loads(raw)
        if (type(record) is not dict or set(record) != {"schema", "state", "reason", "pending"}
                or record["schema"] != 1 or record["state"] not in ATTEMPT_STATES
                or type(record["reason"]) is not str or len(record["reason"]) > 16
                or type(record["pending"]) is not int or not 0 <= record["pending"] <= MAX_BATCHES):
            return None
        return {key: record[key] for key in ("state", "reason", "pending")}
    except (OSError, ValueError, TypeError):
        return None


def write_attempt(state, reason="", pending=0, root="/telemetry", sync=None):
    """Persist one diagnostic after sleep/boot networking, never in the music loop."""
    if (state not in ATTEMPT_STATES or type(reason) is not str or len(reason) > 16
            or type(pending) is not int or not 0 <= pending <= MAX_BATCHES):
        raise ValueError("invalid_telemetry_attempt")
    synchronize = sync if sync is not None else os.sync
    raw = json.dumps({"schema": 1, "state": state, "reason": reason,
                      "pending": pending}, separators=(",", ":"))
    temporary = root + "/status.json.tmp"
    with open(temporary, "w") as stream:
        stream.write(raw)
        stream.flush()
    synchronize()
    os.rename(temporary, root + "/status.json")
    synchronize()


class TelemetryQueue:
    def __init__(self, root="/telemetry", sync=None):
        self.root = root
        self.sync = sync if sync is not None else os.sync
        try:
            os.mkdir(root)
        except OSError:
            os.listdir(root)  # Propagate if the path is inaccessible or a file.

    def _names(self):
        names = []
        for name in os.listdir(self.root):
            if (len(name) == 30 and name[8] == "-" and name.endswith(".json")
                    and name[:8].isdigit()
                    and all(c in "0123456789abcdef" for c in name[9:25])):
                names.append(name)
        return sorted(names)

    def _read(self, name):
        try:
            with open(self.root + "/" + name) as f:
                raw = f.read(MAX_BATCH_BYTES + 1)
            if len(raw.encode()) > MAX_BATCH_BYTES:
                return None
            batch = json.loads(raw)
            if (type(batch) is not dict or batch.get("batch_id") != name[9:25]
                    or type(batch.get("device_id")) is not str or type(batch.get("record")) is not dict):
                return None
            return batch
        except (OSError, ValueError):
            return None

    def pending(self):
        batches = []
        for name in self._names():
            batch = self._read(name)
            if batch is not None:
                batches.append(batch)
        return batches

    def has_pending(self):
        return bool(self._names())

    def enqueue(self, device_id, record):
        names = self._names()
        number = int(names[-1][:8]) + 1 if names else 1
        batch_id = os.urandom(8).hex()
        batch = {"schema": 1, "device_id": device_id, "batch_id": batch_id, "record": record}
        raw = json.dumps(batch, separators=(",", ":")).encode()
        if len(raw) > MAX_BATCH_BYTES:
            raise ValueError("telemetry_batch_too_large")
        name = "%08d-%s.json" % (number, batch_id)
        temporary = self.root + "/" + name + ".tmp"
        with open(temporary, "wb") as f:
            f.write(raw)
            f.flush()
        self.sync()
        os.rename(temporary, self.root + "/" + name)
        self.sync()
        for old in (names + [name])[:-MAX_BATCHES]:
            os.remove(self.root + "/" + old)
        if len(names) + 1 > MAX_BATCHES:
            self.sync()
        return batch

    def flush(self, upload, limit=1):
        acknowledged = 0
        attempted = 0
        for name in self._names():
            batch = self._read(name)
            if batch is None:
                continue
            if attempted >= limit:
                break
            attempted += 1
            response = upload(batch)
            if type(response) is not dict or response.get("accepted") != batch["batch_id"]:
                break
            os.remove(self.root + "/" + name)
            self.sync()
            acknowledged += 1
        return acknowledged
