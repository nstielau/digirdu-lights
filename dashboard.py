"""Pure telemetry formatting and optional, bounded TFT presentation."""
import math
from effects import EFFECT_NAMES

DB_PER_NEPER = 20 / math.log(10)  # CircuitPython provides log, not log10.


# Fields allow up to 6x14 font cells; native CP10.3.1 reports 6x12.
TFT_FIELDS = (
    ('b0',2,5,5,1,0x00d9ff), ('page',2,21,3,1,0x8899aa),
    ('b1',2,58,5,1,0xff4596), ('b2',2,111,5,1,0xff9f43),
    ('header',44,3,31,1,0x00d9ff), ('effect',44,28,15,2,0xffffff),
    ('sleep_title',12,10,18,2,0xffffff),
    ('sleep_number',108,43,1,4,0xffffff),
    ('sleep_detail',12,112,36,1,0xffffff),
    ('level',44,91,31,1,0x8899aa), ('state',44,117,31,1,0xffb454),
) + tuple(field for index in range(4) for field in (
    ('k%d'%index,44,32+27*index,18,1,0x8899aa),
    ('v%d'%index,164,32+27*index,11,1,0xffffff)))


def snapshot(role, effect, rms=0, volume=0, clipped=False, calibrating=False,
             fault=False, active=False, age=None, timeout=.5, seen=0, full=False,
             rate=0, battery=None, spectrum=(), tx_failed=0, message='', overlay=None, brightness=.15, brightness_max=.5):
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
            'state':state, 'labels':('PAGE','NEXT','SLEEP'),
            'spectrum':tuple(max(0,min(1,spectrum[i])) if i<len(spectrum) else 0 for i in range(8)),
            'status_rows':rows, 'message':message, 'overlay':overlay,
            'brightness':brightness, 'brightness_max':brightness_max}


def sleep_overlay(holding=0, remaining=None, status=''):
    if remaining is not None:
        return ('SLEEPING',str(min(9,max(0,int(math.ceil(remaining))))),'Group shutdown')
    if holding>0:
        return ('HOLD TO SLEEP',str(min(9,int(math.ceil(holding)))),'Release to cancel')
    if status:
        return ('GROUP CONTROL','',status)
    return None


def page_content(state, page):
    if state.get('overlay'):
        title,number,detail=state['overlay']
        return {'sleep_title':title,'sleep_number':number,'sleep_detail':detail}
    content = {'b0':state['labels'][0], 'b1':state['labels'][1], 'b2':state['labels'][2],
               'page':'%d/3'%(page+1)}
    if page == 2:
        content.update(b1='+',b2='-',header='BRIGHTNESS',
                       effect='%d%%'%round(state['brightness']*100),
                       level='FeatherWing / max %d%%'%round(state['brightness_max']*100),
                       state=state['message'] or (state['state'] if state['state'] in ('MIC FAULT','CLIPPING','LOST') else 'Hold D2 to sleep'))
    elif page == 1:
        critical = state['state'] if state['state'] in ('MIC FAULT','CLIPPING','LOST') else ''
        content['header'] = state['message'] or critical or state['effect']
        for index,(label,value) in enumerate(state['status_rows']):
            content['k%d'%index],content['v%d'%index]=label,value
    else:
        content['state'] = state['message'] or state['state']
        content['header'] = state['effect']
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
    def __init__(self, backend, interval=.2):
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

    def set_overlay(self, overlay):
        if overlay != self.overlay:
            self.overlay = overlay
            self.next_refresh = self.frame_deadline = self.retry_at = 0

    def toggle(self):
        self.page = (self.page + 1) % 3
        self.next_refresh = 0
        self.retry_at = 0

    def ready(self, now, spare):
        # Retry a bounded strip after a transient slow step; never with no budget.
        return (spare >= self.cost + .002
                or (spare >= .012 and (self.overlay is not None or now >= self.retry_at)))

    def update(self, now, state, spare=1, preparation=0):
        if self.failed or now < self.next_refresh:
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
        from array import array
        self.display=board.DISPLAY
        self.display.auto_refresh=False
        self.display.rotation=config.display_rotation
        self.display.brightness=config.display_brightness
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
        self.atlases={}
        source=self.font.bitmap
        self.columns=source.width//self.gw
        # Colored/scaled glyph atlases are built once before audio/radio start.
        for _,_,_,_,scale,color in TFT_FIELDS:
            key=(scale,color)
            if key in self.atlases:continue
            index=colors.index(color)
            width,height=source.width*scale,source.height*scale
            atlas=displayio.Bitmap(width,height,16)
            pixels=array('B',(index if source[x//scale,y//scale] else 0
                              for y in range(height) for x in range(width)))
            bitmaptools.arrayblit(atlas,pixels)
            self.atlases[key]=atlas
        group=displayio.Group()
        group.append(displayio.TileGrid(self.front,pixel_shader=palette))
        self.display.root_group=group
        # Initial full refresh occurs before the audio loop, not in its budget.
        self.display.refresh(target_frames_per_second=None,minimum_frames_per_second=0)
        self.page=None
        self.row=135
        self.pending=False
        self.overlay=None

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
        self.back.fill(1 if state.get('overlay') else 0)
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

    def draw(self, state, page):
        overlay=state.get('overlay')
        stage=overlay[0] if overlay else None
        previous_stage=self.overlay[0] if self.overlay else None
        # Finish a frame across digit changes; only a new stage preempts it.
        if not self.pending or page!=self.page or stage!=previous_stage:
            self._prepare(state,page)
            self.page=page
            self.overlay=state.get('overlay')
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
        return Dashboard(TFTBackend(config), config.display_interval_s)
    except Exception as error:
        print('TFT unavailable:',type(error).__name__)
        return None
