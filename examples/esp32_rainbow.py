"""Moving rainbow on a 32-pixel NeoPixel FeatherWing. Runs at power-on."""

import time

import board
import digitalio
from neopixel_write import neopixel_write
from rainbowio import colorwheel

# The FeatherWing's factory data jumper connects to GPIO 32 on ESP32 Feathers.
PIXEL_PIN = board.D32
PIXEL_COUNT = 32
BRIGHTNESS = 0.15  # 0.0 to 1.0; start low when powering the wing over USB.
FRAME_DELAY = 0.02


def main():
    """Send RGB colors in the FeatherWing's GRB wire order."""
    pixels = bytearray(PIXEL_COUNT * 3)
    with digitalio.DigitalInOut(PIXEL_PIN) as pin:
        pin.switch_to_output(value=False)
        phase = 0
        frames = 0
        try:
            while True:
                for index in range(PIXEL_COUNT):
                    color = colorwheel((index * 256 // PIXEL_COUNT + phase) % 256)
                    offset = index * 3
                    pixels[offset] = int(((color >> 8) & 255) * BRIGHTNESS)
                    pixels[offset + 1] = int(((color >> 16) & 255) * BRIGHTNESS)
                    pixels[offset + 2] = int((color & 255) * BRIGHTNESS)
                neopixel_write(pin, pixels)
                frames += 1
                if frames == 1:
                    print("Rainbow running: 32 pixels on D32, brightness", BRIGHTNESS)
                elif frames % 256 == 0:
                    print("Rainbow frames:", frames)
                phase = (phase + 1) % 256
                time.sleep(FRAME_DELAY)
        finally:
            # Ctrl-C or a Python exception turns off the wing before releasing the pin.
            pixels[:] = bytes(len(pixels))
            neopixel_write(pin, pixels)


if __name__ == "__main__":
    main()
