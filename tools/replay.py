"""Replay saved feature logs through the actual firmware renderer (host only)."""

import argparse
import ast
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from animation import CulvertAnimation
from audio_features import AudioFeatures
from config import Config
from effects import EFFECT_NAMES, spectrum_frequency

FIELDS = {'rms': 'rms', 'noise': 'noiseFloor', 'vol': 'volume', 'drone': 'drone',
          'harm': 'harmonics', 'timbre': 'timbrePosition', 'growl': 'growl',
          'vocal': 'vocal', 'rough': 'roughness', 'active': 'active', 'clip': 'clipped'}
LIMITS = ('Feature logs, not PCM: FFT/classifier replay is unavailable. '
          'Levels are held between roughly 1 Hz observations; event timestamps are preserved. '
          'Unlogged decay and attack envelopes are reconstructed. Final fade is synthetic. '
          'Band centroid is approximate, not fundamental pitch. Display brightness is amplified.')


def read_records(path):
    records = []
    previous = -1.0
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        row = json.loads(line)
        t = float(row['elapsed_s'])
        if not math.isfinite(t) or t < previous:
            raise ValueError('Non-monotonic timestamp at line ' + str(number))
        previous = t
        text = row['line']
        data = None
        if text.startswith('AUDIO '):
            data = {}
            for key, value in re.findall(r'(\w+)=([^ ]+)', text):
                if key in FIELDS:
                    if key in ('active', 'clip'):
                        if value not in ('True', 'False'):
                            raise ValueError('Invalid boolean')
                        value = value == 'True'
                    else:
                        value = float(value)
                        if not math.isfinite(value):
                            raise ValueError('Non-finite feature')
                    data[FIELDS[key]] = value
            kind = 'audio'
        elif text.startswith('SPECTRUM levels='):
            data = tuple(ast.literal_eval(text.split('=', 1)[1]))
            if len(data) != 8 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in data):
                raise ValueError('Invalid spectrum')
            kind = 'spectrum'
        elif text.startswith(('ATTACK strength=', 'YELL vocal=')):
            data = float(text.split('=', 1)[1])
            if not math.isfinite(data) or not 0 <= data <= 1:
                raise ValueError('Invalid event strength')
            kind = 'attack' if text.startswith('ATTACK') else 'yell'
        if data is not None:
            records.append({'time': t, 'section': row.get('section', 'unlabelled'),
                            'kind': kind, 'data': data})
    if not any(r['kind'] == 'audio' for r in records):
        raise ValueError('No audio features in capture')
    return records


def percentile(values, fraction):
    ordered = sorted(values)
    pos = (len(ordered) - 1) * fraction
    low = int(pos)
    return ordered[low] + (ordered[min(low + 1, len(ordered)-1)] - ordered[low]) * (pos-low)


def calibration(records, config):
    centers = tuple(math.sqrt(a*b) for a, b in zip(config.spectrum_edges, config.spectrum_edges[1:]))
    volume = 0
    audio_time = -100
    frequencies = []
    sections = {}
    for row in records:
        stats = sections.setdefault(row['section'], {'start_s': row['time'], 'end_s': row['time'],
                                                    'audio': 0, 'spectrum': 0, 'attack': 0, 'yell': 0})
        stats['end_s'] = row['time']
        stats[row['kind']] += 1
        if row['kind'] == 'audio':
            volume = row['data'].get('volume', 0)
            audio_time = row['time']
        if (row['kind'] == 'spectrum' and volume >= config.chroma_min_volume
                and row['time'] - audio_time < .25 and row['section'] != 'quiet'):
            frequency = spectrum_frequency(row['data'], centers, config.spectrum_curve)
            if frequency:
                frequencies.append(frequency)
    if len(frequencies) < 2:
        raise ValueError('Need at least two active, paired spectrum samples to calibrate')
    return {'active_spectrum_samples': len(frequencies),
            'frequency_p10_p90_hz': [round(percentile(frequencies, p), 2) for p in (.1, .9)],
            'frequency_min_max_hz': [min(frequencies), max(frequencies)],
            'sections': sections, 'spectrum_edges_hz': config.spectrum_edges,
            'spectrum_curve': config.spectrum_curve, 'limitations': LIMITS}


def feature_frames(records, config, fps=20, tail=8):
    """Causal sample-and-hold; each recorded event is consumed once, with age."""
    f = AudioFeatures()
    f.calibrating = False
    index = 0
    section = 'start'
    end = records[-1]['time']
    for frame in range(math.ceil((end + tail) * fps) + 1):
        now = frame / fps
        dt = 1 / fps
        f.attackEvent = f.yellEvent = False
        yell_peak = 0.0
        f.attack *= math.exp(-dt / config.attack_release_s)
        while index < len(records) and records[index]['time'] <= now:
            row = records[index]
            index += 1
            section = row['section']
            kind, data = row['kind'], row['data']
            if kind == 'audio':
                for key, value in data.items():
                    setattr(f, key, value)
            elif kind == 'spectrum':
                f.spectrum = data
            elif kind == 'attack':
                f.attackEvent = True
                f.attackAge = now - row['time']
                f.attack = data
            elif kind == 'yell':
                f.yellEvent = True
                f.yellAge = now - row['time']
                yell_peak = max(yell_peak, data)
        if now > end:
            section = 'synthetic fade (not recorded)'
            f.volume = f.drone = f.harmonics = f.growl = f.vocal = f.roughness = 0.0
            f.spectrum = (0.0,) * 8
            f.active = False
        f.decay = max(f.volume, f.decay * math.exp(-dt / config.decay_s))
        held_vocal = f.vocal
        if f.yellEvent:
            f.vocal = max(f.vocal, yell_peak)
        yield now, section, f
        f.vocal = held_vocal


