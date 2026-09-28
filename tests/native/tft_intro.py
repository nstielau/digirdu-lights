"""Native Reverse TFT intro completion and frame-cadence check.

Execute with tools.board.Repl and restart the app afterward. Host unittest
cannot exercise the CircuitPython display driver.
"""
import time,hardware
from ota_bootstrap import load_app
app,version=load_app()
original=hardware.EchoArt.draw
times=[];stages=[]
def record(self,elapsed):
 times.append(time.monotonic())
 stages.append(hardware.echo_frame(elapsed)[0])
 original(self,elapsed)
screen=hardware.start_boot()
screen.version(version)
screen.phase('Intro timing check')
hardware.EchoArt.draw=record
started=time.monotonic()
screen.finish()
elapsed=time.monotonic()-started
hardware.EchoArt.draw=original
assert screen.elapsed>=2.35
assert elapsed<3.1
assert len(times)>=40
for stage in ('wave','echo','burst','glow'):assert stage in stages,stage
gaps=[(times[i]-times[i-1])*1000 for i in range(1,len(times))]
print('INTRO elapsed_s',elapsed,'frames',len(times),'gap_avg_ms',sum(gaps)/len(gaps),'gap_max_ms',max(gaps))
print('INTRO stages',[(stage,stages.count(stage)) for stage in ('wave','echo','burst','glow')])
start=time.monotonic()
app.start_dashboard()
assert hardware._boot_screen is None
assert app.DISPLAY is not None and not app.DISPLAY.failed
assert app.DISPLAY.backend.display.root_group is not None
print('INTRO handoff_s',time.monotonic()-start,'backlight',app.DISPLAY.backend.display.brightness)
