# Waveform Seek and Pan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let reviewers click the waveform to seek and drag a zoomed waveform to pan without changing the playhead.

**Architecture:** Add one pointer-gesture state machine to the existing review page. Keep all seeking in the existing `setTime()` synchronization path and use the waveform viewport's native horizontal scrolling for pan state; no review schema or audio-analysis changes are required.

**Tech Stack:** Browser JavaScript pointer events, CSS overflow/touch behavior, Playwright browser tests, Python sound-review artifact generator.

---

## File structure

- Modify `web/test/app.spec.js`: cover click-to-seek, playback continuity, drag threshold, zoomed panning, 1× bounds, and overlay-button behavior.
- Modify `web/review-page.js`: implement the pointer gesture state and coordinate-to-time conversion.
- Modify `web/review.html`: disclose grab state and preserve vertical touch scrolling.
- Modify ignored `.artifacts/samples/review/high-yell-01.labels.json`: save the user's authoritative 1020–6950 ms drone label.
- Regenerate ignored `.artifacts/sound-review/*`: rebuild the current local reviewer bundle after the tracked UI changes.

### Task 1: Specify direct waveform interaction

**Files:**
- Modify: `web/test/app.spec.js:91-163`
- Test: `web/test/app.spec.js`

- [ ] **Step 1: Add a test bundle helper and failing gesture tests**

Add a helper near the existing review tests so each interaction test receives the same deterministic bundle:

```js
async function routeReviewBundle(page,url='/gesture-review.json'){
 await page.route(`**${url}`,route=>route.request().resourceType()==='document'?route.continue():route.fulfill({json:{
  duration_ms:1000,
  audio_url:'/fixture.wav',
  waveform:[0,.2,.8,.3],
  labels:[{type:'drone',start_ms:200,end_ms:800}],
  events:[{type:'yell',time_ms:500,confidence:.9}],
  features:[{time_ms:500,volume:.8,drone:.7,vocal:.9,transient_strength:.2}],
  comparison:{},
  effects:{frames:{}}
 }}));
 await page.route('**/fixture.wav',route=>route.abort());
}
```

Add tests that use real Playwright pointer input:

```js
test('review waveform click seeks and preserves playback state',async({page})=>{
 await page.addInitScript(()=>{
  window.reviewCurrentTimeWrites=[];
  Object.defineProperty(HTMLMediaElement.prototype,'currentTime',{
   configurable:true,
   get(){return this.reviewCurrentTimeValue||0;},
   set(value){this.reviewCurrentTimeValue=value;window.reviewCurrentTimeWrites.push(value);}
  });
  HTMLMediaElement.prototype.play=async function(){};
  HTMLMediaElement.prototype.pause=function(){};
 });
 await routeReviewBundle(page);
 await page.goto('/review.html?data=/gesture-review.json');
 await page.locator('#review-audio').evaluate(audio=>{
  Object.defineProperty(audio,'src',{configurable:true,value:'mock://audio'});
  document.querySelector('#review-play').disabled=false;
 });
 await page.getByRole('button',{name:'Play',exact:true}).click();
 const waveform=page.locator('#review-waveform');
 const box=await waveform.boundingBox();
 await page.mouse.click(box.x+box.width/2,box.y+40);
 await expect(page.getByRole('slider',{name:'Position'})).toHaveValue('500');
 await expect(page.getByRole('button',{name:'Pause',exact:true})).toBeVisible();
 expect(await page.evaluate(()=>window.reviewCurrentTimeWrites)).toEqual([.5]);
});

test('review waveform drag pans when zoomed without seeking',async({page})=>{
 await routeReviewBundle(page);
 await page.goto('/review.html?data=/gesture-review.json');
 const position=page.getByRole('slider',{name:'Position'});
 await position.fill('400');
 await position.dispatchEvent('input');
 const zoom=page.getByRole('slider',{name:'Zoom'});
 await zoom.fill('4');
 await zoom.dispatchEvent('input');
 const waveform=page.locator('#review-waveform');
 const box=await waveform.boundingBox();
 await page.mouse.move(box.x+box.width*.75,box.y+40);
 await page.mouse.down();
 await page.mouse.move(box.x+box.width*.25,box.y+40);
 await page.mouse.up();
 expect(await waveform.evaluate(node=>node.scrollLeft)).toBeGreaterThan(0);
 await expect(position).toHaveValue('400');
});

test('review waveform separates shaky clicks from pans and stays bounded at 1x',async({page})=>{
 await routeReviewBundle(page);
 await page.goto('/review.html?data=/gesture-review.json');
 const waveform=page.locator('#review-waveform');
 const box=await waveform.boundingBox();
 await page.mouse.move(box.x+box.width*.25,box.y+40);
 await page.mouse.down();
 await page.mouse.move(box.x+box.width*.25+4,box.y+40);
 await page.mouse.up();
 expect(Number(await page.getByRole('slider',{name:'Position'}).inputValue())).toBeGreaterThan(250);
 await page.mouse.move(box.x+box.width*.75,box.y+40);
 await page.mouse.down();
 await page.mouse.move(box.x+box.width*.25,box.y+40);
 await page.mouse.up();
 expect(await waveform.evaluate(node=>node.scrollLeft)).toBe(0);
});
```

