"""Layered culvert light field, independent of GPIO and audio capture."""

import math

from audio_features import clamp
from audio_spectrum import np
from effects import PALETTES, effect_indicator_pixels


def hsv(hue, saturation, value):
    """Return linear RGB floats without a CircuitPython-only dependency."""
    h = (hue % 1.0) * 6
    sector = int(h)
    fraction = h - sector
    p = value * (1 - saturation)
    q = value * (1 - saturation * fraction)
    t = value * (1 - saturation * (1 - fraction))
    return ((value, t, p), (q, value, p), (p, value, t),
            (p, q, value), (t, p, value), (value, p, q))[sector]


class CulvertAnimation:
    def __init__(self, config):
        self.c = config
        self.positions = config.pixel_positions or tuple(
            (-1 + 2 * i / (config.pixel_count - 1), 0.0) for i in range(config.pixel_count))
        self.x = np.array([p[0] for p in self.positions])
        self.angle = np.array([p[1] for p in self.positions])
        delta = self.x - config.origin
        self.distance = np.maximum(delta, -delta)
        self.trails = [np.zeros(config.pixel_count) for _ in range(3)]
        # Fixed-size pool: no unbounded event list during sustained playing.
        self.pulses = [[100.0, 0.0, 0.0] for _ in range(config.max_pulses)]
        self.next_pulse = 0
        self.phase = self.time = 0.0
        self.effect = config.effect_index
        self.flash = 0.0
        self.indicator_remaining = 0.0
        self.indicator_pixels = None
        self.pixels = np.zeros(config.pixel_count * 3, dtype=np.uint8)

    def set_effect(self, effect):
        if not 0 <= effect < len(PALETTES):
            raise ValueError("Unknown effect")
        if effect != self.effect:
            self.effect = effect
            self.flash = 0.0
            self.indicator_pixels = effect_indicator_pixels(effect, self.c)
            self.indicator_remaining = (self.c.effect_indicator_s
                                        if self.indicator_pixels is not None else 0.0)

    def _pulse(self, strength, vocal, age=0.0):
        pulse = self.pulses[self.next_pulse]
        pulse[:] = (age, strength, float(vocal))
        self.next_pulse = (self.next_pulse + 1) % len(self.pulses)

    def render(self, features, dt):
        c, f = self.c, features
        responsive = self.effect == 0
        offset, hue_scale, cycles, field_level, texture_level, width_scale = PALETTES[self.effect]
        self.time += dt
        self.phase = (self.phase + dt * (c.base_speed + c.harmonic_speed * f.harmonics)) % 1
        for pulse in self.pulses:
            pulse[0] += dt
        if f.attackEvent:
            self._pulse(f.attack, False, f.attackAge)
        if f.yellEvent:
            self._pulse(max(f.vocal, 0.7), True, f.yellAge)
        self.flash *= math.exp(-dt / c.responsive_flash_s)
        if responsive:
            # Keep the transient age consistent when a receiver catches up.
            if f.attackEvent:
                self.flash = max(self.flash, f.attack * c.responsive_flash_gain *
                                 math.exp(-f.attackAge / c.responsive_flash_s))
            if f.yellEvent:
                self.flash = max(self.flash, max(f.vocal, 0.7) * c.responsive_flash_gain *
                                 math.exp(-f.yellAge / c.responsive_flash_s))
        trail_decay = math.exp(-dt / (c.responsive_trail_s if responsive else c.trail_s))
        hue = c.base_hue + offset + c.timbre_hue_span * hue_scale * f.timbrePosition
        if responsive:
            atmosphere = max(f.drone * 0.65,
                             c.responsive_volume_gain * clamp(f.volume) ** c.responsive_volume_curve,
                             f.decay * c.responsive_decay_level)
        else:
            atmosphere = max(f.drone * 0.65, f.volume * 0.12, f.decay * 0.32)
        wave = 0.5 + 0.5 * np.sin(2 * math.pi *
                (self.distance * (c.wave_cycles * cycles + f.harmonics) - self.phase + self.angle))
        # All per-pixel trigonometry runs in native ulab, not Python loops.
        field = atmosphere * field_level * (0.45 + 0.55 * wave)
        texture = (0.5 + 0.5 * np.sin(self.x * 31 + self.time * 7 +
                   np.sin(self.angle * 17 + self.time * 11))) * f.growl * c.growl_texture * texture_level
        ribbon = np.maximum(0.0, np.sin(self.distance * 8 - self.time * 3 + self.angle * 6.28))
        ribbon *= ribbon
        ribbon *= ribbon
        ribbon *= f.vocal * 0.6
        base_rgb = hsv(hue, 0.85, 1.0)
        growl_rgb = hsv(hue + 0.42, 0.95, 1.0)
        vocal_rgb = hsv(hue + 0.18, 0.45, 1.0)
        channels = [field * base_rgb[i] + texture * growl_rgb[i] + ribbon * vocal_rgb[i] +
                    (self.flash if responsive else 0.0)
                    for i in range(3)]
        for age, strength, vocal in self.pulses:
            if strength <= 0 or age * c.pulse_speed > 2.0 + c.pulse_width:
                continue
            width = c.pulse_width * (1 + vocal) * width_scale
            delta = self.distance - age * c.pulse_speed
            front = np.maximum(0.0, 1 - np.maximum(delta, -delta) * (1.0 / width))
            front *= strength * math.exp(-age / c.pulse_decay_s)
            rgb = hsv(hue + vocal * 0.2, 0.15 if vocal else 0.4, 1.0)
            for channel in range(3):
                channels[channel] += front * rgb[channel]
        for channel in range(3):
            self.trails[channel] = np.maximum(np.minimum(channels[channel], 1.0),
                                              self.trails[channel] * trail_decay)
        # Native strided assignment interleaves GRB and casts to uint8.
        self.pixels[0::3] = self.trails[1] * (c.brightness * 255)
        self.pixels[1::3] = self.trails[0] * (c.brightness * 255)
        self.pixels[2::3] = self.trails[2] * (c.brightness * 255)
        # Overlay only the output. Audio, scene time, pulses and radio continue.
        if self.indicator_remaining > 0:
            self.indicator_remaining = max(0.0, self.indicator_remaining - dt)
            if self.indicator_remaining > 0:
                return self.indicator_pixels
        return self.pixels.tobytes()
