# Sound Analysis Virtual Consumer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the review page to Sound Analysis and add a sticky, effect-selectable virtual consumer that displays the exact Python-rendered 4×8 FeatherWing frame.

**Architecture:** Keep `CulvertAnimation` as the only renderer. The offline Python pipeline converts each physical-order GRB frame into 32 logical portrait RGB pixels, while small pure JavaScript helpers select the available effect and node-`0` timeline for the DOM renderer.

**Tech Stack:** Python 3/unittest, browser ES modules/node:test, HTML/CSS, Playwright, esbuild

---

### Task 1: Serialize exact portrait consumer frames

**Files:**
- Modify: `tests/test_sound_review.py`
- Modify: `tools/sound_review.py`

- [x] **Step 1: Write failing conversion and frame-shape tests**

Replace the grouped-pixel import and test with a portrait conversion test that
sets unique physical GRB values and asserts logical row-major RGB order through
the shared FeatherWing mapping:

```python
from effects import FEATHERWING_PORTRAIT
from tools.sound_review import portrait_pixels

def test_portrait_pixels_converts_grb_and_reorders_physical_pixels(self):
    grb = bytearray(96)
    for physical in range(32):
        offset = physical * 3
        grb[offset : offset + 3] = bytes((physical, physical + 32, physical + 64))

    pixels = portrait_pixels(grb)

    self.assertEqual(len(pixels), 32)
    for logical, physical in enumerate(FEATHERWING_PORTRAIT):
        self.assertEqual(
            pixels[logical],
            [physical + 32, physical, physical + 64],
        )
```

Update the renderer test to expect 32 RGB triples and assert the returned layout
metadata:

```python
self.assertEqual(effects["pixel_count"], 32)
self.assertEqual(
    effects["pixel_layout"],
    {"columns": 4, "rows": 8, "order": "row-major-portrait"},
)
self.assertEqual(len(effects["frames"]["Spectrum"]["0"][0]["pixels_rgb"]), 32)
```

Update the neutral delayed-frame assertion from eight to 32 dark pixels.

- [x] **Step 2: Run focused tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_sound_review.SoundReviewEffectTests.test_portrait_pixels_converts_grb_and_reorders_physical_pixels \
  tests.test_sound_review.SoundReviewEffectTests.test_render_effects_groups_renderer_output_for_three_nodes
```

Expected: FAIL because `portrait_pixels` and full-frame metadata do not exist and
the renderer still emits eight grouped pixels.

- [x] **Step 3: Implement physical-GRB to portrait-RGB conversion**

Import the shared mapping and replace `group_pixels` with a strict one-wing
converter:

```python
from effects import EFFECT_NAMES, FEATHERWING_PORTRAIT

def portrait_pixels(grb_bytes, mapping=FEATHERWING_PORTRAIT):
    """Convert one physical-order GRB wing to logical portrait RGB pixels."""
    if not isinstance(grb_bytes, (bytes, bytearray, memoryview)):
        raise ValueError("grb_bytes must be a byte sequence")
    if len(grb_bytes) != len(mapping) * 3:
        raise ValueError("Renderer output must contain one complete 32-pixel wing")
    return [
        [
            grb_bytes[physical * 3 + 1],
            grb_bytes[physical * 3],
            grb_bytes[physical * 3 + 2],
        ]
        for physical in mapping
    ]
```

Use `portrait_pixels(pixels)` in `render_effects`, add:

```python
"pixel_count": 32,
"pixel_layout": {
    "columns": 4,
    "rows": 8,
    "order": "row-major-portrait",
},
```

and replace the manifest’s `pixel_groups` field with the same full-frame
metadata.

- [x] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.test_sound_review.SoundReviewEffectTests
```

Expected: PASS with every rendered effect/node frame containing 32 RGB pixels.

### Task 2: Add pure effect-selection behavior

**Files:**
- Modify: `web/test/review-mode.test.mjs`
- Modify: `web/review-mode.mjs`

- [x] **Step 1: Write failing helper tests**

