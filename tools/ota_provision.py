"""Provision a board-specific token via verified USB writes; never print it."""
import argparse
import ast
import json
import os
from pathlib import Path
import tomllib

from board import Repl, ROOT, S2_BOARD, ESP32_BOARD, find_port, find_drive


def render_settings(previous, credential, enabled):
    additions={'OTA_ENABLED':'1' if enabled else '0','OTA_WIFI_SSID':'openwireless.org',
               'OTA_API_BASE':credential['api'],'OTA_DEVICE_ID':credential['id'],
               'OTA_DEVICE_TOKEN':credential['token'],'OTA_CHANNEL':'stable'}
    # Preserve all unrelated top-level values and tables; insert OTA keys BEFORE tables.
    parsed=tomllib.loads(previous)
    lines=[line for line in previous.splitlines() if line.split('=',1)[0].strip() not in additions]
    text='\n'.join(key+' = '+json.dumps(value) for key,value in additions.items())+'\n'+'\n'.join(lines)+'\n'
    result=tomllib.loads(text)
    if any(result.get(k)!=v for k,v in additions.items()):raise ValueError('Invalid settings')
    for k,v in parsed.items():
        if k not in additions and result.get(k)!=v:raise ValueError('Unrelated settings changed')
    return text.encode()


def provision(port, credential, enabled=False):
    if not (len(credential['token'])==64 and all(c in '0123456789abcdef' for c in credential['token'])):
        raise ValueError('Invalid device token')
    r=Repl(port)
    try:
        r.enter()
        identity=ast.literal_eval(r.execute("import board,microcontroller; print(repr((board.board_id,microcontroller.cpu.uid.hex().lower())))"))
        if identity!=(credential['board'],credential['id']):raise ValueError('Credential does not match connected board')
        r.execute("import os,supervisor; supervisor.runtime.autoreload=False; os.stat('/ota_bootstrap.py'); os.stat('/recovery/lights_app.py')")
        if identity[0]==S2_BOARD:
            drive=find_drive('CIRCUITPY')
            info=(drive/'boot_out.txt').read_text().lower()
            if credential['id'] not in info:raise ValueError('Wrong CIRCUITPY mount')
            previous=(drive/'settings.toml').read_text() if (drive/'settings.toml').exists() else ''
        else:
            previous=r.execute("try:\n print(repr(open('/settings.toml').read()))\nexcept OSError:\n print(repr(''))")
            previous=ast.literal_eval(previous)
        contents=render_settings(previous,credential,enabled)
        backup=ROOT/'.artifacts/ota'/('settings-backup-'+credential['id']+'.toml')
        backup.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as f:f.write(previous)
        if identity[0]==S2_BOARD:
            temporary=drive/'settings.toml.tmp'
            with temporary.open('wb') as f:f.write(contents);f.flush();os.fsync(f.fileno())
            if temporary.read_bytes()!=contents:raise ValueError('Settings readback failed')
            temporary.replace(drive/'settings.toml');os.sync()
        else:
            r.execute("import storage; storage.remount('/',readonly=False)")
            r.execute("f=open('/settings.toml.tmp','wb'); f.write(%r); f.close(); os.sync()" % contents)
            # Compare digest instead of returning credentials through the console.
            import hashlib
            actual=r.execute("from ota_manifest import sha256; print(sha256(open('/settings.toml.tmp','rb').read()))")
            if actual!=hashlib.sha256(contents).hexdigest():raise ValueError('Settings readback failed')
            r.execute("os.rename('/settings.toml.tmp','/settings.toml'); os.sync()")
        print('Credential and settings verified; OTA '+('enabled' if enabled else 'disabled')+'. Hard reset required.')
        if not enabled:
            r.restart(identity[0])
    finally:
        r.serial.write(b'\x02\r')
        r.serial.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('device_id');parser.add_argument('--port',default='');parser.add_argument('--enable',action='store_true')
    args=parser.parse_args()
    if not args.device_id.isalnum():raise SystemExit('Invalid device ID')
    c=json.loads((ROOT/'.artifacts/ota'/(args.device_id+'.json')).read_text())
    try:provision(find_port(args.port),c,args.enable)
    except Exception:
        raise SystemExit('Provisioning failed; inspect board identity and maintenance access. Credentials were not logged.') from None
