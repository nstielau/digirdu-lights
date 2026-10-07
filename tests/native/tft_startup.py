"""Run on the Reverse TFT via tools.board.Repl, then restart the normal app.

Native regression: font/display preparation <1 second and every font pixel
identical to the former Python nearest-neighbor builder. This is deliberately
not part of host unittest discovery: it needs CircuitPython/display hardware.
"""
import time,gc,hardware
from ota_bootstrap import load_app
app,version=load_app()
from dashboard import TFTBackend
gc.collect()
# Measure construction separately from the intentional completed splash.
hardware.close_boot()
start=time.monotonic()
backend=TFTBackend(app.CONFIG)
elapsed=time.monotonic()-start
print('FONT preparation_seconds',elapsed)
assert elapsed<1,('font preparation too slow',elapsed)
colors=(0x030714,0xec436f,0xfa8153,0xeabf55,0x99da67,0x40debd,
        0x44bbea,0x947bea,0xcc69db,0x162132,0x00d9ff,0xffffff,
        0x8899aa,0xff4596,0xff9f43,0xffb454)
source=backend.font.bitmap
pixels=0
for (scale,color),atlas in backend.atlases.items():
 expected=colors.index(color)
 assert atlas.width==source.width*scale
 assert atlas.height==source.height*scale
 for y in range(atlas.height):
  for x in range(atlas.width):
   assert atlas[x,y]==(expected if source[x//scale,y//scale] else 0),(scale,color,x,y)
   pixels+=1
 print('FONT verified scale',scale,'color',hex(color))
assert hardware._boot_screen is None
print('FONT PASS pixels',pixels,'free',gc.mem_free())