Add tests for declared-order discovery, object-key fallback, preferred selection,
fallback selection, node-`0` lookup, and malformed data:

```javascript
import {
  localReviewDataUrl,
  reviewEffectFrames,
  reviewEffectNames,
  selectReviewEffect,
} from '../review-mode.mjs';

const effects={
 effects:['Spectrum','Ember','Chroma'],
 frames:{
  Spectrum:{'0':[{time_ms:0,pixels_rgb:[]}]},
  Ember:{'0':[{time_ms:0,pixels_rgb:[]}]},
  Chroma:{'0':[{time_ms:0,pixels_rgb:[]}]},
 }
};

test('review effects preserve declared order and preferred selection',()=>{
 assert.deepEqual(reviewEffectNames(effects),['Spectrum','Ember','Chroma']);
 assert.equal(selectReviewEffect(effects,'Chroma'),'Chroma');
 assert.equal(selectReviewEffect(effects,'Ripple'),'Spectrum');
});

test('review effect frames use virtual node zero and reject malformed rows',()=>{
 assert.equal(reviewEffectFrames(effects,'Ember'),effects.frames.Ember['0']);
 assert.deepEqual(reviewEffectFrames({frames:{Ember:{'0':{}}}},'Ember'),[]);
 assert.deepEqual(reviewEffectNames({frames:{Ripple:{'0':[]}}}),['Ripple']);
 assert.equal(selectReviewEffect({frames:{}},'Spectrum'),null);
});
```

- [x] **Step 2: Run unit tests and verify RED**

Run:

```bash
npm test -- --test-name-pattern='review effect'
```

Expected: FAIL because the three helper exports do not exist.

- [x] **Step 3: Implement minimal pure helpers**

Add focused helpers without DOM dependencies:

```javascript
export function reviewEffectNames(effects){
 const frames=effects?.frames;
 if(!frames||typeof frames!=='object'||Array.isArray(frames))return [];
 const declared=Array.isArray(effects.effects)?effects.effects:Object.keys(frames);
 return [...new Set(declared)].filter(name=>
  typeof name==='string'&&frames[name]&&typeof frames[name]==='object'&&!Array.isArray(frames[name])
 );
}

export function selectReviewEffect(effects,preferred){
 const names=reviewEffectNames(effects);
 return names.includes(preferred)?preferred:(names[0]??null);
}

export function reviewEffectFrames(effects,effect){
 const rows=effects?.frames?.[effect]?.['0'];
 return Array.isArray(rows)?rows:[];
}
```

- [x] **Step 4: Run unit tests and verify GREEN**

Run:

```bash
npm test
```

Expected: PASS.

### Task 3: Build the sticky 4×8 review consumer

**Files:**
- Modify: `web/test/app.spec.js`
- Modify: `web/review.html`
- Modify: `web/review-page.js`

- [x] **Step 1: Write the failing browser behavior test**

Extend the synchronized review fixture to include all five effect names and
32-pixel Spectrum/Ember/Aurora/Ripple/Chroma frames. Add assertions that:

```javascript
await expect(page.getByRole('heading',{name:'Sound Analysis',exact:true})).toBeVisible();
const effect=page.getByRole('combobox',{name:'Effect'});
await expect(effect.locator('option')).toHaveText(['Spectrum','Ember','Aurora','Ripple','Chroma']);
await expect(page.locator('#review-led .led-pixel')).toHaveCount(32);
await position.fill('500');
await position.dispatchEvent('input');
await effect.selectOption('Chroma');
await expect(position).toHaveValue('500');
await expect(page.locator('#review-led')).toHaveAttribute('data-effect','Chroma');
await expect(page.locator('#review-led')).toHaveAttribute('aria-label',/Chroma.*0\.50 s/);
const columns=await page.locator('#review-led').evaluate(node=>getComputedStyle(node).gridTemplateColumns.split(' ').length);
expect(columns).toBe(4);
const railPosition=await page.locator('.review-consumer-rail').evaluate(node=>getComputedStyle(node).position);
expect(railPosition).toBe((await page.viewportSize()).width<=700?'static':'sticky');
```

