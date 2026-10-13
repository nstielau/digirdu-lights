"""USB-managed filesystem ownership and BOOT-after-reset maintenance window.

Press BOOT AFTER resetting, during the blue two-second window. Holding BOOT
through reset enters Espressif ROM download instead. Never allow concurrent
host and application filesystem writes.
"""
import os
import board
import storage
from hardware import profile, PROFILES, consume_maintenance_request

mode = "usb"
requested = False
if board.board_id == "adafruit_feather_esp32s3_reverse_tft":
    import microcontroller
    requested = consume_maintenance_request(microcontroller.nvm)
if os.getenv("OTA_ENABLED") == "1" and board.board_id in PROFILES:
    import time
    import digitalio
    from neopixel_write import neopixel_write
    p = profile(board.board_id)
    led_pin = getattr(board, p["wing"])
    button_pin = getattr(board, p["boot"])
    with digitalio.DigitalInOut(button_pin) as button, digitalio.DigitalInOut(led_pin) as pixels:
        # ESP32 V2 GPIO38 has an external pull-up and no internal pull-up support.
        button.switch_to_input(pull=digitalio.Pull.UP if board.board_id != "adafruit_feather_esp32_v2" else None)
        pixels.switch_to_output(value=False)
        def orange_pixel(index):
            frame = bytearray(96)
            frame[index * 3:index * 3 + 3] = bytes((3, 8, 0))  # GRB, dim orange.
            return frame
        orange = requested
        index = 0
        neopixel_write(pixels, orange_pixel(index) if orange else bytes((0, 0, 12)) * 32)
        now = time.monotonic()
        end = now + 2
        next_step = now + .5
        maintenance = requested
        while now < end:
            if not button.value and not maintenance:
                maintenance = True
                if board.board_id == "adafruit_feather_esp32s3_reverse_tft":
                    orange = True
                    index = 0
                    neopixel_write(pixels, orange_pixel(index))
            elif orange and now >= next_step:
                index = (index + 1) % 32
                neopixel_write(pixels, orange_pixel(index))
                next_step = now + .5
            time.sleep(.01)
            now = time.monotonic()
        neopixel_write(pixels, bytes(96))
    if maintenance:
        storage.remount("/", readonly=True)
        mode = "maintenance"
    else:
        storage.remount("/", readonly=False)
        mode = "ota"
print("DIGIRDU_BOOT mode=" + mode)
