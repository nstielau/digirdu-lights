"""USB-base board facts; safe to import on the host or before slot isolation."""
S2 = 'unexpectedmaker_feathers2'
V2 = 'adafruit_feather_esp32_v2'
S3 = 'adafruit_feather_esp32s3_reverse_tft'
PROFILES = {
    S2: {'id': S2, 'wing': 'IO38', 'wing_gpio': 38, 'mic': ('IO5', 'IO6', 'IO9'),
         'mic_gpios': (5, 6, 9), 'display': False, 'native_usb': True,
         'boot': 'IO0', 'battery': None, 'reserved': (38,), 'flash_mb': 4},
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
