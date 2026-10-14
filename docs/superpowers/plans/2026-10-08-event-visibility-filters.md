# Event Visibility Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-type detector-event visibility controls to the sound reviewer, with transients hidden by default and yell and combined drone boundaries visible.

**Architecture:** Keep filter state entirely in `web/review-page.js`, derived fresh from each loaded bundle. A display-group mapper will connect raw detector event types to checkbox groups, and both detector render paths will consult the same enabled-group set; human labels and comparison rendering stay independent.

**Tech Stack:** Browser-native HTML/CSS/JavaScript, Playwright browser tests, Node test runner.

---

### Task 1: Known event-group controls and filtering

**Files:**
- Modify: `web/test/app.spec.js`
- Modify: `web/review.html`
- Modify: `web/review-page.js`

- [ ] **Step 1: Write the failing browser test**

Add a Playwright test with a review bundle containing a transient, yell,
drone-start, and drone-stop event, plus a human drone label and comparison
text. Assert that the three controls expose their combined counts, Transient
starts unchecked, Yell and Drone boundaries start checked, only the three
enabled event rows/markers render, and the human marker and comparison remain.
Toggle Transient on and Drone boundaries off; assert the rows and markers now
contain transient and yell only, while the comparison text is unchanged.

```js
test('review event visibility filters known detector groups without changing evaluation',async({page})=>{
 await page.route('**/filter-review.json',route=>route.request().resourceType()==='document'?route.continue():route.fulfill({json:{
  duration_ms:1000,waveform:[0,.5],
  labels:[{type:'drone',start_ms:100,end_ms:900}],
  events:[
   {type:'transient',time_ms:100},{type:'yell',time_ms:300},
   {type:'drone_start',time_ms:200},{type:'drone_stop',time_ms:800}
  ],
  features:[],comparison:{drone:{intersection_over_union:.7,false_active_ms:100,false_inactive_ms:200}},
  effects:{frames:{}}
 }}));
 await page.goto('/review.html?data=/filter-review.json');
 const transient=page.getByRole('checkbox',{name:'Transient (1)'});
 const yell=page.getByRole('checkbox',{name:'Yell (1)'});
 const drone=page.getByRole('checkbox',{name:'Drone boundaries (2)'});
 await expect(transient).not.toBeChecked();
 await expect(yell).toBeChecked();
 await expect(drone).toBeChecked();
 await expect(page.locator('#review-events li')).toHaveCount(3);
 await expect(page.locator('.event-overlay')).toHaveCount(3);
 await expect(page.locator('.label-overlay')).toHaveCount(1);
 const comparison=page.locator('#review-comparison');
 const comparisonText=await comparison.textContent();
 await transient.check();
 await drone.uncheck();
 await expect(page.locator('#review-events')).toContainText('transient');
 await expect(page.locator('#review-events')).toContainText('yell');
 await expect(page.locator('#review-events')).not.toContainText('drone_start');
 await expect(page.locator('.event-overlay')).toHaveCount(2);
 await expect(page.locator('.label-overlay')).toHaveCount(1);
 await expect(comparison).toHaveText(comparisonText);
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
npm run test:browser -- --project=desktop-chromium --grep "review event visibility filters known"
```

Expected: FAIL because the event-group checkboxes do not exist.

- [ ] **Step 3: Add the accessible filter container and styles**

In the Detected events panel in `web/review.html`, add:

```html
<fieldset id="review-event-filters" class="review-event-filters">
  <legend>Show detector events</legend>
</fieldset>
```

Add compact flex-wrap styles for `.review-event-filters` and its labels, using
native checkbox inputs with the existing pink accent color.

- [ ] **Step 4: Implement known display groups and shared filtering**

In `web/review-page.js`, add `eventFilters` to the DOM references and
`enabledEventGroups: new Set()` to state. Define known groups in display order:

```js
const KNOWN_EVENT_GROUPS = [
  {id:'transient',label:'Transient',types:['transient'],enabled:false},
  {id:'yell',label:'Yell',types:['yell'],enabled:true},
  {id:'drone-boundaries',label:'Drone boundaries',types:['drone_start','drone_stop'],enabled:true},
];
```

Add `eventGroupForType(type)`, `eventIsVisible(event)`, and
`renderEventFilters()`. The renderer derives counts from the current bundle,
omits empty groups, resets the enabled set from group defaults, and creates
native labeled checkboxes. Each `change` handler updates the enabled set and
calls `renderEvents(state.timeMs)` without calling `setTime()`.

Change both loops in `renderEventOverlays()` and `renderEvents()` to skip
events for which `eventIsVisible(event)` is false. If events exist but all are
filtered, render the message `No detected events selected.` in the list.
Call `renderEventFilters()` from `configureBundle()` after the waveform exists
and before `setTime(0)` performs the first event render.

