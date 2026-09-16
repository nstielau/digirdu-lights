"""Shared effect IDs and button debouncing; independent of hardware."""

EFFECT_NAMES = ("Spectrum", "Ember", "Aurora", "Ripple", "Chroma")
# Hue offset, timbre hue scale, wave frequency, field level, texture level,
# pulse width. IDs are transmitted; keep order identical across all nodes.
PALETTES = (
    (0.0, 1.0, 1.0, 1.0, 1.0, 1.0),
    (-0.49, 0.35, 0.5, 1.05, 1.3, 1.3),
    (0.10, 0.80, 2.0, 0.95, 0.9, 2.0),
    (-0.16, 0.65, 0.7, 0.50, 0.6, 1.0),
    (0.0, 1.0, 1.0, 1.0, 1.0, 1.0),
)

# Display numbers are 1..5; protocol IDs remain 0..4. Three columns, seven rows.
EFFECT_DIGITS = (
    ("010", "110", "010", "010", "010", "010", "111"),
    ("111", "001", "001", "111", "100", "100", "111"),
    ("111", "001", "001", "111", "001", "001", "111"),
    ("101", "101", "101", "111", "001", "001", "001"),
    ("111", "100", "100", "111", "001", "001", "111"),
)
INDICATOR_COLORS = ((0, 0, 1), (1, .2, 0), (0, 1, .6), (.6, 0, 1), (0, 1, 1))
# Factory PCB has four progressive rows of eight. Portrait view: pixel 0 at
# bottom left, logical row-major 4x8 coordinates -> physical pixel index.
FEATHERWING_PORTRAIT = tuple(8 * x + 7 - y for y in range(8) for x in range(4))


def effect_indicator_pixels(effect, config):
    """Return a GRB number on black for each complete 32-pixel wing, or None."""
    if not config.effect_indicator_enabled or config.pixel_count % 32:
        return None
    mapping = config.effect_indicator_map or FEATHERWING_PORTRAIT
    red, green, blue = INDICATOR_COLORS[effect]
    grb = bytes(int(v * config.brightness * 255) for v in (green, red, blue))
    wing = bytearray(96)
    for y, row in enumerate(EFFECT_DIGITS[effect]):
        for x, bit in enumerate(row):
            if bit == "1":
                logical = y * 4 + x
                if config.effect_indicator_rotation == 180:
                    logical = 31 - logical
                offset = mapping[logical] * 3
                wing[offset:offset + 3] = grb
    return bytes(wing) * (config.pixel_count // 32)


class DebouncedButton:
    """Return true once per stable press, never repeatedly during a hold."""

    def __init__(self, debounce_s):
        self.debounce_s = debounce_s
        self.raw = self.stable = False
        self.changed_at = 0.0

    def update(self, pressed, now):
        if pressed != self.raw:
            self.raw = pressed
            self.changed_at = now
        if self.stable != self.raw and now - self.changed_at >= self.debounce_s:
            self.stable = self.raw
            return self.stable
        return False


def spectrum_frequency(levels, centers, curve):
    """Coarse power-weighted centroid from transmitted display bands, in Hz.

    Undo the display amplitude curve, then square for relative power. Shared
    gain cancels; clipping, smoothing and coarse bands make this approximate.
    Zero means no measurable spectrum. This is spectral color, not pitch.
    """
    total = weighted = 0.0
    for level, center in zip(levels, centers):
        power = max(0.0, min(1.0, level)) ** (2.0 / curve)
        total += power
        weighted += power * center
    return weighted / total if total > 1e-12 else 0.0