def render_replay(records, config, fps=20, tail=8):
    # Saved audio has no device-voltage measurements; replay only audio effects.
    names = EFFECT_NAMES[:5]
    scenes = [CulvertAnimation(Config(**dict(vars(config), effect_index=i))) for i in range(len(names))]
    frames, sections = [], []
    for now, section, features in feature_frames(records, config, fps, tail):
        # All effects get exactly the same features and event edges.
        frames.append(base64.b64encode(b''.join(a.render(features, 1/fps) for a in scenes)).decode())
        sections.append(section)
    return {'fps': fps, 'names': names, 'frames': frames, 'sections': sections,
            'brightness': config.brightness, 'duration': now, 'limits': LIMITS}


HTML = '''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Didgeridoo effect replay</title>
<style>body{background:#090516;color:#e7e3ff;font:16px system-ui;margin:2rem}button,input{margin:.5rem}main{display:flex;flex-wrap:wrap;gap:24px}canvas{width:320px;height:160px;background:#000;border:1px solid #723b91;border-radius:8px}p{max-width:1000px;color:#b9afc9}input{width:min(70vw,900px)}h2{color:#40e9ed}</style>
<h1>Saved didgeridoo · effect replay</h1><p id="limits"></p>
<button id="play">Play</button><input id="seek" aria-label="Playback position" type="range" min="0" value="0"><output id="status"></output><main></main>
<script>
const data=REPLAY_DATA;
document.querySelector('#limits').textContent=data.limits;
const canvases=data.names.map(name=>{const wrap=document.createElement('section'), title=document.createElement('h2'), c=document.createElement('canvas');title.textContent=name;c.width=320;c.height=160;wrap.append(title,c);document.querySelector('main').append(wrap);return c.getContext('2d')});
const seek=document.querySelector('#seek'), play=document.querySelector('#play');seek.max=data.frames.length-1;
let index=0,playing=false,started=0;
function draw(){const raw=atob(data.frames[index]);canvases.forEach((ctx,e)=>{ctx.clearRect(0,0,320,160);for(let p=0;p<32;p++){const k=e*96+p*3, gain=1/data.brightness;const g=raw.charCodeAt(k)*gain,r=raw.charCodeAt(k+1)*gain,b=raw.charCodeAt(k+2)*gain;ctx.fillStyle=`rgb(${r},${g},${b})`;ctx.beginPath();ctx.arc(p%8*40+20,Math.floor(p/8)*40+20,15,0,Math.PI*2);ctx.fill()}});seek.value=index;document.querySelector('#status').textContent=`${(index/data.fps).toFixed(1)}s · ${data.sections[index]}`}
function tick(now){if(playing){index=Math.min(data.frames.length-1,Math.floor((now-started)*data.fps/1000));draw();if(index===data.frames.length-1){playing=false;play.textContent='Play'}}requestAnimationFrame(tick)}
play.onclick=()=>{playing=!playing;if(playing){if(index===data.frames.length-1)index=0;started=performance.now()-index/data.fps*1000}play.textContent=playing?'Pause':'Play'};
seek.oninput=()=>{index=Number(seek.value);started=performance.now()-index/data.fps*1000;draw()};draw();requestAnimationFrame(tick);
</script></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', type=Path, default=Path('.artifacts/replay.html'))
    parser.add_argument('--web-data', type=Path, help='Export public pixel frames and section labels only')
    parser.add_argument('--calibrate', action='store_true', help='Use this take’s p10/p90 for preview only')
    parser.add_argument('--fps', type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.fps <= 60:
        parser.error('--fps must be 1..60')
    records = read_records(args.capture)
    config = Config()
    report = calibration(records, config)
    report['source_sha256'] = hashlib.sha256(args.capture.read_bytes()).hexdigest()
    root = Path(__file__).resolve().parents[1]
    report['renderer_sha256'] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                                 for name in ('animation.py', 'effects.py', 'config.py', 'tools/replay.py')}
    if args.calibrate:
        config = Config(chroma_frequency_hz=tuple(report['frequency_p10_p90_hz']))
    report['render_frequency_hz'] = config.chroma_frequency_hz
    report['renderer_config'] = {name: getattr(config, name) for name in dir(config)
                                 if not name.startswith('_') and not callable(getattr(config, name))}
    data = render_replay(records, config, args.fps)
    if args.web_data:
        args.web_data.parent.mkdir(parents=True, exist_ok=True)
        args.web_data.write_text(json.dumps(data, separators=(',', ':')) + '\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(HTML.replace('REPLAY_DATA', json.dumps(data).replace('<', '\\u003c')))
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items()
                      if key != 'renderer_config'}, indent=2))
    print('Replay:', args.output.resolve())


if __name__ == '__main__':
    main()
