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
    if board.board_id == "adafruit_feather_esp32s3_reverse_tft":
        reading = read_gauge()
        return {"voltage": reading["voltage"], "status": reading["status"]}
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
    def __init__(self, interval_s=2.0, local_gauge=False):
        self.interval_s = interval_s
        self.local_gauge = local_gauge
        self.next_read = 0.0
        self.reading = {"voltage": None, "status": "unsupported"}

    def update(self, now):
        if now >= self.next_read:
            self.reading = read_gauge() if self.local_gauge else read_battery()
            self.next_read = now + self.interval_s
        return self.reading


def read_gauge():
    """Read MAX17048 only; skip a busy I2C bus instead of delaying audio.

    Register scaling/version mask follow Adafruit's MAX1704x driver. Do not
    reset the gauge: its learned charge estimate must survive app reads.
    """
    import board
    failure = {"voltage": None, "percent": None, "status": "read_error"}
    locked = False
    try:
        bus = board.I2C()
        locked = bus.try_lock()
        if not locked:
            return failure
        response = bytearray(2)
        def register(number):
            bus.writeto_then_readfrom(0x36, bytes((number,)), response)
            return (response[0] << 8) | response[1]
        if register(8) & 0xfff0 != 0x0010:
            return {"voltage": None, "percent": None, "status": "unsupported"}
        volts = register(2) * 0.000078125
        percent = register(4) / 256.0
        if not 2.0 <= volts <= 4.5 or not 0 <= percent <= 100:
            return {"voltage": None, "percent": None, "status": "out_of_range"}
        return {"voltage": round(volts, 3), "percent": percent, "status": "measured"}
    except (OSError, RuntimeError, ValueError, AttributeError):
        return failure
    finally:
        if locked:
            bus.unlock()
