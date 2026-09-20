"""Shared effect IDs and button debouncing; independent of hardware."""

EFFECT_NAMES = ("Spectrum", "Ember", "Aurora", "Ripple", "Chroma", "Battery")
# Hue offset, timbre hue scale, wave frequency, field level, texture level,
# pulse width. IDs are transmitted; keep order identical across all nodes.
PALETTES = (
    (0.0, 1.0, 1.0, 1.0, 1.0, 1.0),
    (-0.49, 0.35, 0.5, 1.05, 1.3, 1.3),
    (0.10, 0.80, 2.0, 0.95, 0.9, 2.0),
    (-0.16, 0.65, 0.7, 0.50, 0.6, 1.0),
    (0.0, 1.0, 1.0, 1.0, 1.0, 1.0),
)

# Battery has no audio palette; keep ID-indexed tables aligned.
PALETTES += ((0.0, 1.0, 1.0, 1.0, 1.0, 1.0),)

# Display numbers are 1..6; protocol IDs remain 0..5. Three columns, seven rows.
EFFECT_DIGITS = (
    ("010", "110", "010", "010", "010", "010", "111"),
    ("111", "001", "001", "111", "100", "100", "111"),
    ("111", "001", "001", "111", "001", "001", "111"),
    ("101", "101", "101", "111", "001", "001", "001"),
    ("111", "100", "100", "111", "001", "001", "111"),
    ("111", "100", "100", "111", "101", "101", "111"),
)
INDICATOR_COLORS = ((0, 0, 1), (1, .2, 0), (0, 1, .6), (.6, 0, 1), (0, 1, 1), (1, .5, 0))
# Factory PCB has four progressive rows of eight. Portrait view: pixel 0 at
# bottom left, logical row-major 4x8 coordinates -> physical pixel index.
FEATHERWING_PORTRAIT = tuple(8 * x + 7 - y for y in range(8) for x in range(4))


def effect_indicator_pixels(effect, config):
    """Return a GRB number on black for each complete 32-pixel wing, or None."""
    if not config.effect_indicator_enabled or config.pixel_count % 32:
        return None
    mapping = config.effect_indicator_map or FEATHERWING_PORTRAIT
    red, green, blue = INDICATOR_COLORS[effect]
    brightness = min(config.brightness, config.battery_brightness) if effect == 5 else config.brightness
    grb = bytes(int(v * brightness * 255) for v in (green, red, blue))
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


def battery_pixels(voltage, config):
    """Local portrait voltage gauge; numeric volts belong in device reports."""
    logical = bytearray(32)
    valid = voltage is not None and 2.0 <= voltage <= 4.5
    low, high = config.battery_voltage_range
    level = max(0.0, min(1.0, (voltage - low) / (high - low))) if valid else 0.0
    rgb = (0, 1, .1) if level >= .6 else ((1, .5, 0) if level >= .25 else (1, 0, 0))
    if not valid:
        # Two amber dashes mean unavailable, never an empty/zero-volt battery.
        rgb = (1, .5, 0)
        for y in (3, 5):
            for x in (1, 2):logical[y * 4 + x] = 1
    else:
        logical[1] = logical[2] = 1  # Battery terminal.
        for y in range(1, 8):
            logical[y * 4] = logical[y * 4 + 3] = 1
        for x in range(4):logical[4 + x] = logical[28 + x] = 1
        rows = int(level * 5 + .5)
        for y in range(7 - rows, 7):
            logical[y * 4 + 1] = logical[y * 4 + 2] = 1
    r, g, b = rgb
    gain = 255 * min(config.brightness, config.battery_brightness)
    color = bytes((int(g * gain), int(r * gain), int(b * gain)))
    mapping = config.effect_indicator_map or FEATHERWING_PORTRAIT
    wing = bytearray(96)
    for i, lit in enumerate(logical):
        if lit:
            physical = mapping[31 - i if config.effect_indicator_rotation == 180 else i] * 3
            wing[physical:physical + 3] = color
    return bytes(wing) * (config.pixel_count // 32) + bytes((config.pixel_count % 32) * 3)


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


class ButtonGesture:
    """A short release or one long hold; a hold never also advances an effect."""
    SHORT = 1
    HOLD = 2

    def __init__(self, debounce_s, hold_s):
        self.button = DebouncedButton(debounce_s)
        self.hold_s = hold_s
        self.pressed_at = None
        self.held = False

    def update(self, pressed, now):
        was_pressed = self.button.stable
        if self.button.update(pressed, now):
            self.pressed_at = self.button.changed_at
            self.held = False
        if was_pressed and not self.button.stable:
            duration = self.button.changed_at - self.pressed_at
            self.pressed_at = None
            if not self.held:
                return self.HOLD if duration >= self.hold_s else self.SHORT
        if (self.button.stable and self.button.raw and not self.held
                and now - self.pressed_at >= self.hold_s):
            self.held = True
            return self.HOLD
        return 0


class SleepTransition:
    """Monotonic, irreversible red fade using local time; duplicates can't extend it."""
    def __init__(self):
        self.started = None
        self.duration = 0.0

    def request(self, now, duration, elapsed=0.0):
        if self.started is None:
            self.started = now - elapsed
            self.duration = duration
            return True
        return False

    def elapsed(self, now):
        return max(0.0, now - self.started) if self.started is not None else 0.0

    def done(self, now):
        return self.started is not None and self.elapsed(now) >= self.duration

    def pixels(self, now, config):
        level = max(0.0, 1.0 - self.elapsed(now) / self.duration)
        # GRB, pure red, with the same installation-wide brightness cap.
        return bytes((0, int(255 * config.brightness * level), 0)) * config.pixel_count
