"""Pure telemetry formatting and optional, bounded TFT presentation."""
import math
from effects import EFFECT_NAMES


def snapshot(role, effect, rms=0, volume=0, clipped=False, calibrating=False,
             fault=False, active=False, age=0, timeout=.5, seen=0, full=False,
             rate=0, battery=None, channel=1, group=1, version='', counters='',
             source='', overruns=0, message=''):
    producer = role in ('leader', 'producer')
    level = max(-96.0, 20 * math.log10(max(rms, .5) / 32768)) if producer else min(100, max(0, volume * 100))
    state = ('MIC FAULT' if fault else 'CALIBRATING' if calibrating else
             'CLIPPING' if clipped else 'PLAYING' if active else 'QUIET') if producer else ('LOST' if age > timeout else 'LIVE')
    reading = battery or {}
    volts = reading.get('voltage')
    percent = reading.get('percent')
    battery_text = ('%d%% %.2fV' % (percent, volts) if percent is not None and volts is not None
                    else '%.2fV' % volts if volts is not None else 'BAT --')
    return {'role': 'PRODUCER' if producer else 'CONSUMER', 'battery':battery_text,
            'effect':'%d %s' % (effect + 1, EFFECT_NAMES[effect]),
            'level':level, 'level_units':'dBFS' if producer else '%',
            'meter':max(0,min(1,(level+60)/60)) if producer else level/100,
            'state':state, 'labels':('PAGE','NEXT' if producer else 'FOLLOW','SLEEP'),
            'lower':('SEEN/10s %d%s TX %.1f/s' % (seen,'+' if full else '',rate) if producer
                     else '%s RX %.1f/s age %.1fs' % (state,rate,min(age,999))),
            'footer':'CH%d G%d v%s' % (channel,group,version),
            'counters':counters, 'source':source, 'overruns':overruns, 'message':message}


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
        self.page = 0
        self.failed = False
        self.cost = .005
        self.skipped = 0

    def toggle(self):
        self.page = 1 - self.page

    def update(self, now, state, spare=1):
        if self.failed or now < self.next_refresh:
            return False
        if spare < self.cost + .002:
            self.skipped += 1
            return False
        import time
        start = time.monotonic()
        self.next_refresh = now + self.interval
        try:
            self.backend.draw(state,self.page)
            self.cost = max(.002, time.monotonic()-start)
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
    def __init__(self, config):
        from hardware import TextScreen
        self.screen = TextScreen((
            ('b0',2,7,6,1,0x00d9ff), ('b1',2,57,6,1,0xff4596), ('b2',2,110,6,1,0xff9f43),
            ('header',48,2,31,1,0x00d9ff), ('effect',48,23,15,2,0xffffff),
            ('level',48,53,31,1,0x00d9ff), ('meter',48,70,30,1,0xff4596),
            ('lower',48,88,31,1,0xffffff), ('extra',48,103,31,1,0x8899aa),
            ('footer',48,119,31,1,0x8899aa)), config.display_brightness, config.display_rotation)

    def draw(self, state, page):
        s=self.screen
        for index,label in enumerate(state['labels']):s.text('b%d'%index,label)
        s.text('header',state['role']+' '+state['battery'])
        s.text('footer',state['footer'])
        if page:
            s.text('effect','DIAGNOSTICS')
            s.text('level',state['counters'][:31])
            s.text('meter',state['counters'][31:62])
            s.text('lower','Source '+state['source'])
            s.text('extra','Overruns %d'%state['overruns'])
        else:
            s.text('effect',state['effect'])
            s.text('level','%.0f %s  %s'%(state['level'],state['level_units'],state['state']))
            bars=int(state['meter']*30)
            s.text('meter','|'*bars+'.'*(30-bars))
            s.text('lower',state['lower'])
            s.text('extra',state['message'])
        s.refresh()

    def close(self):
        self.screen.close()


def create(config):
    try:
        return Dashboard(TFTBackend(config), config.display_interval_s)
    except Exception as error:
        print('TFT unavailable:',type(error).__name__)
        return None
