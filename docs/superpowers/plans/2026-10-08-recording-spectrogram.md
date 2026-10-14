# Recording Spectrogram Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic log-frequency spectrogram beneath the recording waveform and display each detected event on its own line.

**Architecture:** The offline Python review pipeline computes a compact 64-row, fixed-dBFS spectrogram from each existing PCM hop and embeds it in review bundle schema version 2. A focused browser module validates and rasterizes the payload; the existing review page places its canvas in the waveform timeline so zoom, pan, seek, and playhead state stay shared.

**Tech Stack:** Python 3, NumPy, `unittest`, browser ES modules, Canvas 2D, Node test runner, Playwright, Firebase review-library generation.

**Repository note:** Do not create commits unless the user explicitly authorizes them. The checkpoints below end with verification and `git diff` review rather than automatic commits.

---

## File Map

- Modify `tools/sound_review.py`: generate the fixed-scale spectrogram and add it to analysis and review bundles.
- Modify `tests/test_sound_review.py`: cover silence, deterministic tone placement, and schema-version-2 artifact output.
- Modify `tests/test_review_library.py`: verify generated authenticated-library bundles carry aligned spectrogram data.
- Create `web/spectrogram.mjs`: validate spectrogram payloads, map intensities to the approved palette, and paint a DPR-aware canvas.
- Create `web/test/spectrogram.test.mjs`: unit-test browser-side validation and raster ordering without a browser.
- Modify `tools/build_web.mjs`: copy the standalone spectrogram module into built web output.
- Modify `Makefile`: copy the module into local `make sound-review` output.
- Modify `web/review-page.js`: normalize spectrogram data and render it inside the existing shared timeline.
- Modify `web/review.html`: add shared-timeline spectrogram styles, frequency/intensity labels, and a single-column detector list.
- Modify `web/test/app.spec.js`: test layout, shared interactions, switching, missing/malformed data, and one-event-per-line behavior.
- Modify `README.md`: replace the “spectrogram is not currently shown” limitation with the implemented display semantics.

### Task 1: Generate a Deterministic Log-Frequency Spectrogram

**Files:**
- Modify: `tests/test_sound_review.py:19-40,391-637`
- Modify: `tools/sound_review.py:1-25,243-255`

- [ ] **Step 1: Write failing generator tests**

Add `from tools import sound_review` beside the existing imports, then add these
focused tests to `SoundReviewAnalysisTests`. The explicit `hasattr` assertions
make the first run fail as a test assertion rather than aborting module import:

```python
def test_spectrogram_preview_maps_silence_to_fixed_floor(self):
    config = Config()
    hops = [array.array("h", [0]) * config.hop_size for _ in range(2)]

    self.assertTrue(hasattr(sound_review, "spectrogram_preview"))
    preview = sound_review.spectrogram_preview(hops, config)

    self.assertEqual(preview["min_frequency_hz"], 31.25)
    self.assertEqual(preview["max_frequency_hz"], 8000.0)
    self.assertEqual(preview["min_dbfs"], -90.0)
    self.assertEqual(preview["max_dbfs"], 0.0)
    self.assertEqual(preview["rows"], 64)
    self.assertEqual(preview["columns"], 2)
    self.assertEqual(preview["frames"], [[0] * 64, [0] * 64])

def test_spectrogram_preview_places_tone_in_expected_log_band(self):
    config = Config()
    frequency_hz = 500.0
    samples = array.array(
        "h",
        (
            round(12000 * math.sin(2 * math.pi * frequency_hz * index / config.sample_rate))
            for index in range(config.hop_size)
        ),
    )

    self.assertTrue(hasattr(sound_review, "spectrogram_preview"))
    first = sound_review.spectrogram_preview([samples], config)
    second = sound_review.spectrogram_preview([samples], config)
    peak_row = max(range(first["rows"]), key=first["frames"][0].__getitem__)
    expected_row = math.floor(
        math.log(frequency_hz / first["min_frequency_hz"])
        / math.log(first["max_frequency_hz"] / first["min_frequency_hz"])
        * first["rows"]
    )

    self.assertEqual(first, second)
    self.assertLessEqual(abs(peak_row - expected_row), 1)
    self.assertGreater(first["frames"][0][peak_row], 0)
    self.assertTrue(all(0 <= value <= 255 for value in first["frames"][0]))
```

