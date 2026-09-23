"""Explicit first-run role setup; microphone evidence never elects a producer."""

class MicAssessment:
    def __init__(self, started, duration=10):
        self.started, self.duration = started, duration
        self.low, self.high, self.span = 32768.0, 0.0, 0
        self.failed = self.clipped = self.confirmed = False
        self.observations = 0

    def observe(self, rms, peak, span, count, now):
        if count != 1024:
            self.failed = True
        if .2 <= now - self.started <= self.duration:
            self.observations += 1
            self.low, self.high = min(self.low,rms), max(self.high,rms)
            self.span = max(self.span,span)
            self.clipped = self.clipped or peak >= 32000

    def result(self, now):
        if self.failed:return 'CAPTURE FAILED'
        if now - self.started < self.duration:return 'TESTING'
        if self.observations < 2 or self.span < 4:return 'FLAT INPUT'
        if self.clipped:return 'CLIPPING'
        if self.high < max(4, self.low*2):return 'NO LEVEL CHANGE'
        return 'CONFIRM RESPONSE'

    def confirm(self, now):
        self.confirmed = self.result(now) == 'CONFIRM RESPONSE'
        return self.confirmed


def ensure_configured():
    import board
    import node_state
    from hardware import S3
    if board.board_id != S3 or node_state.current().get('radio_role'):
        return
    import os
    if os.getenv('OTA_DEVICE_TOKEN'):
        raise ValueError('Missing enrolled identity; repair through host configuration')
    import array
    import time
    import digitalio
    import storage
    import microcontroller
    from hardware import TextScreen, microphone
    from effects import DebouncedButton
    from sound_reactive import measure
    screen = TextScreen((('title',8,8,36,1,0x00d9ff),('info',8,36,36,1,0xffffff),
                         ('detail',8,60,36,1,0xff4596),('choice',8,95,36,1,0xffffff),
                         ('footer',8,118,36,1,0x8899aa)))
    screen.text('title','DIGIRDU / SELECT ROLE')
    screen.text('info','D0 Consumer / D1 Test microphone')
    screen.text('choice','No automatic role detection')
    screen.text('footer','USB: make configure-node')
    screen.refresh()
    print('SETUP role unconfigured; D0 consumer / D1 microphone test')
    assessment = None
    pins=[]
    try:
        for name, high in (('D0',False),('D1',True),('D2',True)):
            pin=digitalio.DigitalInOut(getattr(board,name));pin.switch_to_input()
            pins.append((pin,high,DebouncedButton(.04)))
        while True:
            now=time.monotonic()
            events=[b.update(p.value==high,now) for p,high,b in pins]
            if events[0]:
                screen.text('title','CONSUMER / SOURCE REQUIRED')
                screen.text('info','Use make configure-node')
                screen.text('detail','ROLE=consumer LEADER_MAC=...')
                screen.text('choice','Enter your producer MAC on host')
                screen.refresh()
            if events[1]:
                samples=array.array('h',[0]*1024)
                assessment=MicAssessment(time.monotonic())
                screen.text('title','MIC TEST / 10 SECONDS')
                screen.text('choice','Quiet first, then speak / clap')
                screen.refresh()
                # Native capture uses generated clocks. A stalled driver is bounded
                # by watchdog reset rather than leaving an unresponsive setup UI.
                from watchdog import WatchDogMode
                previous_mode=microcontroller.watchdog.mode
                previous_timeout=microcontroller.watchdog.timeout
                try:
                    microcontroller.watchdog.timeout=8
                    microcontroller.watchdog.mode=WatchDogMode.RESET
                    with microphone() as mic:
                        while time.monotonic()-assessment.started<10:
                            count=mic.record(samples,len(samples))
                            rms,peak,span=measure(samples,count)
                            now=time.monotonic()
                            assessment.observe(rms,peak,span,count,now)
                            screen.text('info','RMS %.0f  span %d'%(rms,span))
                            screen.text('detail','%.1f seconds'%(now-assessment.started))
                            screen.refresh()
                            microcontroller.watchdog.feed()
                except Exception:
                    assessment.failed=True
                finally:
                    microcontroller.watchdog.mode=previous_mode
                    microcontroller.watchdog.timeout=previous_timeout
                screen.text('title',assessment.result(time.monotonic()))
                screen.text('choice','D2 confirm producer / D1 retry')
                screen.refresh()
            if events[2] and assessment and assessment.confirm(now):
                if os.getenv('OTA_DEVICE_TOKEN'):
                    screen.text('choice','Enrolled: use host configuration')
                elif storage.getmount('/').readonly:
                    screen.text('choice','USB owns disk: make configure-node')
                    screen.text('detail','ROLE=producer')
                else:
                    node_state.save({'schema':1,'radio_role':'producer','radio_group':1})
                    print('SETUP confirmed producer')
                    return
                screen.refresh()
            time.sleep(.02)
    finally:
        for pin,_,_ in pins:pin.deinit()
        screen.close()
