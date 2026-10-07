"""Pure telemetry formatting and optional, bounded TFT presentation."""
import math
from effects import EFFECT_NAMES

DB_PER_NEPER = 20 / math.log(10)  # CircuitPython provides log, not log10.

# Cached once as a 3x pixel-art sprite, using the existing indexed palette.
# A curled-up dog: round back, floppy ear, closed eye, muzzle and tucked paws.
SLEEP_DOG = (
    '............................',
    '..........aaaaaaa...........',
    '........aaaaaaaaaaa.........',
    '......aaaaaaaaaaaaaaa.......',
    '.....aaaaaaaaaaaaaaaaa......',
    '....aaaaaaaabbbbaaaaaaa.....',
    '...aaaaaaaaabbbbbaaaaaaa....',
    '...aaaaaaaaabbbbbaaaaaaa....',
    '..aaaaaaaaccbbbbccaaaaaaa...',
    '..aaaaaaacccbbccccccccaa....',
    '...aaaaacccddcccccccddc.....',
    '....aaaaccccccccccddcc......',
    '.....aaaacccccccccccc.......',
    '......aaaaacccccccc.........',
    '.......cccccc..cccccc.......',
)


# Fields allow up to 6x14 font cells; native CP10.3.1 reports 6x12.
TFT_FIELDS = (
    ('b0',2,5,5,1,0x00d9ff), ('page',2,21,3,1,0x8899aa),
    ('b1',2,58,5,1,0xff4596), ('b2',2,111,5,1,0xff9f43),
    ('header',44,3,31,1,0x00d9ff), ('effect',44,28,15,2,0xffffff),
    ('banner',44,3,31,1,0xffffff),
    ('sleep_title',12,10,18,2,0xffffff),
    ('sleep_number',178,47,1,4,0xffffff),
    ('sleep_detail',12,112,36,1,0xffffff),
    ('level',44,91,31,1,0x8899aa), ('state',44,117,31,1,0xffb454),
) + tuple(field for index in range(4) for field in (
    ('k%d'%index,44,32+27*index,18,1,0x8899aa),
    ('v%d'%index,164,32+27*index,11,1,0xffffff))) + tuple(
    ('info%d'%index,44,18+14*index,31,1,0xffb454 if index>=4 else 0xffffff)
    for index in range(8))


def snapshot(role, effect, rms=0, volume=0, clipped=False, calibrating=False,
             fault=False, active=False, age=None, timeout=.5, seen=0, full=False,
             rate=0, battery=None, spectrum=(), tx_failed=0, message='', overlay=None,
             brightness=.15, brightness_max=.5, banner='', animation_frame=0, device=None,
             maintenance=False):
    producer = role in ('leader', 'producer')
    level = max(-96.0, DB_PER_NEPER * math.log(max(rms, .5) / 32768)) if producer else min(100, max(0, volume * 100))
    state = ('MIC FAULT' if fault else 'CALIBRATING' if calibrating else
             'CLIPPING' if clipped else 'PLAYING' if active else 'QUIET') if producer else ('LOST' if age is None or age > timeout else 'LIVE')
    reading = battery or {}
    percent = reading.get('percent')
    battery_text = ('%d%%' % percent if reading.get('status') == 'measured'
                    and percent is not None and 0 <= percent <= 100 else '--')
    rate_text = '%.1f' % min(999.9, max(0, rate)) if rate < 1000 else '999.9+'
    age_text = ('--' if age is None else '%dms' % max(0, int(age*1000)) if age < 1
                else '%.1fs' % age if age < 100 else '%ds' % age if age < 10000 else '9999+s')
    rows = (('Battery',battery_text), ('Seen / 10s','%d%s'%(seen,'+' if full else '')),
            ('TX / sec',rate_text), ('TX failed',str(tx_failed))) if producer else (
            ('Battery',battery_text), ('Link',state), ('RX / sec',rate_text), ('Last RX',age_text))
    return {'role': 'PRODUCER' if producer else 'CONSUMER',
            'effect':'%d %s' % (effect + 1, EFFECT_NAMES[effect]),
            'level':level, 'level_units':'dBFS' if producer else '%',
            'meter':max(0,min(1,(level+60)/60)) if producer else level/100,
            'state':state, 'labels':('PAGE','NEXT','AUX'),
            'spectrum':tuple(max(0,min(1,spectrum[i])) if i<len(spectrum) else 0 for i in range(8)),
            'status_rows':rows, 'message':message, 'overlay':overlay,
            'brightness':brightness, 'brightness_max':brightness_max,
            'banner':banner, 'animation_frame':animation_frame, 'device':device,
            'maintenance':bool(maintenance)}