- [ ] **Step 2: Run the tests and confirm RED**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_sound_review.SoundReviewAnalysisTests.test_spectrogram_preview_maps_silence_to_fixed_floor \
  tests.test_sound_review.SoundReviewAnalysisTests.test_spectrogram_preview_places_tone_in_expected_log_band
```

Expected: two assertion failures because `spectrogram_preview` does not exist.

- [ ] **Step 3: Implement the minimal generator**

Import host NumPy in `tools/sound_review.py` and add constants plus the generator immediately after `waveform_preview`:

```python
import numpy as np


SPECTROGRAM_MIN_HZ = 31.25
SPECTROGRAM_MIN_DBFS = -90.0
SPECTROGRAM_MAX_DBFS = 0.0
SPECTROGRAM_ROWS = 64


def spectrogram_preview(hops, config):
    """Return fixed-scale, byte-quantized log-frequency magnitudes per hop."""
    fft_size = config.fft_size
    if config.hop_size != fft_size:
        raise ValueError("Spectrogram preview requires contiguous full FFT hops")
    max_frequency_hz = config.sample_rate / 2.0
    window = np.hanning(fft_size)
    amplitude_scale = 2.0 / (float(np.sum(window)) * 32768.0)
    frequencies = np.fft.rfftfreq(fft_size, 1.0 / config.sample_rate)
    edges = np.geomspace(SPECTROGRAM_MIN_HZ, max_frequency_hz, SPECTROGRAM_ROWS + 1)
    band_indexes = []
    for row, (low_hz, high_hz) in enumerate(zip(edges, edges[1:])):
        upper = frequencies <= high_hz if row == SPECTROGRAM_ROWS - 1 else frequencies < high_hz
        indexes = np.flatnonzero((frequencies >= low_hz) & upper)
        if not len(indexes):
            center_hz = math.sqrt(low_hz * high_hz)
            indexes = np.array([int(np.argmin(np.abs(frequencies - center_hz)))])
        band_indexes.append(indexes)

    floor_amplitude = 10.0 ** (SPECTROGRAM_MIN_DBFS / 20.0)
    frames = []
    for hop in hops:
        if len(hop) != fft_size:
            raise ValueError("Expected one complete PCM hop")
        samples = np.asarray(hop, dtype=float)
        samples -= float(np.mean(samples))
        amplitude = np.abs(np.fft.rfft(samples * window)) * amplitude_scale
        amplitude[-1] *= 0.5
        frame = []
        for indexes in band_indexes:
            peak = max(float(np.max(amplitude[indexes])), floor_amplitude)
            dbfs = max(SPECTROGRAM_MIN_DBFS, min(SPECTROGRAM_MAX_DBFS, 20.0 * math.log10(peak)))
            frame.append(round((dbfs - SPECTROGRAM_MIN_DBFS) * 255.0 / (SPECTROGRAM_MAX_DBFS - SPECTROGRAM_MIN_DBFS)))
        frames.append(frame)
    return {
        "min_frequency_hz": SPECTROGRAM_MIN_HZ,
        "max_frequency_hz": max_frequency_hz,
        "min_dbfs": SPECTROGRAM_MIN_DBFS,
        "max_dbfs": SPECTROGRAM_MAX_DBFS,
        "rows": SPECTROGRAM_ROWS,
        "columns": len(frames),
        "frames": frames,
    }
