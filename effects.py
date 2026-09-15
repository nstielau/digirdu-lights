"""Shared effect IDs and button debouncing; independent of hardware."""

EFFECT_NAMES = ("Culvert", "Ember", "Aurora", "Ripple")
# Hue offset, timbre hue scale, wave frequency, field level, texture level,
# pulse width. IDs are transmitted; keep order identical across all nodes.
PALETTES = (
    (0.0, 1.0, 1.0, 1.0, 1.0, 1.0),
    (-0.49, 0.25, 0.5, 1.1, 1.3, 1.3),
    (0.10, 0.65, 2.0, 0.9, 0.6, 2.0),
    (-0.16, 0.45, 0.7, 0.22, 0.4, 0.65),
)


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