Extend the existing synchronization test after `.event-overlay` is rendered:

```js
 await page.locator('.event-overlay').click();
 await expect(page.getByRole('slider',{name:'Position'})).toHaveValue('500');
```

- [ ] **Step 2: Run the focused tests and verify the new behavior fails**

Run:

```sh
npm run test:browser -- --project=desktop-chromium --grep='review waveform|synchronizes all tracks'
```

Expected: the synchronization test still passes, while the three new tests fail because the waveform has no pointer gesture listeners and dragging does not change `scrollLeft`.

### Task 2: Implement click-to-seek and drag-to-pan

**Files:**
- Modify: `web/review-page.js:1-430`
- Modify: `web/review.html:8-56`
- Test: `web/test/app.spec.js`

- [ ] **Step 1: Add the pointer gesture state and helpers**

In `web/review-page.js`, add the threshold and state near the existing page state:

```js
const WAVEFORM_DRAG_THRESHOLD_PX = 5;
const waveformGesture = {
  pointerId: null,
  startClientX: 0,
  startScrollLeft: 0,
  dragged: false,
};
```

Add focused helpers before `configureBundle()`:

```js
function waveformTrack(){
  return waveform.querySelector('.timeline-track');
}

function clearWaveformGesture(pointerId,{release=true}={}){
  if (waveformGesture.pointerId!==pointerId) return;
  if (release && waveform.hasPointerCapture(pointerId)) waveform.releasePointerCapture(pointerId);
  waveformGesture.pointerId=null;
  waveformGesture.dragged=false;
  waveform.dataset.panning='false';
}

function seekWaveformAt(clientX){
  const rect=waveformTrack().getBoundingClientRect();
  if (!rect.width) return;
  const fraction=Math.max(0,Math.min(1,(clientX-rect.left)/rect.width));
  setTime(fraction*state.bundle.duration_ms);
}

function waveformPointerDown(event){
  if (!event.isPrimary || event.button!==0 || waveformGesture.pointerId!==null) return;
  if (event.target.closest('.label-overlay,.event-overlay')) return;
  waveformGesture.pointerId=event.pointerId;
  waveformGesture.startClientX=event.clientX;
  waveformGesture.startScrollLeft=waveform.scrollLeft;
  waveformGesture.dragged=false;
  waveform.setPointerCapture(event.pointerId);
}

function waveformPointerMove(event){
  if (waveformGesture.pointerId!==event.pointerId) return;
  const delta=event.clientX-waveformGesture.startClientX;
  if (!waveformGesture.dragged && Math.abs(delta)>WAVEFORM_DRAG_THRESHOLD_PX){
    waveformGesture.dragged=true;
    waveform.dataset.panning='true';
  }
  if (!waveformGesture.dragged) return;
  waveform.scrollLeft=waveformGesture.startScrollLeft-delta;
  event.preventDefault();
}

function waveformPointerUp(event){
  if (waveformGesture.pointerId!==event.pointerId) return;
  if (!waveformGesture.dragged) seekWaveformAt(event.clientX);
  clearWaveformGesture(event.pointerId);
}
```

