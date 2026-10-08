# Authenticated Recording Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Commit both reviewed recordings and publish an administrator-only Firebase review page with a recording dropdown.

**Architecture:** Canonical WAVs, labels, and catalog metadata live under `review/recordings/`. A deterministic Python builder stages per-recording bundles and audio inside the ignored Firebase Functions package; authenticated callable handlers return the catalog or one selected recording. The existing renderer stays Firebase-independent, while a small bundled online module owns sign-in, catalog selection, request races, and temporary audio URLs.

**Tech Stack:** Python 3/unittest, existing sound-analysis pipeline, Node 22/CommonJS Firebase Functions, Firebase Auth/App Check, browser JavaScript, esbuild, Playwright.

---

### Task 1: Canonical recording catalog and deterministic staging build

**Files:**
- Create: `review/recordings/catalog.json`
- Move: `tests/fixtures/audio/drone-yell-10s.wav` to `review/recordings/drone-yell-10s.wav`
- Move: `tests/fixtures/audio/drone-yell-10s.labels.json` to `review/recordings/drone-yell-10s.labels.json`
- Move: `.artifacts/samples/review/high-yell-01.wav` to `review/recordings/high-yell-01.wav`
- Move: `.artifacts/samples/review/high-yell-01.labels.json` to `review/recordings/high-yell-01.labels.json`
- Create: `tools/review_library.py`
- Create: `tests/test_review_library.py`
- Modify: `tests/test_sound_review.py`
- Modify: `.gitignore`
- Modify: `Makefile`

- [ ] **Step 1: Write failing catalog/build tests**

Create `tests/test_review_library.py` with tests that import
`build_review_library`, `load_recording_catalog`, and `validate_recording_id`.
Use temporary one-second WAV/label pairs to assert:

```python
self.assertEqual(validate_recording_id("high-yell-01"), "high-yell-01")
for invalid in ("", "../take", "Take One", "a/b"):
    with self.assertRaises(ValueError):
        validate_recording_id(invalid)
```

Build two entries and assert the staged `catalog.json` preserves declared
order, contains duration and label/event counts, and each entry contains only
`audio.wav` and `bundle.json`. Build again after removing an entry and assert
the old staged directory is gone. Add focused failures for duplicate IDs,
missing sources, mismatched `audio_file`, and labels beyond duration.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_review_library -v
```

Expected: import failure because `tools.review_library` does not exist.

- [ ] **Step 3: Implement the catalog builder**

Create `tools/review_library.py` with these public boundaries:

```python
RECORDING_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

def validate_recording_id(value): ...
def load_recording_catalog(catalog_path): ...
def build_review_library(catalog_path, output_dir): ...
def main(argv=None): ...
```

The tracked catalog schema is:

```json
{
  "schema_version": 1,
  "recordings": [
    {
      "id": "drone-yell-10s",
      "name": "Generated drone/yell fixture",
      "audio": "drone-yell-10s.wav",
      "labels": "drone-yell-10s.labels.json"
    },
    {
      "id": "high-yell-01",
      "name": "High yell 01",
      "audio": "high-yell-01.wav",
      "labels": "high-yell-01.labels.json"
    }
  ]
}
```

Resolve filenames strictly beneath the catalog directory. Validate WAV and
labels before analysis. Build into a sibling temporary directory, call the
existing `build_artifacts()` for each entry, write its normalized `review.json`
as `<id>/bundle.json` with `audio_url` removed, copy the WAV as
`<id>/audio.wav`, and write the runtime summary catalog. Replace the exact
staging directory only after every entry succeeds.

- [ ] **Step 4: Move and register the authorized recordings**

Move the existing fixture and the explicitly authorized local take into
`review/recordings/`, add the catalog above, and update the fixture paths in
`tests/test_sound_review.py`. Preserve the known SHA-256 assertion for the
original fixture and add assertions for `high-yell-01`'s 1020–6950 ms drone and
2950–3050 ms yell labels.

- [ ] **Step 5: Add build integration and ignore only staging output**

Add `/firebase/functions/review-data/` to `.gitignore`, update the Make defaults
to the canonical fixture paths, add `review-library` to `.PHONY`, and implement:

```make
review-library: $(VENV)/.dev-ready
	$(PY) tools/review_library.py --catalog review/recordings/catalog.json --output-dir firebase/functions/review-data
```

Add `tools/review_library.py` to the `py_compile` list.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.test_review_library tests.test_sound_review -v
make review-library
```

Expected: all tests pass and staging contains two ordered recordings without
tracked generated files.

- [ ] **Step 7: Commit the recording library**

```bash
git add .gitignore Makefile review/recordings tools/review_library.py tests/test_review_library.py tests/test_sound_review.py
git commit -m "feat: add reviewed recording library"
```

### Task 2: Administrator-only recording service