```

- [ ] **Step 4: Run the focused generator tests and confirm GREEN**

Run the command from Step 2.

Expected: two tests pass with no warnings or errors.

- [ ] **Step 5: Run the complete Python sound-review test module**

Run:

```bash
.venv/bin/python -m unittest tests.test_sound_review
```

Expected: all existing sound-review tests still pass.

### Task 2: Add Spectrogram Data to Review Bundle Schema Version 2

**Files:**
- Modify: `tests/test_sound_review.py:1193-1240`
- Modify: `tests/test_review_library.py:103-134`
- Modify: `tools/sound_review.py:527-589,1140-1160`

- [ ] **Step 1: Write failing artifact and library assertions**

Update `test_artifacts_include_a_deterministic_browser_review_bundle` so its expected key set includes `"spectrogram"`, its expected schema version is `2`, and it asserts alignment:

```python
self.assertEqual(bundle["schema_version"], 2)
self.assertEqual(bundle["spectrogram"]["columns"], len(bundle["waveform"]))
self.assertEqual(bundle["spectrogram"]["rows"], 64)
self.assertTrue(
    all(
        len(frame) == bundle["spectrogram"]["rows"]
        for frame in bundle["spectrogram"]["frames"]
    )
)
```

In `test_build_is_ordered_deterministic_and_removes_stale_entries`, add:

```python
self.assertEqual(bundle["schema_version"], 2)
self.assertEqual(bundle["spectrogram"]["columns"], len(bundle["waveform"]))
self.assertEqual(bundle["spectrogram"]["rows"], 64)
```

- [ ] **Step 2: Run the bundle tests and confirm RED**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_sound_review.SoundReviewEffectTests.test_artifacts_include_a_deterministic_browser_review_bundle \
  tests.test_review_library.ReviewLibraryTests.test_build_is_ordered_deterministic_and_removes_stale_entries
```

Expected: failures for missing `spectrogram` and schema version `1`.

- [ ] **Step 3: Integrate the generator into analysis and artifact output**

Add the preview to the `analyze_wav` result:

```python
return {
    "info": info,
    "labels": labels,
    "waveform": waveform_preview(hops),
    "spectrogram": spectrogram_preview(hops, config),
    "features": features,
    "events": list(events),
    "comparison": comparison,
    "fps": fps,
    "feature_fps": config.sample_rate / config.hop_size,
    "detector_config": _serialize_detector_config(detector.config),
}
```

Update only the browser review bundle schema number and payload in `build_artifacts`:

```python
{
    "schema_version": 2,
    "duration_ms": result["info"]["duration_ms"],
    "sample_rate_hz": result["info"]["sample_rate_hz"],
    "audio_url": audio_url,
    "waveform": result["waveform"],
    "spectrogram": result["spectrogram"],
    "labels": result["labels"]["labels"],
    "features": result["features"],
    "events": result["events"],
    "comparison": result["comparison"],
    "effects": result["effects"],
}
```

Keep the run-manifest schema at `1`; it is a separate contract.

- [ ] **Step 4: Run focused bundle tests and confirm GREEN**

Run the Step 2 command with the confirmed class names.

Expected: both tests pass.

- [ ] **Step 5: Verify deterministic library generation**

Run:

```bash
.venv/bin/python -m unittest tests.test_review_library tests.test_sound_review
```

Expected: both modules pass, including byte-for-byte repeated library generation and unchanged labels.

### Task 3: Validate and Rasterize Spectrograms in a Focused Browser Module

**Files:**
- Create: `web/spectrogram.mjs`
- Create: `web/test/spectrogram.test.mjs`

- [ ] **Step 1: Write failing browser-module unit tests**

Create `web/test/spectrogram.test.mjs`. Import dynamically inside each test so
the first run produces assertion failures rather than an uncaught module-load
error:

