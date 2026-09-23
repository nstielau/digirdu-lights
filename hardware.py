"""USB-base board facts; safe to import on the host or before slot isolation."""
S2 = 'unexpectedmaker_feathers2'
V2 = 'adafruit_feather_esp32_v2'
S3 = 'adafruit_feather_esp32s3_reverse_tft'
PROFILES = {
    S2: {'id': S2, 'wing': 'IO38', 'wing_gpio': 38, 'mic': ('IO5', 'IO6', 'IO9'),
         'mic_gpios': (5, 6, 9), 'display': False, 'native_usb': True,
         'boot': 'IO0', 'battery': None, 'reserved': (38,), 'flash_mb': 16},
    V2: {'id': V2, 'wing': 'D32', 'wing_gpio': 32, 'mic': None,
         'mic_gpios': None, 'display': False, 'native_usb': False,
         'boot': 'BUTTON', 'battery': 'adc', 'reserved': (32, 35), 'flash_mb': 8},
    S3: {'id': S3, 'wing': 'D6', 'wing_gpio': 6, 'mic': ('D5', 'D9', 'D10'),
         'mic_gpios': (5, 9, 10), 'display': True, 'native_usb': True,
         'boot': 'D0', 'battery': 'max17048', 'flash_mb': 4,
         'reserved': (0, 1, 2, 3, 4, 6, 7, 21, 33, 35, 36, 37, 40, 41, 42, 45)},
}


def profile(board_id):
    if board_id not in PROFILES:
        raise ValueError('No verified wiring profile: ' + str(board_id))
    return PROFILES[board_id]


def validate_pins(p, mic_gpios):
    if p['mic'] is None or len(mic_gpios) != 3 or len(set(mic_gpios)) != 3:
        raise ValueError('Unsupported or duplicate microphone pins')
    if any(type(pin) is not int or pin in p['reserved'] for pin in mic_gpios):
        raise ValueError('Microphone conflicts with reserved GPIO')
    # Wiring profiles are verified as a set; arbitrary overrides need a new profile.
    if tuple(mic_gpios) != p['mic_gpios']:
        raise ValueError('Unverified microphone pins')


def microphone(sample_rate=16000):
    import board
    import audioi2sin
    p = profile(board.board_id)
    validate_pins(p, p['mic_gpios'] or ())
    return audioi2sin.I2SIn(*(getattr(board, name) for name in p['mic']),
                          sample_rate=sample_rate, bit_depth=32, output_bit_depth=16,
                          mono=True, left_justified=False, samples_signed=True)


class TextScreen:
    """Small base-owned display backend; built-in font, reused glyph grids.

    No imports/allocations until constructed on a display-capable board.
    Fields: (name, x, y, character count, scale, RGB color).
    """
    def __init__(self, fields, brightness=.12, rotation=0):
        import board
        import displayio
        import terminalio
        self.display = board.DISPLAY
        self.display.auto_refresh = False
        self.display.rotation = rotation
        self.display.brightness = brightness
        self.font = terminalio.FONT
        width, height = self.font.get_bounding_box()[:2]
        self.group = displayio.Group()
        self.fields = {}
        for name, x, y, count, scale, color in fields:
            palette = displayio.Palette(2)
            palette[0] = 0x030714
            palette[1] = color
            grid = displayio.TileGrid(self.font.bitmap, pixel_shader=palette,
                                      width=count, height=1, tile_width=width,
                                      tile_height=height)
            group = displayio.Group(x=x, y=y, scale=scale)
            group.append(grid)
            self.group.append(group)
            self.fields[name] = (grid, count)
            self.text(name, '')
        self.display.root_group = self.group

    def text(self, name, value):
        grid, count = self.fields[name]
        for index in range(count):
            character = ord(value[index]) if index < len(value) else 32
            glyph = self.font.get_glyph(character) or self.font.get_glyph(63)
            grid[index] = glyph.tile_index

    def refresh(self):
        self.display.refresh(minimum_frames_per_second=0)

    def close(self):
        self.display.brightness = 0
        self.display.root_group = None


class BootScreen:
    def __init__(self):
        import board
        self.screen = None
        if not profile(board.board_id)['display']:
            return
        try:
            self.screen = TextScreen((('title', 8, 12, 35, 1, 0x00d9ff),
                                      ('phase', 8, 48, 35, 1, 0xffffff),
                                      ('note', 8, 90, 35, 1, 0x8899aa)))
            self.screen.text('title', 'DIGIRDU / STARTUP')
            self.screen.text('note', 'BOOT after RESET: USB maintenance')
            self.phase('Starting')
        except Exception as error:
            print('TFT boot unavailable:', type(error).__name__)
            self.close()

    def phase(self, text):
        if self.screen:
            try:
                self.screen.text('phase', text)
                self.screen.refresh()
            except Exception:
                self.close()

    def close(self):
        if self.screen:
            try:
                self.screen.close()
            except Exception:
                pass
            self.screen = None


def sleep_power():
    """Release native display ownership, then preserve its power rails LOW.

    CP10.3.1 reset_all_pins skips preserved pins before the board reset hook;
    preserving GPIO7 prevents its board-specific default-HIGH reset hook.
    Retain these DigitalInOuts through alarm handoff; never deinit on unwind.
    """
    import board
    import displayio
    import digitalio
    display = board.DISPLAY
    display.auto_refresh = False
    display.brightness = 0
    display.root_group = None
    displayio.release_displays()
    # Singleton bus remains initialized after gauge reads; close before power-off.
    try:
        board.I2C().deinit()
    except (OSError, RuntimeError):
        pass
    held = []
    for name in ('TFT_BACKLIGHT', 'TFT_I2C_POWER', 'NEOPIXEL_POWER'):
        pin = digitalio.DigitalInOut(getattr(board,name))
        pin.switch_to_output(value=False)
        held.append(pin)
    return tuple(held)
