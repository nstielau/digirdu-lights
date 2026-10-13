"""Bounded RAM-only ESP-NOW flight recorder; no I/O in the music loop."""

WINDOW_BITS = 256
WINDOW_BYTES = WINDOW_BITS // 8


class TelemetryRecorder:
    def __init__(self, role, boot_id, max_windows=112):
        if role not in ("producer", "consumer") or not 1 <= max_windows <= 112:
            raise ValueError("invalid_telemetry_config")
        self.role = role
        self.boot_id = boot_id
        self.max_windows = max_windows
        self.windows = []
        self.session = self.last_sequence = None
        self.cycle = 0
        self.epoch_uncertain = False
        self.truncated_windows = 0
        self.counts = {"features": 0, "controls": 0, "skipped": 0,
                       "rejected": 0, "native_drops": 0, "link_losses": 0,
                       "audio_overruns": 0, "audio_discontinuities": 0}
        self.native_count = None
        self.lost = False
        self.rssi_min = self.rssi_max = None
        self.rssi_sum = self.rssi_count = 0

    def _window(self, session, sequence):
        if session != self.session:
            self.session = session
            self.last_sequence = None
            self.cycle = 0
            if self.role == "consumer" and sequence != 1:
                self.epoch_uncertain = True
        elif self.last_sequence is not None and sequence < self.last_sequence:
            self.cycle += 1
        self.last_sequence = sequence
        extended = self.cycle * 65536 + sequence
        base = extended & ~(WINDOW_BITS - 1)
        if self.windows and self.windows[-1]["session"] == session and self.windows[-1]["base"] == base:
            return self.windows[-1], extended - base
        window = {"session": session, "base": base,
                  "received": bytearray(WINDOW_BYTES), "attempted": bytearray(WINDOW_BYTES),
                  "delivered": bytearray(WINDOW_BYTES), "failed": bytearray(WINDOW_BYTES),
                  "controls": bytearray(WINDOW_BYTES)}
        self.windows.append(window)
        if len(self.windows) > self.max_windows:
            self.windows.pop(0)
            self.truncated_windows += 1
        return window, extended - base

    @staticmethod
    def _mark(window, name, offset):
        window[name][offset >> 3] |= 1 << (offset & 7)

    def received(self, session, sequence, rssi, control):
        window, offset = self._window(session, sequence)
        self._mark(window, "controls" if control else "received", offset)
        self.counts["controls" if control else "features"] += 1
        if type(rssi) is int and -128 <= rssi <= 0:
            self.rssi_min = rssi if self.rssi_min is None else min(self.rssi_min, rssi)
            self.rssi_max = rssi if self.rssi_max is None else max(self.rssi_max, rssi)
            self.rssi_sum += rssi
            self.rssi_count += 1

    def attempted(self, session, sequence, control):
        window, offset = self._window(session, sequence)
        self._mark(window, "attempted", offset)
        if control:
            self._mark(window, "controls", offset)
        self.counts["controls" if control else "features"] += 1

    def completed(self, session, sequence, success):
        # A send completion belongs to the previous pending packet and may
        # arrive just as a new 256-sequence window begins.
        for window in reversed(self.windows):
            extended = (window["base"] // 65536) * 65536 + sequence
            if window["session"] == session and window["base"] <= extended < window["base"] + WINDOW_BITS:
                self._mark(window, "delivered" if success else "failed",
                           extended - window["base"])
                return

    def skipped(self):
        self.counts["skipped"] += 1

    def audio_overrun(self):
        self.counts["audio_overruns"] += 1

    def audio_discontinuity(self):
        self.counts["audio_discontinuities"] += 1

    def rejected(self):
        self.counts["rejected"] += 1

    def native_failures(self, current):
        if self.native_count is not None:
            self.counts["native_drops"] += (current - self.native_count) & 0xffffffff
        self.native_count = current

    def link_lost(self, lost):
        if lost and not self.lost:
            self.counts["link_losses"] += 1
        self.lost = lost

    def snapshot(self):
        windows = []
        for window in self.windows:
            windows.append({key: bytes(value).hex() if isinstance(value, bytearray) else value
                            for key, value in window.items()})
        return {"schema": 1, "role": self.role, "boot_id": self.boot_id,
                "windows": windows, "counts": dict(self.counts),
                "truncated_windows": self.truncated_windows,
                "epoch_uncertain": self.epoch_uncertain,
                "rssi": None if not self.rssi_count else {
                    "min": self.rssi_min, "max": self.rssi_max,
                    "mean": round(self.rssi_sum / self.rssi_count)}}