```javascript
import assert from 'node:assert/strict';
import test from 'node:test';
const valid={
  min_frequency_hz:31.25,max_frequency_hz:8000,
  min_dbfs:-90,max_dbfs:0,rows:2,columns:2,
  frames:[[0,255],[64,128]],
};

async function loadModule(){
  return import('../spectrogram.mjs').catch(()=>null);
}

test('missing spectrogram remains backward compatible',async()=>{
  const module=await loadModule();
  assert.ok(module,'spectrogram module should exist');
  assert.equal(module.normalizeSpectrogram(undefined,2),null);
});

test('normalizes aligned byte frames and rasterizes high frequencies on top',async()=>{
  const module=await loadModule();
  assert.ok(module,'spectrogram module should exist');
  const normalized=module.normalizeSpectrogram(valid,2);
  const rgba=module.spectrogramRgba(normalized);
  assert.equal(rgba.length,2*2*4);
  assert.deepEqual([...rgba.slice(0,4)],[255,207,106,255]);
  assert.deepEqual([...rgba.slice(8,12)],[7,11,35,255]);
});

test('rejects malformed or horizontally misaligned spectrograms',async()=>{
  const module=await loadModule();
  assert.ok(module,'spectrogram module should exist');
  assert.throws(()=>module.normalizeSpectrogram({...valid,columns:3},2),/columns/);
  assert.throws(()=>module.normalizeSpectrogram({...valid,frames:[[0,256],[64,128]]},2),/byte/);
  assert.throws(()=>module.normalizeSpectrogram({...valid,min_dbfs:0,max_dbfs:-90},2),/dB/);
});
```

- [ ] **Step 2: Run the module test and confirm RED**

Run:

```bash
node_modules/.bin/node --test web/test/spectrogram.test.mjs
```

Expected: three assertion failures stating that the spectrogram module should exist.

- [ ] **Step 3: Implement validation, palette interpolation, and canvas painting**

Create `web/spectrogram.mjs` with these exported interfaces:

```javascript
const PALETTE=[
  {at:0,rgb:[7,11,35]},
  {at:.35,rgb:[22,93,117]},
  {at:.68,rgb:[212,91,114]},
  {at:1,rgb:[255,207,106]},
];

function finite(value,name){
  if(typeof value!=='number'||!Number.isFinite(value))throw new Error(`${name} must be finite`);
  return value;
}

function positiveInteger(value,name){
  if(!Number.isInteger(value)||value<=0)throw new Error(`${name} must be a positive integer`);
  return value;
}

export function normalizeSpectrogram(value,waveformColumns){
  if(value===undefined)return null;
  if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('spectrogram must be an object');
  const rows=positiveInteger(value.rows,'spectrogram rows');
  const columns=positiveInteger(value.columns,'spectrogram columns');
  if(columns!==waveformColumns)throw new Error('spectrogram columns must match waveform');
  const minFrequencyHz=finite(value.min_frequency_hz,'minimum frequency');
  const maxFrequencyHz=finite(value.max_frequency_hz,'maximum frequency');
  if(minFrequencyHz<=0||maxFrequencyHz<=minFrequencyHz)throw new Error('spectrogram frequency bounds are invalid');
  const minDbfs=finite(value.min_dbfs,'minimum dBFS');
  const maxDbfs=finite(value.max_dbfs,'maximum dBFS');
  if(maxDbfs<=minDbfs)throw new Error('spectrogram dB bounds are invalid');
  if(!Array.isArray(value.frames)||value.frames.length!==columns)throw new Error('spectrogram frame count is invalid');
  const frames=value.frames.map(frame=>{
    if(!Array.isArray(frame)||frame.length!==rows)throw new Error('spectrogram row count is invalid');
    return frame.map(sample=>{
      if(!Number.isInteger(sample)||sample<0||sample>255)throw new Error('spectrogram values must be bytes');
      return sample;
    });
  });
  return {minFrequencyHz,maxFrequencyHz,minDbfs,maxDbfs,rows,columns,frames};
}

function colorFor(value){
  const position=value/255;
  const right=PALETTE.findIndex(stop=>position<=stop.at);
  if(right<=0)return PALETTE[0].rgb;
  const low=PALETTE[right-1],high=PALETTE[right];
  const mix=(position-low.at)/(high.at-low.at);
  return low.rgb.map((channel,index)=>Math.round(channel+(high.rgb[index]-channel)*mix));
}

export function spectrogramRgba(spectrogram){
  const rgba=new Uint8ClampedArray(spectrogram.columns*spectrogram.rows*4);
  spectrogram.frames.forEach((frame,x)=>frame.forEach((value,row)=>{
    const y=spectrogram.rows-1-row;
    const offset=(y*spectrogram.columns+x)*4;
    rgba.set([...colorFor(value),255],offset);
  }));
  return rgba;
}

export function paintSpectrogram(canvas,spectrogram,devicePixelRatio=1){
  const width=Math.max(1,Math.round(canvas.clientWidth*devicePixelRatio));
  const height=Math.max(1,Math.round(canvas.clientHeight*devicePixelRatio));
  canvas.width=width;canvas.height=height;
  const source=document.createElement('canvas');
  source.width=spectrogram.columns;source.height=spectrogram.rows;
  source.getContext('2d').putImageData(new ImageData(spectrogramRgba(spectrogram),spectrogram.columns,spectrogram.rows),0,0);
  const context=canvas.getContext('2d');
  context.imageSmoothingEnabled=false;
  context.drawImage(source,0,0,width,height);
}
```

