"""USB-base battery sensing shared by boot reports and the local display.

No hardware imports until a read. VOLTAGE_MONITOR is ADC1/GPIO35 on the
Feather ESP32 V2, behind its factory 2:1 divider. Original FeatherS2 has no
battery sense circuit: never probe a floating pin or the microphone's I2C pins.
"""
import math

SAMPLE_COUNT = 8
DIVIDER_RATIO = 2.0
CALIBRATION_GAIN = 1.0  # Adjust only after comparison with a multimeter.


def read_battery():
    import board
    if board.board_id != "adafruit_feather_esp32_v2":
        return {"voltage": None, "status": "unsupported"}
    try:
        import analogio
        with analogio.AnalogIn(board.VOLTAGE_MONITOR) as adc:
            _ = adc.value  # Discard the first conversion after initialization.
            raw = sum(adc.value for _ in range(SAMPLE_COUNT)) / SAMPLE_COUNT
            volts = raw * adc.reference_voltage / 65535 * DIVIDER_RATIO * CALIBRATION_GAIN
        if not math.isfinite(volts) or not 2.0 <= volts <= 4.5:
            return {"voltage": None, "status": "out_of_range"}
        return {"voltage": round(volts, 3), "status": "measured"}
    except (OSError, RuntimeError, ValueError, AttributeError):
        return {"voltage": None, "status": "read_error"}


class BatteryMonitor:
    """Read at bounded intervals; replace a failed reading rather than retaining it."""
    def __init__(self, interval_s=2.0):
        self.interval_s = interval_s
        self.next_read = 0.0
        self.reading = {"voltage": None, "status": "unsupported"}

    def update(self, now):
        if now >= self.next_read:
            self.reading = read_battery()
            self.next_read = now + self.interval_s
        return self.reading