Also assert that an effects-empty bundle keeps 32 dark pixels and a disabled
Effect selector.

- [x] **Step 2: Run the focused browser test and verify RED**

Run:

```bash
npm run test:browser -- --grep='virtual consumer'
```

Expected: FAIL because the heading, effect selector, 32-pixel matrix, and sticky
rail do not exist yet.

- [x] **Step 3: Implement the review structure and responsive styles**

In `web/review.html`:

- change the `h1` text to `Sound Analysis`;
- wrap protected content in `.review-layout`;
- add `.review-consumer-rail` before `.review-analysis`;
- move the virtual-consumer panel into that rail;
- add `<select id="review-effect" disabled></select>` above the matrix;
- remove the old bottom virtual-consumer section;
- change `.led-view` to four equal columns and a portrait width;
- use a desktop grid with a sticky rail and a one-column, non-sticky layout at
  `max-width:700px`.

The key styles are:

```css
.review-layout{display:grid;grid-template-columns:minmax(180px,220px) minmax(0,1fr);gap:18px;align-items:start}
.review-consumer-rail{position:sticky;top:86px;align-self:start}
.review-consumer-panel{margin:18px 0}
.review-analysis{min-width:0}
.led-view{grid-template-columns:repeat(4,minmax(20px,1fr));max-width:220px}
@media(max-width:700px){
 .review-layout{grid-template-columns:1fr}
 .review-consumer-rail{position:static}
 .review-consumer-panel{margin-bottom:0}
}
```

- [x] **Step 4: Connect selection and synchronized rendering**

Import the pure helpers into `web/review-page.js`, add `effect: 'Spectrum'` to
state, cache `#review-effect`, and implement:

```javascript
function renderEffectOptions(){
 const names=reviewEffectNames(state.bundle?.effects);
 state.effect=selectReviewEffect(state.bundle?.effects,state.effect);
 effectSelect.replaceChildren(...names.map(name=>{
  const option=document.createElement('option');
  option.value=name;
  option.textContent=name;
  return option;
 }));
 effectSelect.disabled=!state.effect;
 if(state.effect)effectSelect.value=state.effect;
}
```

Use `reviewEffectFrames(state.bundle?.effects,state.effect)` for frame lookup.
Always create exactly 32 `.led-pixel` elements, clamping channels as today.
Set `data-effect` and an accessible label containing the effect and formatted
frame time. On selector change, update only `state.effect` and call
`renderLedFrame(state.timeMs)`.

Call `renderEffectOptions()` during bundle configuration before the initial
`setTime`. During `clearReview`, clear and disable the selector but retain
`state.effect` so a supported choice survives recording changes; render a dark
32-pixel matrix. Initialize the page with the same dark matrix before online or
local loading begins.

- [x] **Step 5: Run browser tests and verify GREEN**

Run:

```bash
npm run test:browser -- --grep='virtual consumer|synchronizes all tracks|hosted review'
```

Expected: PASS in desktop Chromium, mobile Chromium, and mobile WebKit.

### Task 4: Regenerate and verify the complete review path

**Files:**
- Generated and ignored: `firebase/functions/review-data/`
- Generated and ignored: `.artifacts/sound-review/`

- [x] **Step 1: Run focused Python and JavaScript suites**

```bash
.venv/bin/python -m unittest tests.test_sound_review tests.test_review_library
npm test
```

Expected: PASS.

- [x] **Step 2: Rebuild authenticated review bundles and inspect schema**

```bash
make review-library
```

Expected: generated bundles contain five effect timelines, 32 RGB pixels per
frame, and 4×8 portrait layout metadata; no source labels or recordings change.

- [x] **Step 3: Run browser and build verification**

```bash
npm run test:browser
npm run build
```

Expected: all desktop/mobile browser projects pass and `web/dist` builds.

- [x] **Step 4: Run project-wide verification**

```bash
make check
git diff --check
git status --short
```

Expected: all host tests pass, the diff is whitespace-clean, and only the
approved spec, plan, source, and test files are tracked changes. Do not commit
unless the user explicitly requests it.