- [ ] **Step 4: Run the module tests and confirm GREEN**

Run:

```bash
node_modules/.bin/node --test web/test/spectrogram.test.mjs
```

Expected: all three spectrogram module tests pass.

### Task 4: Render the Shared Timeline and Stack Detector Events

**Files:**
- Modify: `web/review.html:12-52,88-94,105-111`
- Modify: `web/review-page.js:1-120,420-560`
- Modify: `web/test/app.spec.js:91-405`
- Modify: `tools/build_web.mjs:8-10`
- Modify: `Makefile:84-92`

- [ ] **Step 1: Extend browser fixtures and write failing UI assertions**

Add a helper near the review fixtures in `web/test/app.spec.js` and include a matching payload in every fixture intended to exercise current schema behavior:

```javascript
function testSpectrogram(columns){
 return {min_frequency_hz:31.25,max_frequency_hz:8000,min_dbfs:-90,max_dbfs:0,
  rows:3,columns,frames:Array.from({length:columns},(_,column)=>[0,80+column*20,255-column*20])};
}
```

Add one browser test that verifies layout and shared interaction:

```javascript
test('review stacks a log spectrogram under the waveform on the shared timeline',async({page})=>{
 await routeReviewBundle(page,'/spectrogram-review.json');
 await page.goto('/review.html?data=/spectrogram-review.json');
 const amplitude=page.locator('.waveform-region');
 const spectrogram=page.locator('.spectrogram-region');
 await expect(page.locator('#review-spectrogram')).toBeVisible();
 const amplitudeBox=await amplitude.boundingBox();
 const spectrogramBox=await spectrogram.boundingBox();
 expect(spectrogramBox.y).toBeGreaterThanOrEqual(amplitudeBox.y+amplitudeBox.height);
 expect(Math.abs(spectrogramBox.width-amplitudeBox.width)).toBeLessThanOrEqual(1);
 await expect(spectrogram).toContainText('8 kHz');
 await expect(spectrogram).toContainText('31 Hz');
 await expect(spectrogram).toContainText('-90 dBFS');
 const waveform=page.locator('#review-waveform');
 const box=await waveform.boundingBox();
 await waveform.click({position:{x:box.width/2,y:spectrogramBox.y-box.y+spectrogramBox.height/2}});
 expect(Number(await page.getByRole('slider',{name:'Position'}).inputValue())).toBeGreaterThanOrEqual(495);
 await page.getByRole('slider',{name:'Zoom'}).fill('4');
 await page.getByRole('slider',{name:'Zoom'}).dispatchEvent('input');
 await expect(waveform).toHaveAttribute('data-zoom','4');
});
```