_device_identity = None


def _mac_text(value):
    if value is None:
        return '--'
    if isinstance(value, (bytes, bytearray)):
        value = ':'.join('%02x' % byte for byte in value)
    value = str(value).lower()
    if value.replace(':', '') == '000000000000':
        return 'NONE'
    return value


def device_information(role=None, source=None):
    """Static identity cached once; optional boot snapshot never starts networking."""
    global _device_identity
    if _device_identity is None:
        import microcontroller
        from app_version import APP_VERSION
        from ota_manifest import BASE_VERSION
        _device_identity = {'app':APP_VERSION, 'base':BASE_VERSION,
                            'id':microcontroller.cpu.uid.hex().lower()}
    result = dict(_device_identity)
    if role is None or source is None:
        try:
            import node_state
            saved = node_state.current()
            role = role or saved.get('radio_role')
            source = source if source is not None else saved.get('leader_mac')
        except Exception:
            pass
    result['role'] = {'leader':'PRODUCER','producer':'PRODUCER',
                      'follower':'CONSUMER','consumer':'CONSUMER'}.get(role, '--')
    result['source'] = _mac_text(source)
    try:
        import ota_status
        result['update'] = ota_status.snapshot()
    except ImportError:
        result['update'] = {'state':'unsupported', 'blocked':None}
    return result


def device_lines(info):
    info = info or {'app':'--', 'base':'--', 'id':'--'}
    rows = ['App '+info['app'], 'Base '+info['base'],
            'Role '+info.get('role','--')]
    identifier = 'ID '+info['id']
    update = info.get('update') or {}
    blocked = update.get('blocked')
    id_rows = [identifier[i:i+31] for i in range(0,len(identifier),31)]
    blocked_rows = []
    if update.get('state') == 'checked' and blocked:
        blocked_rows = ['USB BASE NEEDED', 'App '+blocked['version'],
                        'Needs base '+blocked['minimum_base']]
    else:
        label = {'not_checked':'Not checked this boot',
                 'checking':'Checking updates...',
                 'disabled':'OTA not enabled/enrolled',
                 'maintenance':'Not checked: USB mode',
                 'unavailable':'Check unavailable',
                 'unsupported':'Status needs base 1.1.3',
                 'paused':'Updates paused',
                 'no_release':'No release configured',
                 'checked':'No base block found'}.get(update.get('state'),'Not checked this boot')
        if update.get('state') == 'unavailable' and update.get('reason'):
            label += ': ' + str(update['reason'])[:16]
        blocked_rows = [label]
        if update.get('state') in ('checked','paused','no_release'):
            blocked_rows.append('Checked this boot')
    source_value = info.get('source','--')
    source_label = 'MAC' if info.get('role') == 'PRODUCER' else 'Src'
    source_rows = [] if source_value == '--' else [source_label+' '+source_value]
    # The normal UID is 12 hex characters, but keep the page bounded even for
    # a diagnostic fixture or a future longer identity. Preserve the role and
    # complete ID, dropping the optional source row only when necessary.
    if len(rows) + len(source_rows) + len(id_rows) + len(blocked_rows) > 8:
        source_rows = []
    rows.extend(source_rows)
    rows.extend(id_rows)
    rows.extend(blocked_rows)
    return rows