**Files:**
- Create: `firebase/functions/reviews.cjs`
- Create: `firebase/functions/test/reviews.test.cjs`
- Modify: `firebase/functions/service.cjs`
- Modify: `firebase/functions/index.js`
- Modify: `firebase/functions/test-emulator/service.test.cjs`

- [ ] **Step 1: Write failing runtime-library and handler tests**

In `firebase/functions/test/reviews.test.cjs`, create a temporary staged catalog
with one bundle/audio pair and assert:

```js
const library=createReviewLibrary(root);
assert.deepEqual(library.catalog().recordings.map(item=>item.id),['take-one']);
assert.equal(library.recording('take-one').bundle.duration_ms,1000);
assert.equal(Buffer.from(library.recording('take-one').audio_base64,'base64').toString(),'audio');
for(const id of ['../take','missing'])assert.throws(()=>library.recording(id));
```

Test `createReviewHandlers(authorize, library)` to prove authorization runs
before catalog/recording data is returned and that a rejected authorization is
not swallowed.

- [ ] **Step 2: Run Functions tests and verify RED**

Run:

```bash
npm --prefix firebase/functions test
```

Expected: module-not-found for `reviews.cjs`.

- [ ] **Step 3: Implement the library and authenticated handlers**

`createReviewLibrary(root)` loads and validates the generated catalog once,
keeps an ID map, reads only fixed `<id>/bundle.json` and `<id>/audio.wav`
locations, and returns Base64 audio with `audio_mime_type: "audio/wav"`.

`createReviewHandlers(authorize, library)` returns:

```js
{
  catalog: async request => { await authorize(request); return library.catalog(); },
  recording: async request => {
    await authorize(request);
    return library.recording(request.data?.id);
  }
}
```

Errors carry HTTP-style `status` values for the existing callable wrapper.

- [ ] **Step 4: Expose the existing admin authorization boundary**

Return `authorizeAdmin: admin` from `createService()` without weakening its
verified-Google-user, App Check, or Firestore allowlist checks. Add an emulator
assertion that the allowlisted request succeeds and unauthenticated,
missing-App-Check, and non-admin requests fail through `authorizeAdmin()`.

- [ ] **Step 5: Register callable functions**

In `firebase/functions/index.js`, create the review library from
`path.join(__dirname, 'review-data')`, create handlers using
`service.authorizeAdmin`, and export `reviewCatalog` and `reviewRecording` with
the existing `browser` options and `callable()` error mapping.

- [ ] **Step 6: Verify service tests GREEN**

Run:

```bash
npm --prefix firebase/functions test
make web-test-emulator
```

Expected: unit and local Firestore authorization tests pass.

- [ ] **Step 7: Commit the protected service**

```bash
git add firebase/functions/index.js firebase/functions/service.cjs firebase/functions/reviews.cjs firebase/functions/test/reviews.test.cjs firebase/functions/test-emulator/service.test.cjs
git commit -m "feat: serve reviews to authorized admins"
```

### Task 3: Hosted recording selector and lifecycle

**Files:**
- Create: `web/review-online.js`
- Create: `web/review-mode.mjs`
- Create: `web/test/review-mode.test.mjs`
- Modify: `web/gateway.js`
- Modify: `web/test/gateway.js`
- Modify: `web/review-page.js`
- Modify: `web/review.html`
- Modify: `web/index.html`
- Modify: `web/effects.html`
- Modify: `tools/build_web.mjs`
- Modify: `web/test/app.spec.js`

- [ ] **Step 1: Write failing hosted-review browser tests**

Extend the test gateway with `reviewCatalog()` and `reviewRecording({id})`
routes. Add a Playwright test that opens `/review.html` without `?data`, signs
in, receives a two-entry catalog, and verifies a native Recording combobox.
Return distinct bundle/audio payloads for both IDs, select the second, and
assert its labels render and that playhead, zoom, pan, selected label, and event
filters reset.

Add focused tests for:

- signed-out review content hidden;
- catalog permission failure showing administrator access required;
- sign-out stopping audio and clearing protected DOM;
- rapid selection where the late first response cannot replace the second;
- failed selection disabling playback and leaving a retryable selector; and
- a pure mode-selection test proving production hosts ignore `?data=` while
  localhost and `127.0.0.1` accept it.

- [ ] **Step 2: Run the hosted-review tests and verify RED**

Run:

```bash
npm run test:browser -- --project=desktop-chromium --grep "hosted review"
```

Expected: failure because the Review login/catalog UI and online module do not
exist.

- [ ] **Step 3: Add callable gateway exports and online module**

In `web/gateway.js` export:

```js
export const reviewCatalog=httpsCallable(fn,'reviewCatalog');
export const reviewRecording=httpsCallable(fn,'reviewRecording');
```

Mirror them in `web/test/gateway.js` through `/test-api/review-catalog` and
`/test-api/review-recording`.

