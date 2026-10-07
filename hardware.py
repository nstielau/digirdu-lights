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
    S3: {'id': S3, 'wing': 'D6', 'wing_gpio': 6, 'mic': ('D5', 'D9', 'D6'),
         'mic_gpios': (5, 9, 6), 'display': True, 'native_usb': True,
         'boot': 'D0', 'battery': 'max17048', 'flash_mb': 4,
         'reserved': (0, 1, 2, 3, 4, 7, 21, 33, 35, 36, 37, 40, 41, 42, 45)},
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
        # An older app or setup/fault screen may already have taken ownership.
        if self.display.root_group is self.group:
            self.display.brightness = 0
            self.display.root_group = None


def echo_frame(elapsed):
    """Time-based wave -> reflection -> light burst -> quiet glow."""
    t=max(0,elapsed)
    if t<.7:return ('wave',24+int(156*t/.7),t/.7)
    if t<1.2:return ('echo',180-int(84*(t-.7)/.5),(t-.7)/.5)
    if t<2.2:return ('burst',96,(t-1.2))
    return ('glow',96,abs((t%2)-1))


class EchoArt:
    """One reusable bitmap; bounded rectangles, no per-frame display objects."""
    RAYS=((100,0),(92,38),(71,71),(38,92),(0,100),(-38,92),(-71,71),
          (-92,38),(-100,0),(-92,-38),(-71,-71),(-38,-92),(0,-100),
          (38,-92),(71,-71),(92,-38))

    def __init__(self,screen):
        import displayio
        import bitmaptools
        self.bitmap=displayio.Bitmap(216,60,8)
        self.maintenance=False
        palette=displayio.Palette(8)
        for i,color in enumerate((0x030714,0x00d9ff,0xff4596,0xffc45c,
                                  0x164058,0x481a40,0x615032,0xffffff)):
            palette[i]=color
        self.fill_region=bitmaptools.fill_region
        screen.group.append(displayio.TileGrid(self.bitmap,pixel_shader=palette,x=12,y=45))

    def _rect(self,x,y,w,h,color):
        x1,y1=max(0,int(x)),max(0,int(y))
        x2,y2=min(216,int(x+w)),min(60,int(y+h))
        if x1<x2 and y1<y2:self.fill_region(self.bitmap,x1,y1,x2,y2,color)

    def draw(self,elapsed):
        stage,x,progress=echo_frame(elapsed)
        self.bitmap.fill(0)
        if getattr(self,'maintenance',False):
            # Amber rails make USB ownership obvious without replacing the
            # EchoGlow blue/pink artwork with an error-looking full orange fill.
            self._rect(0,0,216,2,3)
            self._rect(0,58,216,2,3)
        if stage in ('wave','echo'):
            self._rect(184,7,3,46,2)
            self._rect(189,10,1,40,5)
            direction=1 if stage=='wave' else -1
            # Three curved wave fronts. Cyan outbound, pink reflected.
            for arc in range(3):
                for dy in range(-18,19,3):
                    curve=(dy*dy)//48
                    self._rect(x-direction*(arc*10+curve),30+dy,2,3,
                               (1 if stage=='wave' else 2) if arc==0 else 4 if stage=='wave' else 5)
            if .63<elapsed<.82:self._rect(181,18,6,24,7)
        else:
            radius=(4+progress*75) if stage=='burst' else (22+progress*3)
            for i,(dx,dy) in enumerate(self.RAYS):
                px=x+radius*dx/100
                py=30+radius*.34*dy/100
                color=1+i%3
                if stage=='glow' and i%3==int(progress*3):color+=3
                size=3 if stage=='glow' else max(1,4-int(progress*3))
                self._rect(px,py,size,size,color)
            core=4+int((1-progress)*6) if stage=='burst' else 3
            self._rect(x-core,29,core*2+1,2,1)
            self._rect(x-1,30-core,2,core*2+1,3)


class BootScreen:
    def __init__(self):
        import board
        import time
        self.screen = None
        self.started=time.monotonic()
        self.last_frame=self.started
        self.elapsed=0
        self.next_frame=0
        if not PROFILES.get(getattr(board,'board_id',''),{}).get('display'):
            return
        try:
            self.screen = TextScreen((('mode',12,3,10,1,0xffb454),
                                      ('title',72,3,8,2,0x00d9ff),
                                      ('version',102,29,20,1,0x8899aa),
                                      ('phase',12,115,36,1,0xffffff)),brightness=.5)
            self.art=EchoArt(self.screen)
            self.screen.text('mode','')
            self.screen.text('title','EchoGlow')
            self.screen.text('version','')
            self.phase('Starting')
        except Exception as error:
            print('TFT boot unavailable:', type(error).__name__)
            self.close()

    def maintenance(self):
        """Mark the splash and subsequent dashboard as USB maintenance mode."""
        if self.screen:
            try:
                self.screen.text('mode','USB MAINT')
                self.screen.text('phase','CIRCUITPY READY')
                self.art.maintenance=True
                self.tick(force=True)
            except Exception:
                self.close()

    def phase(self, text):
        if self.screen:
            try:
                self.screen.text('phase', text)
                self.tick(force=True)
            except Exception:
                self.close()

    def version(self, version):
        if self.screen:
            try:
                self.screen.text('version','v'+version)
                self.tick(force=True)
            except Exception:
                self.close()

    def tick(self, force=False):
        if not self.screen:return
        import time
        now=time.monotonic()
        if not force and now<self.next_frame:return
        try:
            # Avoid skipping the whole echo after a blocking import/Wi-Fi call.
            self.elapsed+=min(.075,max(0,now-self.last_frame))
            self.last_frame=now
            self.art.draw(self.elapsed)
            self.screen.refresh()
            self.next_frame=now+.05
        except Exception:
            self.close()

    def finish(self):
        """Finish the visible intro before handoff; never wait on a dead display."""
        if not self.screen or self.screen.display.root_group is not self.screen.group:return
        import time
        deadline=time.monotonic()+3
        while self.screen and self.elapsed<2.35 and time.monotonic()<deadline:
            self.tick()
            if self.screen and self.elapsed<2.35:time.sleep(.005)

    def close(self):
        if self.screen:
            try:
                self.screen.close()
            except Exception:
                pass
            self.screen = None


_boot_screen=None


def start_boot():
    global _boot_screen
    close_boot()
    _boot_screen=BootScreen()
    return _boot_screen


def boot_tick():
    if _boot_screen is not None:_boot_screen.tick()


def finish_boot():
    if _boot_screen is not None:_boot_screen.finish()
    close_boot()


def close_boot():
    global _boot_screen
    if _boot_screen is not None:_boot_screen.close()
    _boot_screen=None


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
