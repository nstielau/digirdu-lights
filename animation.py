"""Layered culvert light field, independent of GPIO and audio capture."""

import math

from audio_features import clamp, scale, smooth
from audio_spectrum import np
from effects import PALETTES, effect_indicator_pixels, spectrum_frequency, battery_pixels


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
        self.attack_bloom = self.yell_bloom = 0.0
        self.chroma_position = self.chroma_volume = 0.0
        self.chroma_centers = tuple(math.sqrt(a * b) for a, b in
                                    zip(config.spectrum_edges, config.spectrum_edges[1:]))
        self.chroma_log_low = math.log(config.chroma_frequency_hz[0])
        self.chroma_log_span = math.log(config.chroma_frequency_hz[1]) - self.chroma_log_low
        self.effect = config.effect_index
        self.battery_voltage = None
        self.indicator_remaining = 0.0
        self.indicator_pixels = None
        # Factory progressive rows, top -> bottom; repeat for complete wings.
        self.spectrum_colors = tuple(hsv(x / 10.0, 1.0, config.brightness * 255)
                                     for x in range(8))
        self.pixels = np.zeros(config.pixel_count * 3, dtype=np.uint8)

    def set_effect(self, effect):
        if not 0 <= effect < len(PALETTES):
            raise ValueError("Unknown effect")
        if effect != self.effect:
            self.effect = effect
            self.indicator_pixels = effect_indicator_pixels(effect, self.c)
            self.indicator_remaining = (self.c.effect_indicator_s
                                        if self.indicator_pixels is not None else 0.0)

    def _pulse(self, strength, vocal, age=0.0):
        pulse = self.pulses[self.next_pulse]
        pulse[:] = (age, strength, float(vocal))
        self.next_pulse = (self.next_pulse + 1) % len(self.pulses)

    def render(self, features, dt):
        c, f = self.c, features
        offset, hue_scale, cycles, field_level, texture_level, width_scale = PALETTES[self.effect]
        self.time += dt
        self.phase = (self.phase + dt * (c.base_speed + c.harmonic_speed * f.harmonics)) % 1
        for pulse in self.pulses:
            pulse[0] += dt
        self.attack_bloom *= math.exp(-dt / c.attack_bloom_s)
        self.yell_bloom *= math.exp(-dt / c.yell_bloom_s)
        if f.attackEvent:
            self._pulse(f.attack, False, f.attackAge)
            self.attack_bloom = max(self.attack_bloom,
                                    f.attack * math.exp(-f.attackAge / c.attack_bloom_s))
        if f.yellEvent:
            self._pulse(max(f.vocal, 0.7), True, f.yellAge)
            self.yell_bloom = max(self.yell_bloom,
                                  max(f.vocal, 0.7) * math.exp(-f.yellAge / c.yell_bloom_s))
        # Track Chroma even under another effect so switching has no stale hue.
        self._update_chroma(f, dt)
        if self.effect == 5:
            return self._overlay(battery_pixels(self.battery_voltage, c), dt)
        if self.effect == 4:
            low, high = c.chroma_hue_range
            rgb = hsv(low + (high - low) * self.chroma_position, 1.0,
                      self.chroma_volume * c.brightness * 255)
            color = bytes((int(rgb[1]), int(rgb[0]), int(rgb[2])))
            return self._overlay(color * c.pixel_count, dt)
        if self.effect == 0:
            return self._overlay(self._spectrum(f), dt)
        trail_decay = math.exp(-dt / c.trail_s)
        timbre = scale(f.timbrePosition, c.visual_timbre_range)
        growl = scale(f.growl, c.visual_growl_range)
        vocal = scale(f.vocal, c.visual_vocal_range)
        hue = c.base_hue + offset + c.timbre_hue_span * hue_scale * timbre
        atmosphere = max(f.drone * c.drone_field_gain, f.volume * c.volume_field_gain,
                         f.decay * c.decay_field_gain)
        wave = 0.5 + 0.5 * np.sin(2 * math.pi *
                (self.distance * (c.wave_cycles * cycles + f.harmonics) - self.phase + self.angle))
        # All per-pixel trigonometry runs in native ulab, not Python loops.
        field = atmosphere * field_level * (c.wave_floor + (1 - c.wave_floor) * wave)
        texture = (0.5 + 0.5 * np.sin(self.x * 31 + self.time * 7 +
                   np.sin(self.angle * 17 + self.time * 11))) * growl * c.growl_texture * texture_level
        ribbon = np.maximum(0.0, np.sin(self.distance * 8 - self.time * 3 + self.angle * 6.28))
        ribbon *= ribbon
        ribbon *= ribbon
        ribbon *= vocal * c.vocal_ribbon_gain
        base_rgb = hsv(hue, 0.85, 1.0)
        growl_rgb = hsv(hue + 0.42, 0.95, 1.0)
        vocal_rgb = hsv(hue + 0.18, 0.45, 1.0)
        attack_rgb = hsv(hue, 0.15, 1.0)
        yell_rgb = hsv(hue + 0.2, 0.15, 1.0)
        channels = [field * base_rgb[i] + texture * growl_rgb[i] + ribbon * vocal_rgb[i]
                    + self.attack_bloom * c.attack_bloom_gain * attack_rgb[i]
                    + self.yell_bloom * c.yell_bloom_gain * yell_rgb[i]
                    for i in range(3)]
        for age, strength, vocal in self.pulses:
            if strength <= 0 or age * c.pulse_speed > 2.0 + c.pulse_width:
                continue
            width = c.pulse_width * (1 + vocal) * width_scale
            delta = self.distance - age * c.pulse_speed
            front = np.maximum(0.0, 1 - np.maximum(delta, -delta) * (1.0 / width))
            front *= c.pulse_gain * strength * math.exp(-age / c.pulse_decay_s)
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
        return self._overlay(self.pixels.tobytes(), dt)

    def _update_chroma(self, features, dt):
        c = self.c
        frequency = spectrum_frequency(features.spectrum, self.chroma_centers, c.spectrum_curve)
        if frequency > 0 and features.volume >= c.chroma_min_volume:
            target = clamp((math.log(frequency) - self.chroma_log_low) / self.chroma_log_span)
            self.chroma_position = smooth(self.chroma_position, target, dt,
                                          c.chroma_color_s, c.chroma_color_s)
        self.chroma_volume = smooth(self.chroma_volume, clamp(features.volume), dt,
                                   c.chroma_attack_s, c.chroma_release_s)

    def _spectrum(self, features):
        # Incomplete tiles stay dark. Axial culvert coordinates don't affect bars.
        pixels = bytearray(self.c.pixel_count * 3)
        for x, level in enumerate(features.spectrum):
            r, g, b = self.spectrum_colors[x]
            height = clamp(level) * 4
            for y in range(4):
                coverage = clamp(height - y)
                if coverage <= 0:
                    break
                physical = (3 - y) * 8 + x
                if self.c.spectrum_rotation == 180:
                    physical = 31 - physical
                color = bytes((int(g * coverage), int(r * coverage), int(b * coverage)))
                for tile in range(self.c.pixel_count // 32):
                    index = (tile * 32 + physical) * 3
                    pixels[index:index + 3] = color
        return bytes(pixels)

    def _overlay(self, pixels, dt):
        # Overlay only the output. Audio, scene time, pulses and radio continue.
        if self.indicator_remaining > 0:
            self.indicator_remaining = max(0.0, self.indicator_remaining - dt)
            if self.indicator_remaining > 0:
                return self.indicator_pixels
        return pixels