Create `web/review-online.js` using `initAccount()`. It increments a request
generation on every auth/selection change, fetches the catalog only for a user,
creates a WAV Blob URL from Base64 for one selected recording, revokes the
previous URL, and calls renderer callbacks supplied by `review-page.js`.

- [ ] **Step 4: Make the renderer support explicit local and hosted modes**

Create `web/review-mode.mjs` with a pure `localReviewDataUrl(location)` helper
that returns the `data` query value only for `localhost` or `127.0.0.1`; test it
through the Node suite for both local names and a production hostname.

Export `configureBundle`, `clearReview`, `setStatus`, and `stopPlayback` from
`web/review-page.js`. `configureBundle()` resets time, zoom input/value, pan,
selected label, replay bounds, and event-filter defaults. `clearReview()` stops
audio, clears protected rendered content, and disables playback controls.

At startup, honor `?data=` only when hostname is `localhost` or `127.0.0.1`.
Otherwise dynamically import `./review-online.js` and initialize hosted mode.

- [ ] **Step 5: Add shared account/navigation and selector markup**

Update `review.html` with the shared header/account control, a hidden
`#review-protected` wrapper, and an accessible Recording `<select>` plus
selected-recording metadata. Add Review navigation links to all three pages.
Keep local mode able to reveal the protected wrapper without authentication.

- [ ] **Step 6: Bundle only the hosted entry**

Add `web/review-online.js` to `tools/build_web.mjs` entry points while continuing
to copy `review-page.js` as the Firebase-independent renderer. The existing
test-gateway esbuild substitution supplies callable responses in Playwright.

- [ ] **Step 7: Run browser tests and verify GREEN**

Run:

```bash
npm run test:browser -- --project=desktop-chromium --grep "review"
npm run test:browser
```

Expected: all reviewer tests pass, then the complete three-browser matrix
passes.

- [ ] **Step 8: Commit the hosted reviewer**

```bash
git add web/review-online.js web/review-mode.mjs web/test/review-mode.test.mjs web/gateway.js web/test/gateway.js web/review-page.js web/review.html web/index.html web/effects.html tools/build_web.mjs web/test/app.spec.js
git commit -m "feat: add authenticated recording selector"
```

### Task 4: Documentation and deploy integration

**Files:**
- Modify: `README.md`
- Modify: `Makefile`

- [ ] **Step 1: Write the deployment-contract test**

Extend `tests/test_review_library.py` to inspect `Makefile` and assert
`web-test` and `web-deploy` depend on `review-library`, preventing Functions
deployment without staged review data.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_review_library -v
```

Expected: dependency assertion fails.

- [ ] **Step 3: Integrate review generation into web test/deploy**

Make `web-test` depend on `review-library`; `web-deploy` already depends on
`web-test`, so validation and staging complete before Firebase mutation. Keep
the generated function directory ignored but present during packaging.

- [ ] **Step 4: Update operating documentation**

Replace the single-fixture section with the two-entry authenticated library.
Document canonical paths, exact labels, amplitude-only waveform meaning,
admin-only online access, `make review-library`, local `?data=` review, adding a
new catalog entry, and `make web-deploy`. Explicitly state that committed WAVs
are intentionally published only through the authenticated callable.

- [ ] **Step 5: Run focused tests and commit**

Run:

```bash
.venv/bin/python -m unittest tests.test_review_library -v
git diff --check
```

Then:

```bash
git add Makefile README.md tests/test_review_library.py
git commit -m "docs: document authenticated sound reviews"
```

### Task 5: Full verification and Firebase publication

**Files:**
- Verify generated: `firebase/functions/review-data/`
- Verify deploy output only

- [ ] **Step 1: Run all host and web checks**

Run:

```bash
make check
npm test
npm --prefix firebase/functions test
make web-test
```

Expected: Python, Node, Functions, emulator, and all 3 browser projects pass.

- [ ] **Step 2: Inspect staged assets and repository state**

Verify both runtime catalog entries, bundle label intervals, WAV hashes, and
Base64 response sizes below the callable limit. Run `git diff --check` and
`git status --short --ignored`; only the intended generated staging and local
review outputs are ignored.

- [ ] **Step 3: Deploy the authenticated library and site**

Run:

```bash
make web-deploy
```

Expected: Functions, Hosting, and Firestore deploy successfully to
`digirdu-lights`.

- [ ] **Step 4: Verify production without exposing recordings**

Open `https://digirdu-lights.firebaseapp.com/review.html`. Verify signed-out
content is hidden, sign in with the allowlisted account, confirm both dropdown
entries, switch between them, inspect the expected labels, and play each audio
file. Confirm an unlisted recording ID returns no data.

- [ ] **Step 5: Record final deployment evidence**

Add a short dated README or operations note only if deployment reveals a
material limitation or user-visible operational requirement; otherwise report
the verified deployment URL and test counts without adding redundant prose.