def sleep_overlay(holding=0, remaining=None, status=''):
    if remaining is not None:
        return ('SLEEPING',str(min(9,max(0,int(math.ceil(remaining))))),'Group shutdown')
    if holding>0:
        return ('HOLD TO SLEEP',str(min(9,int(math.ceil(holding)))),'Release to cancel')
    return None


def page_content(state, page):
    if state.get('overlay'):
        title,number,detail=state['overlay']
        return {'sleep_title':title,'sleep_number':number,'sleep_detail':detail}
    content = {'b0':state['labels'][0], 'b1':state['labels'][1], 'b2':state['labels'][2],
               'page':'%d/4'%(page+1)}
    if page == 3:
        content['header']='DEVICE'
        for index,line in enumerate(device_lines(state.get('device'))):
            content['info%d'%index]=line
    elif page == 2:
        content.update(b1='+',b2='-',header='BRIGHTNESS',
                       effect='%d%%'%round(state['brightness']*100),
                       level='FeatherWing / max %d%%'%round(state['brightness_max']*100),
                       state=state['message'] or (state['state'] if state['state'] in ('MIC FAULT','CLIPPING','LOST') else 'Hold any button to sleep'))
    elif page == 1:
        critical = state['state'] if state['state'] in ('MIC FAULT','CLIPPING','LOST') else ''
        content['header'] = state['message'] or critical or state['effect']
        for index,(label,value) in enumerate(state['status_rows']):
            content['k%d'%index],content['v%d'%index]=label,value
    else:
        content['state'] = state['message'] or state['state']
        content['header'] = state['effect']
    if state.get('banner'):
        content.pop('header',None)
        content['banner']=state['banner'][:31]
    elif state.get('maintenance'):
        content.pop('header',None)
        content['banner']='USB MAINTENANCE'
    return content


class Rate:
    def __init__(self):
        self.previous = None
        self.time = 0
        self.value = 0

    def update(self, count, now):
        if self.previous is None or now < self.time:
            self.previous, self.time = count, now
            self.value = 0
        elif now - self.time >= 1:
            delta = (count - self.previous) & 0xffffffff
            self.value = delta / (now - self.time) if delta < 0x80000000 else 0
            self.previous, self.time = count, now
        return self.value


class Dashboard:
    def __init__(self, backend, interval=.2, idle_s=30, debounce_s=.04):
        self.backend = backend
        self.interval = interval
        self.next_refresh = 0
        self.frame_deadline = 0
        self.page = 0
        self.failed = False
        self.cost = .005
        self.skipped = 0
        self.retry_at = 0
        self.overlay = None
        self.idle_s = idle_s
        self.debounce_s = debounce_s
        self.last_activity = None
        self.asleep = False
        self.consume_wake = False
        self.released_at = None
        self.banner = ''
        self.banner_until = 0

    def _wake(self, now):
        self.last_activity = now
        if self.asleep:
            self.asleep = False
            self._set_awake(True)
            self.next_refresh = self.frame_deadline = self.retry_at = 0

    def _set_awake(self, awake):
        try:
            self.backend.set_awake(awake)
        except Exception as error:
            self.failed=True
            print('TFT disabled:',type(error).__name__)
            self.close()

    def button_activity(self, now, pressed):
        """Return True while the entire wake gesture must be discarded."""
        if pressed:
            if self.asleep:self.consume_wake=True
            self._wake(now)
            self.released_at=None
        if self.consume_wake:
            if not pressed:
                if self.released_at is None:self.released_at=now
                elif now-self.released_at>=self.debounce_s:self.consume_wake=False
            return True
        return False

    def visible(self, now):
        if self.failed:return False
        if self.last_activity is None:self.last_activity=now
        if self.overlay is not None:self._wake(now)
        elif not self.asleep and now-self.last_activity>=self.idle_s:
            self.asleep=True
            self._set_awake(False)
        return not self.asleep and not self.failed

    def set_banner(self, status, now):
        previous=self.banner
        if status:
            self.banner=('Broadcasting...' if status in (
                'CHANGING EFFECT','SETTING BRIGHTNESS','SENDING SLEEP') else status)
            self.banner_until=now+.8
        elif now>=self.banner_until:self.banner=''
        if self.banner!=previous:
            self.next_refresh=self.frame_deadline=self.retry_at=0

    def set_overlay(self, overlay):
        if overlay != self.overlay:
            self.overlay = overlay
            self.next_refresh = self.frame_deadline = self.retry_at = 0

    def toggle(self):
        self.page = (self.page + 1) % 4
        self.next_refresh = 0
        self.retry_at = 0

    def ready(self, now, spare):
        # Retry a bounded strip after a transient slow step; never with no budget.
        return (spare >= self.cost + .002
                or (spare >= .012 and (self.overlay is not None or now >= self.retry_at)))

    def update(self, now, state, spare=1, preparation=0):
        if not self.visible(now) or now < self.next_refresh:
            return False
        if not self.ready(now, spare):
            self.skipped += 1
            return False
        import time
        start = time.monotonic()
        if not self.frame_deadline or getattr(self.backend,'pending',False) is not True:
            self.frame_deadline = now + (self.interval if self.page == 0 or self.overlay else max(1, self.interval))
        self.next_refresh = self.frame_deadline
        try:
            self.backend.draw(state,self.page)
            if getattr(self.backend,'pending',False) is True:
                self.next_refresh = now
            self.cost = max(.002, time.monotonic()-start+preparation)
            self.retry_at = now + .5
            return True
        except Exception as error:
            self.failed = True
            print('TFT disabled:', type(error).__name__)
            self.close()
            return False

    def close(self):
        try:
            self.backend.close()
        except Exception:
            pass