Extend the event-filter test after enabling Transient so it verifies distinct rows:

```javascript
const eventBoxes=await page.locator('#review-events li').evaluateAll(items=>items.map(item=>item.getBoundingClientRect().toJSON()));
expect(new Set(eventBoxes.map(box=>Math.round(box.y))).size).toBe(eventBoxes.length);
expect(eventBoxes.every(box=>box.width===eventBoxes[0].width)).toBeTruthy();
```

Add missing and malformed payload tests:

```javascript
test('review explains when an older bundle has no spectrogram',async({page})=>{
 await routeReviewBundle(page,'/older-review.json',{spectrogram:undefined});
 await page.goto('/review.html?data=/older-review.json');
 await expect(page.locator('.spectrogram-empty')).toContainText('unavailable');
});

test('review rejects malformed spectrogram bytes',async({page})=>{
 await routeReviewBundle(page,'/invalid-spectrogram.json',{spectrogram:{...testSpectrogram(4),frames:[[0,1,300],[0,1,2],[0,1,2],[0,1,2]]}});
 await page.goto('/review.html?data=/invalid-spectrogram.json');
 await expect(page.locator('#review-status')).toContainText(/could not load/i);
});
```

Replace `routeReviewBundle` with an override-aware helper that preserves the
existing audio route:

```javascript
async function routeReviewBundle(page,url='/gesture-review.json',overrides={}){
 const bundle={
  duration_ms:1000,
  audio_url:'/fixture.wav',
  waveform:[0,.2,.8,.3],
  spectrogram:testSpectrogram(4),
  labels:[{type:'drone',start_ms:200,end_ms:800}],
  events:[{type:'yell',time_ms:500,confidence:.9}],
  features:[{time_ms:500,volume:.8,drone:.7,vocal:.9,transient_strength:.2}],
  comparison:{},
  effects:{frames:{}},
  ...overrides,
 };
 await page.route(`**${url}`,route=>route.request().resourceType()==='document'
  ?route.continue():route.fulfill({json:bundle}));
 await page.route('**/fixture.wav',route=>route.abort());
}
```

Add `spectrogram:testSpectrogram(high?4:3)` to `hostedReview`, use four waveform
samples for the high recording, and assert `#review-spectrogram` has
`data-columns="3"` before switching and `data-columns="4"` afterward. This
proves a recording change replaces the raster rather than retaining stale data.

- [ ] **Step 2: Run focused browser tests and confirm RED**

Run:

```bash
PATH="$(pwd)/node_modules/.bin:$PATH" npm run test:browser -- --project=desktop-chromium --grep='spectrogram|event visibility'
```

Expected: failures because there is no canvas/region, malformed spectrograms are not validated, and events still use a wrapping flex row.

- [ ] **Step 3: Add the shared timeline structure and styles**

In `web/review.html`:

- change the panel heading to `Waveform and spectrogram`;
- change the viewport accessible label to `Audio waveform and log-frequency spectrogram timeline`;
- make `.timeline-track` a stacked container with enough height for an 84 px waveform and a 150 px spectrogram;
- move waveform bars and marker layers into `.waveform-region`;
- add `.spectrogram-region`, `.spectrogram-canvas`, `.spectrogram-axis`, `.spectrogram-legend`, and `.spectrogram-empty` rules;
- keep `.track-cursor` positioned across the complete stacked track; and
- add `#review-events.review-list{display:grid;grid-template-columns:minmax(0,1fr)}` plus full-width list-item styling.

Use these key dimensions and selectors so the browser assertions remain stable:

```css
.timeline-track{position:relative;min-height:234px}
.waveform-region{position:relative;height:84px}
.spectrogram-region{position:relative;height:150px;border-top:1px solid #46314f;background:#070b23}
.spectrogram-canvas{display:block;width:100%;height:100%}
.spectrogram-axis{position:absolute;inset:5px auto 5px 6px;display:flex;flex-direction:column;justify-content:space-between;pointer-events:none;color:#fff;font:10px ui-monospace,monospace;text-shadow:0 1px 3px #000}
.spectrogram-legend{position:absolute;right:7px;bottom:5px;color:#fff;font:10px ui-monospace,monospace;text-shadow:0 1px 3px #000}
.spectrogram-legend::before{content:"";display:inline-block;width:72px;height:8px;margin-right:5px;background:linear-gradient(90deg,#070b23,#165d75,#d45b72,#ffcf6a)}
#review-events.review-list{display:grid;grid-template-columns:minmax(0,1fr)}
#review-events.review-list>li{width:100%;box-sizing:border-box;padding:7px 9px;border:1px solid #46314f;border-radius:5px;background:#0b0a15}
```

- [ ] **Step 4: Normalize and render the spectrogram in the existing page**

At the top of `web/review-page.js`, import the new module:

```javascript
import {normalizeSpectrogram,paintSpectrogram} from './spectrogram.mjs';
```

In `normalizeBundle`, normalize the waveform first, then pass its length into `normalizeSpectrogram`:

```javascript
const waveformRows=Array.isArray(bundle.waveform)?bundle.waveform:[];
return {
  ...bundle,
  duration_ms:durationMs,
  waveform:waveformRows,
  spectrogram:normalizeSpectrogram(bundle.spectrogram,waveformRows.length),
  // existing normalized fields remain unchanged
};
```

Refactor `renderWaveform` to append, in order, a `.waveform-region`, a `.spectrogram-region`, and the shared `.track-cursor`. Put bars and marker layers inside the waveform region. For a current bundle, append this canvas and labels to the spectrogram region:

```javascript
const canvas=document.createElement('canvas');
canvas.id='review-spectrogram';
canvas.className='spectrogram-canvas';
canvas.dataset.columns=String(state.bundle.spectrogram.columns);
canvas.setAttribute('role','img');
canvas.setAttribute('aria-label',`Log-frequency spectrogram from ${state.bundle.spectrogram.minFrequencyHz} Hz to ${state.bundle.spectrogram.maxFrequencyHz} Hz, ${state.bundle.spectrogram.minDbfs} to ${state.bundle.spectrogram.maxDbfs} dBFS`);
spectrogramRegion.append(canvas,frequencyAxis(state.bundle.spectrogram),intensityLegend(state.bundle.spectrogram));
requestAnimationFrame(renderSpectrogramCanvas);
```

For a missing spectrogram, append a `.spectrogram-empty` paragraph containing `Spectrogram unavailable for this older review bundle.`. Implement `renderSpectrogramCanvas` as:

```javascript
function renderSpectrogramCanvas(){
 const canvas=waveform.querySelector('#review-spectrogram');
 if(canvas&&state.bundle?.spectrogram)paintSpectrogram(canvas,state.bundle.spectrogram,window.devicePixelRatio||1);
}
```

Use these helpers for the axis and legend referenced above:

```javascript
function frequencyLabel(value){
 return value>=1000?`${Number((value/1000).toFixed(2))} kHz`:`${Math.round(value)} Hz`;
}

function frequencyAxis(spectrogram){
 const axis=document.createElement('div');
 axis.className='spectrogram-axis';
 axis.append(
  Object.assign(document.createElement('span'),{textContent:frequencyLabel(spectrogram.maxFrequencyHz)}),
  Object.assign(document.createElement('span'),{textContent:frequencyLabel(spectrogram.minFrequencyHz)}),
 );
 return axis;
}

function intensityLegend(spectrogram){
 const legend=document.createElement('div');
 legend.className='spectrogram-legend';
 legend.textContent=`${spectrogram.minDbfs} dBFS → ${spectrogram.maxDbfs} dBFS`;
 return legend;
}
```

