"""Two complete application slots and alternating checksummed selection journals.

OTA never overwrites recovery or the selected active slot. FAT corruption may
still require USB recovery; these are not independent flash partitions.
"""
import hashlib
import json
import os

from ota_manifest import validate, sha256, MAX_FILE, MAX_MANIFEST


def file_info(path):
    h = hashlib.new("sha256")
    size = 0
    with open(path, "rb") as source:
        while True:
            chunk = source.read(1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE:
                raise ValueError("file_too_large")
            h.update(chunk)
    return size, "".join("%02x" % b for b in h.digest())


class UpdateStore:
    def __init__(self, root="/ota", sync=None):
        self.root = root
        self.sync = sync or os.sync
        self.state = {"generation": 0, "active": None, "trial": None, "floor": 0,
                      "outcome": "recovery", "error": "", "report_pending": False}
        for index in (0, 1):
            try:
                with open(root + "/state%d.json" % index) as f:
                    envelope = json.loads(f.read(MAX_MANIFEST * 3))
                body = envelope["body"]
                if sha256(body.encode()) != envelope["sha256"]:
                    continue
                state = json.loads(body)
                if (set(state) != set(self.state) or type(state["generation"]) is not int
                        or state["generation"] <= self.state["generation"]
                        or type(state["floor"]) is not int or state["floor"] < 0
                        or state["outcome"] not in ("recovery", "current", "trial", "rolled_back")
                        or type(state["error"]) is not str or len(state["error"]) > 80
                        or type(state["report_pending"]) is not bool):
                    continue
                for item in (state["active"], state["trial"]):
                    if item is not None:
                        if (set(item) != {"slot", "manifest", "started"}
                                or type(item["slot"]) is not int or item["slot"] not in (0, 1)
                                or type(item["started"]) is not bool):
                            raise ValueError("invalid_slot")
                        validate(item["manifest"])
                        if item["manifest"]["sequence"] > state["floor"]:
                            raise ValueError("invalid_floor")
                if state["active"] and state["trial"] and state["active"]["slot"] == state["trial"]["slot"]:
                    raise ValueError("overlapping_slots")
                self.state = state
            except (OSError, ValueError, KeyError, TypeError):
                pass

    def save(self, state):
        try:
            os.mkdir(self.root)
        except OSError:
            os.stat(self.root)
        state = dict(state)
        state["generation"] = self.state["generation"] + 1
        body = json.dumps(state)
        path = self.root + "/state%d.json" % (state["generation"] % 2)
        with open(path, "w") as f:
            f.write(json.dumps({"body": body, "sha256": sha256(body.encode())}))
            f.flush()
        self.sync()
        self.state = state

    def path(self, item):
        return self.root + "/slot%d" % item["slot"]

    def verified(self, item):
        try:
            m = validate(item["manifest"])
            return all(file_info(self.path(item) + "/" + f["name"]) == (f["size"], f["sha256"])
                       for f in m["files"])
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def select(self):
        trial = self.state["trial"]
        if trial:
            if trial["started"] or not self.verified(trial):
                self.rollback("unconfirmed_boot")
            else:
                trial = dict(trial, started=True)
                self.save(dict(self.state, trial=trial))
                return trial
        active = self.state["active"]
        if active and self.verified(active):
            return active
        if active:
            self.save(dict(self.state, active=None, outcome="rolled_back", error="active_corrupt", report_pending=True))
        return None

    def stage(self, manifest, download, service=lambda: None):
        validate(manifest)
        if self.state["trial"] or manifest["sequence"] <= self.state["floor"]:
            return False
        try:
            os.mkdir(self.root)
        except OSError:
            os.stat(self.root)
        active = self.state["active"]
        slot = 1 - active["slot"] if active else 0
        item = {"slot": slot, "manifest": manifest, "started": False}
        path = self.path(item)
        try:
            os.mkdir(path)
        except OSError:
            os.stat(path)
        # Only the inactive slot is disposable; never traverse caller paths.
        for name in os.listdir(path):
            os.remove(path + "/" + name)
        stat = os.statvfs(self.root)
        if stat[0] * stat[4] < sum(f["size"] for f in manifest["files"]) + 32768:
            raise OSError("insufficient_space")
        for f in manifest["files"]:
            service()
            destination = path + "/" + f["name"]
            def consume(chunks):
                count = 0
                with open(destination, "wb") as target:
                    for chunk in chunks:
                        service()
                        count += len(chunk)
                        if count > f["size"]:
                            raise ValueError("file_too_large")
                        target.write(chunk)
                    target.flush()
                if file_info(destination) != (f["size"], f["sha256"]):
                    raise ValueError("file_digest_mismatch")
            download(manifest, f, consume)
        self.sync()
        if not self.verified(item):
            raise ValueError("bundle_verify_failed")
        service()
        self.save(dict(self.state, trial=item, floor=manifest["sequence"], outcome="trial", error=""))
        return True

    def confirm(self):
        if not self.state["trial"]:
            raise ValueError("no_trial")
        self.save(dict(self.state, active=self.state["trial"], trial=None,
                       outcome="current", error="", report_pending=True))

    def rollback(self, error="trial_failed", active_failed=False):
        self.save(dict(self.state, trial=None, active=None if active_failed else self.state["active"],
                       outcome="rolled_back", error=error[:80], report_pending=True))
