"""USB-managed filesystem ownership and BOOT-after-reset maintenance window.

Press BOOT AFTER resetting, during the blue two-second window. Holding BOOT
through reset enters Espressif ROM download instead. Never allow concurrent
host and application filesystem writes.
"""
import os
import board
import storage

mode = "usb"
if os.getenv("OTA_ENABLED") == "1" and board.board_id in (
        "unexpectedmaker_feathers2", "adafruit_feather_esp32_v2"):
    import time
    import digitalio
    import microcontroller
    from neopixel_write import neopixel_write
    led_pin = board.IO38 if board.board_id == "unexpectedmaker_feathers2" else board.D32
    button_pin = board.IO0 if board.board_id == "unexpectedmaker_feathers2" else board.BUTTON
    with digitalio.DigitalInOut(button_pin) as button, digitalio.DigitalInOut(led_pin) as pixels:
        # ESP32 V2 GPIO38 has an external pull-up and no internal pull-up support.
        button.switch_to_input(pull=digitalio.Pull.UP if board.board_id == "unexpectedmaker_feathers2" else None)
        pixels.switch_to_output(value=False)
        neopixel_write(pixels, bytes((0, 0, 12)) * 32)
        end = time.monotonic() + 2
        maintenance = False
        while time.monotonic() < end:
            maintenance = maintenance or not button.value
            time.sleep(.01)
        neopixel_write(pixels, bytes(96))
    if maintenance:
        storage.remount("/", readonly=True)
        mode = "maintenance"
    else:
        storage.remount("/", readonly=False)
        mode = "ota"
print("DIGIRDU_BOOT mode=" + mode)