Register the handlers with the existing controls:

```js
waveform.addEventListener('pointerdown',waveformPointerDown);
waveform.addEventListener('pointermove',waveformPointerMove);
waveform.addEventListener('pointerup',waveformPointerUp);
waveform.addEventListener('pointercancel',event=>clearWaveformGesture(event.pointerId));
waveform.addEventListener('lostpointercapture',event=>clearWaveformGesture(event.pointerId,{release:false}));
```

- [ ] **Step 2: Add interaction styling and concise help text**

In `web/review.html`, change the viewport style to:

```css
.timeline-viewport{overflow-x:auto;overflow-y:hidden;border:1px solid #46314f;border-radius:5px;background:#080612;cursor:grab;touch-action:pan-y}
.timeline-viewport[data-panning="true"]{cursor:grabbing;user-select:none}
```

Change the help copy to:

```html
<p class="review-help">Click the waveform to seek. Drag a zoomed waveform to pan. Select a human label, then use Replay label to hear the surrounding half-second.</p>
```

- [ ] **Step 3: Run focused browser tests and verify they pass**

Run:

```sh
npm run test:browser -- --project=desktop-chromium --grep='review waveform|synchronizes all tracks|playback advances'
```

Expected: all selected tests pass.

- [ ] **Step 4: Run the interaction tests on all configured browsers**

Run:

```sh
npm run test:browser -- --grep='review waveform|synchronizes all tracks|playback advances'
```

Expected: the selected tests pass on desktop Chromium, mobile Chromium, and mobile WebKit.

- [ ] **Step 5: Commit the tracked implementation**

```sh
git add web/review-page.js web/review.html web/test/app.spec.js
git commit -m "feat: seek and pan sound review waveform"
```

### Task 3: Save the current human label and refresh the reviewer

**Files:**
- Modify ignored: `.artifacts/samples/review/high-yell-01.labels.json`
- Regenerate ignored: `.artifacts/sound-review/*`

- [ ] **Step 1: Save only the authoritative drone label**

Set the ignored label document to:

```json
{
  "audio_file": "high-yell-01.wav",
  "sample_rate_hz": 16000,
  "labels": [
    {"type": "drone", "start_ms": 1020, "end_ms": 6950}
  ]
}
```

Do not add a yell or transient label. The user has not yet identified a reliable yell interval and explicitly found the transient markers unhelpful.

- [ ] **Step 2: Run the full repository checks**

Run:

```sh
make check
npm test
npm run test:browser
```

Expected: all Python, Node, and Playwright suites pass.

- [ ] **Step 3: Regenerate the local review artifact**

Run:

```sh
make sound-review REVIEW_AUDIO=.artifacts/samples/review/high-yell-01.wav REVIEW_LABELS=.artifacts/samples/review/high-yell-01.labels.json
```

Expected: the command reports fresh feature, event, effect, run, and review JSON paths under `.artifacts/sound-review/`.

- [ ] **Step 4: Verify the local review page**

Open `http://127.0.0.1:8765/.artifacts/sound-review/review.html`, confirm the page reports `Review loaded.`, confirm the drone label displays `1.02–6.95 s`, and exercise click-to-seek and zoomed drag-to-pan without adding a yell label.

- [ ] **Step 5: Confirm repository state**

Run:

```sh
git status --short --branch
git log -2 --oneline
```

Expected: the tracked worktree is clean, the implementation commit is at `HEAD`, and the ignored recording, labels, and generated review artifacts remain outside Git.