- [ ] **Step 5: Run the focused test and verify GREEN**

Run:

```bash
npm run test:browser -- --project=desktop-chromium --grep "review event visibility filters known"
```

Expected: 1 passed.

- [ ] **Step 6: Commit the known-group behavior**

```bash
git add web/review.html web/review-page.js web/test/app.spec.js
git commit -m "feat: filter known sound review events"
```

### Task 2: Unknown event groups and interaction-state preservation

**Files:**
- Modify: `web/test/app.spec.js`
- Modify: `web/review-page.js`

- [ ] **Step 1: Write the failing browser test**

Add a test whose bundle includes `{type:'raspy_burst', time_ms:600}`. Before
toggling its generated `Raspy burst (1)` checkbox, set the position to 400 ms,
zoom to 4×, and pan the waveform. Assert the unknown group starts checked;
after unchecking it, assert its row and marker disappear while the position,
zoom, scroll offset, human-label marker, and comparison text are unchanged.

```js
test('review event visibility gives unknown types independent controls and preserves view state',async({page,browserName})=>{
 await page.route('**/unknown-filter-review.json',route=>route.request().resourceType()==='document'?route.continue():route.fulfill({json:{
  duration_ms:1000,waveform:[0,.5],labels:[{type:'drone',start_ms:100,end_ms:900}],
  events:[{type:'raspy_burst',time_ms:600}],features:[],
  comparison:{yell:{true_positive:0,false_positive:0,false_negative:1,precision:0,recall:0,f1:0}},
  effects:{frames:{}}
 }}));
 await page.goto('/review.html?data=/unknown-filter-review.json');
 const position=page.getByRole('slider',{name:'Position'});
 await position.fill('400');await position.dispatchEvent('input');
 const zoom=page.getByRole('slider',{name:'Zoom'});
 await zoom.fill('4');await zoom.dispatchEvent('input');
 const waveform=page.locator('#review-waveform');
 const box=await waveform.boundingBox();
 await dragReviewWaveform(page,waveform,box,.75,.25,browserName);
 const scrollLeft=await waveform.evaluate(node=>node.scrollLeft);
 const comparisonText=await page.locator('#review-comparison').textContent();
 const unknown=page.getByRole('checkbox',{name:'Raspy burst (1)'});
 await expect(unknown).toBeChecked();
 await unknown.uncheck();
 await expect(page.locator('#review-events')).toContainText('No detected events selected.');
 await expect(page.locator('.event-overlay')).toHaveCount(0);
 await expect(position).toHaveValue('400');
 await expect(waveform).toHaveAttribute('data-zoom','4');
 expect(await waveform.evaluate(node=>node.scrollLeft)).toBe(scrollLeft);
 await expect(page.locator('.label-overlay')).toHaveCount(1);
 await expect(page.locator('#review-comparison')).toHaveText(comparisonText);
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
npm run test:browser -- --project=desktop-chromium --grep "unknown types independent"
```

Expected: FAIL because no independent unknown-type checkbox exists.

- [ ] **Step 3: Implement checked-by-default unknown groups**

Extend `eventGroupForType(type)` so an unmatched raw type produces a stable
group `{id: `unknown:${type}`, label: readableEventType(type), types:[type],
enabled:true}`. Implement `readableEventType()` by replacing underscores with
spaces and capitalizing the first character. Derive unknown groups in first
event-occurrence order after known groups and reuse the same count, rendering,
and enabled-set paths from Task 1.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
npm run test:browser -- --project=desktop-chromium --grep "unknown types independent"
```

Expected: 1 passed.

- [ ] **Step 5: Run all review-page browser tests**

Run:

```bash
npm run test:browser -- --project=desktop-chromium --grep "review"
```

Expected: all review tests pass.

- [ ] **Step 6: Commit unknown-group support**

```bash
git add web/review-page.js web/test/app.spec.js
git commit -m "test: cover extensible review event filters"
```

### Task 3: Full regression verification

**Files:**
- Verify only

- [ ] **Step 1: Run the host suite**

Run: `make check`

Expected: all Python and Node tests pass.

- [ ] **Step 2: Run the complete browser matrix**

Run: `npm run test:browser`

Expected: all tests pass on desktop Chromium, mobile Chromium, and mobile
WebKit.

- [ ] **Step 3: Inspect the final diff and status**

Run:

```bash
git diff HEAD~2 --check
git status --short
```

Expected: no whitespace errors and no uncommitted tracked changes. Ignored
recordings and generated review artifacts remain uncommitted.
