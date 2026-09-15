"""Pure signal measurements and rainbow motion, shared by app and host checks."""

import math


def measure(samples, count):
    """Return DC-removed RMS, peak amplitude, and sample span (16-bit units)."""
    if count < 1:
        raise ValueError("No microphone samples received")
    mean = sum(samples[index] for index in range(count)) / count
    energy = 0.0
    peak = 0.0
    low = high = samples[0]
    for index in range(count):
        value = samples[index]
        centered = value - mean
        energy += centered * centered
        peak = max(peak, abs(centered))
        low = min(low, value)
        high = max(high, value)
    return math.sqrt(energy / count), peak, high - low


class RainbowMotion:
    """Volume speeds up hue motion; sudden increases trigger a timed hue jump."""

    def __init__(self, noise_floor, gain=0.008, beat_ratio=2.5, min_beat=60):
        self.noise_floor = max(noise_floor, 1.0)
        self.gain = gain
        self.beat_ratio = beat_ratio
        self.min_beat = min_beat
        self.average = self.noise_floor
        self.envelope = 0.0
        self.phase = 0.0
        self.last_beat = -1.0
        self.beats = 0

    def update(self, rms, now, elapsed):
        level = max(0.0, rms - self.noise_floor * 1.5)
        target = min(1.0, level * self.gain)
        self.envelope = max(target, self.envelope * math.exp(-elapsed / 0.25))
        beat = (rms > max(self.min_beat, self.average * self.beat_ratio,
                          self.noise_floor * 4) and now - self.last_beat > 0.20)
        if beat:
            self.phase += 40
            self.last_beat = now
            self.beats += 1
        self.average += (rms - self.average) * min(1.0, elapsed / 0.5)
        speed = 12 + 220 * self.envelope
        self.phase = (self.phase + speed * elapsed) % 256
        return self.phase, speed, beat
