"""Pure semantic events derived from normalized audio feature frames."""

import math

from audio_features import clamp


class DroneEventConfig:
    def __init__(self, on_threshold=0.45, off_threshold=0.25,
                 start_hold_s=0.12, stop_hold_s=0.30):
        values = (on_threshold, off_threshold, start_hold_s, stop_hold_s)
        if not all(isinstance(value, (int, float)) and math.isfinite(value)
                   for value in values):
            raise ValueError("Drone event configuration must be finite numbers")
        if not 0.0 <= off_threshold < on_threshold <= 1.0:
            raise ValueError("Drone thresholds must form a normalized hysteresis")
        if start_hold_s <= 0 or stop_hold_s <= 0:
            raise ValueError("Drone hold times must be positive")
        self.on_threshold = on_threshold
        self.off_threshold = off_threshold
        self.start_hold_s = start_hold_s
        self.stop_hold_s = stop_hold_s


class SemanticEventDetector:
    def __init__(self, drone_config=None):
        self.config = drone_config or DroneEventConfig()
        self._last_time_ms = None
        self._finished = False
        self._drone_active = False
        self._above_s = 0.0
        self._below_s = 0.0
        self._previous_high = False
        self._previous_low = False
        self._drone_confidence = 0.0

    @staticmethod
    def _validate_time(time_ms, previous):
        if isinstance(time_ms, bool) or not isinstance(time_ms, int):
            raise ValueError("time_ms must be an integer")
        if previous is not None and time_ms <= previous:
            raise ValueError("time_ms must increase")

    @staticmethod
    def _event(event_type, time_ms, confidence):
        return {
            "type": event_type,
            "time_ms": time_ms,
            "confidence": clamp(confidence),
        }

    def update(self, features, time_ms):
        if self._finished:
            raise ValueError("Cannot update a finished detector")
        self._validate_time(time_ms, self._last_time_ms)
        elapsed_s = (time_ms - self._last_time_ms) / 1000.0 if self._last_time_ms is not None else 0.0
        self._last_time_ms = time_ms

        events = []
        if getattr(features, "yellEvent", False):
            events.append(self._event("yell", time_ms, getattr(features, "vocal", 0.0)))
        if getattr(features, "attackEvent", False):
            events.append(self._event("transient", time_ms, getattr(features, "attack", 0.0)))

        drone = getattr(features, "drone", 0.0)
        self._drone_confidence = clamp(drone)
        if drone > self.config.on_threshold:
            was_high = self._previous_high
            self._above_s += elapsed_s
            self._below_s = 0.0
            if (not self._drone_active and was_high and
                    self._above_s >= self.config.start_hold_s):
                self._drone_active = True
                self._above_s = 0.0
                events.append(self._event("drone_start", time_ms, drone))
            self._previous_high = True
            self._previous_low = False
        elif drone < self.config.off_threshold:
            was_low = self._previous_low
            self._below_s += elapsed_s
            self._above_s = 0.0
            if (self._drone_active and was_low and
                    self._below_s >= self.config.stop_hold_s):
                self._drone_active = False
                self._below_s = 0.0
                events.append(self._event("drone_stop", time_ms, drone))
            self._previous_high = False
            self._previous_low = True
        else:
            self._above_s = 0.0
            self._below_s = 0.0
            self._previous_high = False
            self._previous_low = False

        return tuple(events)

    def finish(self, time_ms):
        if self._finished:
            return ()
        self._validate_time(time_ms, self._last_time_ms)
        self._last_time_ms = time_ms
        self._finished = True
        if not self._drone_active:
            return ()
        self._drone_active = False
        return (self._event("drone_stop", time_ms, self._drone_confidence),)
