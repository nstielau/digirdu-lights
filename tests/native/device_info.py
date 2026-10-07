"""Native Device page layout check; restore app with Repl.restart afterward.

Leaves _device_backend/_device_state available for bounded host screenshot reads.
"""
import hardware, microcontroller, ota_status
from ota_bootstrap import load_app
from ota_manifest import BASE_VERSION
_app, _version = load_app()
from dashboard import TFTBackend, device_information, snapshot, page_content, TFT_FIELDS
hardware.close_boot()
_device_backend = TFTBackend(_app.CONFIG)
_info = device_information()
assert _info['app'] == _version
assert _info['base'] == BASE_VERSION
assert _info['id'] == microcontroller.cpu.uid.hex().lower()
print('DEVICE INFO', _info)

def _show_device(info):
    state = snapshot(_app.CONFIG.radio_role, 0, device=info)
    content = page_content(state, 3)
    assert content['page'] == '4/4'
    for name,x,y,count,scale,color in TFT_FIELDS:
        assert len(content.get(name,'')) <= count, name
        assert x+count*6*scale <= 240 and y+14*scale <= 135, name
    _device_backend.draw(state,3)
    strips = 0
    while _device_backend.pending:
        _device_backend.draw(state,3)
        strips += 1
    assert strips == 12, strips
    print('DEVICE PAGE PASS', info['update']['state'], 'strips', strips)

_show_device(_info)