Create one observer after `waveformTrack` is available and repaint after zoom:

```javascript
const spectrogramResizeObserver=new ResizeObserver(renderSpectrogramCanvas);
spectrogramResizeObserver.observe(waveformTrack());

function setZoom(value){
 state.zoom=Math.max(1,Math.min(8,Number(value)));
 waveform.dataset.zoom=String(state.zoom);
 waveformTrack().style.setProperty('--timeline-zoom',state.zoom);
 requestAnimationFrame(renderSpectrogramCanvas);
}
```

Do not create a second scroll container or gesture state.

Add `web/spectrogram.mjs` beside the other standalone review modules in both
explicit copy lists:

```javascript
await copyFile('web/spectrogram.mjs',out+'/spectrogram.mjs');
```

```make
	cp web/spectrogram.mjs .artifacts/sound-review/spectrogram.mjs
```

Update `renderLabelOverlays`, `renderEventOverlays`, and their query sites to find layers inside `.waveform-region`; their existing class selectors and behavior otherwise stay unchanged.

- [ ] **Step 5: Run focused browser tests and confirm GREEN**

Run the Step 2 command.

Expected: spectrogram and event-row tests pass in Chromium.

- [ ] **Step 6: Run browser tests in both supported engines**

Run:

```bash
PATH="$(pwd)/node_modules/.bin:$PATH" npm run test:browser -- --grep='review'
```

Expected: all review tests pass in Chromium and WebKit, including existing seek/pan/filter/recording-switch behavior.

### Task 5: Document, Regenerate, and Verify the Complete Change

**Files:**
- Modify: `README.md:1084-1112`
- Generated and ignored: `firebase/functions/review-data/`

- [ ] **Step 1: Update the recording-review documentation**

Replace the current waveform-only limitation with text that states:

```markdown
The waveform is a normalized peak-amplitude preview; each bar summarizes one
1024-sample hop, about 64 ms at 16 kHz. Directly beneath it, the aligned
spectrogram shows 64 logarithmic frequency bands from 31.25 Hz to 8 kHz. Its
dark-blue-to-yellow colors use a fixed -90 to 0 dBFS range, so intensity remains
comparable when switching recordings. The spectrogram, waveform, labels and
detector markers share one playhead, zoom and horizontal pan. Detected events
are listed one per line.
```

- [ ] **Step 2: Rebuild the authenticated review library**

Run:

```bash
make review-library
```

Expected: two recordings are generated under ignored `firebase/functions/review-data/`, each `bundle.json` has schema version `2`, a 64-row spectrogram, and the same number of waveform and spectrogram columns.

- [ ] **Step 3: Run focused Node and browser validation**

Run:

```bash
PATH="$(pwd)/node_modules/.bin:$PATH" npm test
PATH="$(pwd)/node_modules/.bin:$PATH" npm run test:browser -- --grep='review|spectrogram'
```

Expected: Node tests and review browser tests pass in all configured browser projects.

- [ ] **Step 4: Run required repository validation**

Run:

```bash
make check
make web-test
```

Expected: Python compilation/unit tests, Node/function tests, Playwright tests, and Firebase emulator tests all pass. If an unrelated external emulator prerequisite fails, record the exact failing command and output; do not claim full validation.

- [ ] **Step 5: Review the final diff and generated-data boundary**

Run:

```bash
git status --short
git diff --check
git diff -- tools/sound_review.py tests/test_sound_review.py tests/test_review_library.py web/spectrogram.mjs web/test/spectrogram.test.mjs web/review-page.js web/review.html web/test/app.spec.js README.md
```

Expected: only the planned source, test, documentation, design, and plan files are uncommitted; ignored `firebase/functions/review-data/` is absent from `git status`; no WAV, label, credential, recording, or unrelated file changed.