class TFTBackend:
    """Compose off-screen, then transfer one bounded strip per loop turn."""
    def __init__(self, config):
        import board
        import displayio
        import bitmaptools
        import terminalio
        import hardware
        from array import array
        boot_tick=getattr(hardware,'boot_tick',None)
        self.display=board.DISPLAY
        self.display.auto_refresh=False
        self.display.rotation=config.display_rotation
        self.brightness=config.display_brightness
        self.display.brightness=self.brightness
        self.fill_region=bitmaptools.fill_region
        self.blit=bitmaptools.blit
        self.font=terminalio.FONT
        self.gw,self.gh=self.font.get_bounding_box()[:2]
        self.front=displayio.Bitmap(240,135,16)
        self.back=displayio.Bitmap(240,135,16)
        colors=(0x030714,0xec436f,0xfa8153,0xeabf55,0x99da67,0x40debd,
                0x44bbea,0x947bea,0xcc69db,0x162132,0x00d9ff,0xffffff,
                0x8899aa,0xff4596,0xff9f43,0xffb454)
        palette=displayio.Palette(16)
        for index,color in enumerate(colors):palette[index]=color
        dog_colors={'.':0,'a':3,'b':14,'c':11,'d':9}
        self.dog=displayio.Bitmap(len(SLEEP_DOG[0])*3,len(SLEEP_DOG)*3,16)
        bitmaptools.arrayblit(self.dog,array('B',(
            dog_colors[SLEEP_DOG[y//3][x//3]]
            for y in range(self.dog.height) for x in range(self.dog.width))))
        self.atlases={}
        source=self.font.bitmap
        self.columns=source.width//self.gw
        # Native scaling/recoloring avoids rebuilding every pixel in Python.
        # Origin zero preserves exact integer replication at scales 1/2/4.
        for _,_,_,_,scale,color in TFT_FIELDS:
            key=(scale,color)
            if key in self.atlases:continue
            index=colors.index(color)
            width,height=source.width*scale,source.height*scale
            atlas=displayio.Bitmap(width,height,16)
            bitmaptools.rotozoom(atlas,source,ox=0,oy=0,px=0,py=0,scale=scale)
            bitmaptools.replace_color(atlas,1,index)
            self.atlases[key]=atlas
            if boot_tick:boot_tick()
        group=displayio.Group()
        group.append(displayio.TileGrid(self.front,pixel_shader=palette))
        close_boot=getattr(hardware,'finish_boot',None) or getattr(hardware,'close_boot',None)
        if close_boot:close_boot()
        self.display.brightness=self.brightness
        self.display.root_group=group
        # Initial full refresh occurs before the audio loop, not in its budget.
        self.display.refresh(target_frames_per_second=None,minimum_frames_per_second=0)
        self.page=None
        self.row=135
        self.pending=False
        self.overlay=None
        self.banner=''

    def _text(self, value, x, y, count, scale, color):
        atlas=self.atlases[(scale,color)]
        width,height=self.gw*scale,self.gh*scale
        for index,character in enumerate(value[:count]):
            glyph=self.font.get_glyph(ord(character)) or self.font.get_glyph(63)
            sx=(glyph.tile_index%self.columns)*width
            sy=(glyph.tile_index//self.columns)*height
            self.blit(self.back,atlas,x+index*width,y,x1=sx,y1=sy,
                      x2=sx+width,y2=sy+height,skip_source_index=0)

    def _prepare(self, state, page):
        self.back.fill(0)
        if state.get('overlay'):
            self._sleep_dog(state.get('animation_frame',0))
        elif state.get('banner') or state.get('maintenance'):
            self.fill_region(self.back,40,0,240,22,15 if state.get('maintenance') else 9)
        content=page_content(state,page)
        for name,x,y,count,scale,color in TFT_FIELDS:
            if name in content:self._text(content[name],x,y,count,scale,color)
        if page==0 and not state.get('overlay'):
            for index,level in enumerate(state['spectrum']):
                x=44+index*23
                self.fill_region(self.back,x,39,x+17,107,9)
                height=int(level*68)
                if height:self.fill_region(self.back,x,107-height,x+17,107,index+1)
        elif page==2 and not state.get('overlay'):
            self.fill_region(self.back,44,65,226,83,9)
            width=int(182*max(0,min(1,state['brightness']/max(.01,state['brightness_max']))))
            if width:self.fill_region(self.back,44,65,44+width,83,6)

    def _sleep_dog(self, frame):
        phase=frame%4
        # Pillow stays still while the dog's body rises by two pixels.
        self.fill_region(self.back,14,96,116,101,7)
        self.blit(self.back,self.dog,23,51-(2 if phase in (1,2) else 0),
                  skip_source_index=0)
        self._text('Z',115+phase*5,64-phase*7,1,1,0xffffff)
        if phase>=2:self._text('Z',122+phase*5,46-phase*4,1,1,0xffffff)

    def set_awake(self, awake):
        self.display.brightness=self.brightness if awake else 0
        if awake:self.pending=False # discard the old partial frame after standby

    def draw(self, state, page):
        overlay=state.get('overlay')
        banner=state.get('banner','') if not overlay else ''
        stage=overlay[0] if overlay else None
        previous_stage=self.overlay[0] if self.overlay else None
        # Digits/sprite frames cannot restart a transfer. A new banner can:
        # otherwise a fast ACK can expire before the next slow Status frame.
        if (not self.pending or page!=self.page or stage!=previous_stage
                or banner!=getattr(self,'banner','')):
            self._prepare(state,page)
            self.page=page
            self.overlay=state.get('overlay')
            self.banner=banner
            self.row=0
            self.pending=True
            return
        end=min(135,self.row+12)
        self.blit(self.front,self.back,0,self.row,x1=0,y1=self.row,x2=240,y2=end)
        self.display.refresh(target_frames_per_second=None,minimum_frames_per_second=0)
        self.row=end
        self.pending=end<135

    def close(self):
        self.display.brightness=0
        self.display.root_group=None


def create(config):
    try:
        return Dashboard(TFTBackend(config), config.display_interval_s,
                         config.display_idle_s, config.button_debounce_s)
    except Exception as error:
        print('TFT unavailable:',type(error).__name__)
        return None
