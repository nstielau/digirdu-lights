# Local Sound Review Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the loopback Sound Analysis page list and play both generated review-library recordings while preserving authenticated production behavior.

**Architecture:** Add a loopback-only `catalog` query helper and a focused local loader that reads the existing generated review catalog, derives each recording's bundle and WAV URLs, and drives the shared review renderer. Keep single-bundle `data` mode and the authenticated online loader intact, and never copy recordings into the public web build.

**Tech Stack:** Browser ES modules, Fetch API, Node test runner, Playwright, Python static server

---

### Task 1: Recognize loopback-only catalog mode

**Files:**
- Modify: `web/test/review-mode.test.mjs`
- Modify: `web/review-mode.mjs`

- [x] **Step 1: Write the failing URL-mode tests**

Import `localReviewCatalogUrl` and assert that it returns the `catalog` query
value on `localhost` and `127.0.0.1`, rejects it on production, and remains
independent of the existing `data` query helper.

- [x] **Step 2: Run the focused test and verify RED**

Run: `npm test -- --test-name-pattern='local review catalog'`

Expected: FAIL because `localReviewCatalogUrl` is not exported.

- [x] **Step 3: Implement the catalog URL helper**

Add a helper mirroring the existing loopback hostname restriction:

```javascript
export function localReviewCatalogUrl(location) {
  if (!['localhost', '127.0.0.1'].includes(location.hostname)) return null;
  return new URLSearchParams(location.search).get('catalog');
}
```

- [x] **Step 4: Run the focused test and verify GREEN**

Run: `npm test -- --test-name-pattern='local review catalog'`

Expected: PASS.

### Task 2: Load and switch local recordings

**Files:**
- Create: `web/review-local.js`
- Modify: `web/review-page.js`
- Modify: `tools/build_web.mjs`
- Modify: `web/test/app.spec.js`

- [x] **Step 1: Write a failing browser test for the complete local library**

Route a two-entry catalog plus each recording's `bundle.json` and `audio.wav`,
then open:

```text
/review.html?catalog=/local-review-data/catalog.json&data=/ignored.json
```

Assert that the Recording selector contains both declared names, the first
recording loads initially, its audio element resolves to its adjacent WAV,
switching to the second recording resets the playhead and loads the second
bundle/audio URL, and the ignored `data` URL is never requested.

- [x] **Step 2: Write a failing browser test for local errors**

Return HTTP 503 for the catalog and assert that the protected controls remain
visible and the status reports that the local recording catalog could not load.

- [x] **Step 3: Run the focused browser tests and verify RED**

Run: `npm run test:browser -- --grep='local review library' --project=desktop-chromium`

Expected: FAIL because the page still enters single-bundle mode and no local
catalog loader exists.

- [x] **Step 4: Implement the focused local loader**

Create `initLocalReview(renderer, catalogUrl)` in `web/review-local.js`. It must:

- fetch the catalog with `cache: 'no-store'`;
- require schema version 1 and at least one recording;
- accept only lowercase URL-safe recording IDs and non-empty names;
- populate `#review-recording` in catalog order;
- resolve `<id>/bundle.json` and `<id>/audio.wav` relative to the catalog
  response URL;
- clear and reconfigure the shared renderer when a recording changes;
- keep the controls visible and expose catalog/recording failures in status;
- retry the selected recording through the existing Retry button.

- [x] **Step 5: Choose local catalog mode before single-bundle mode**

In `web/review-page.js`, import `localReviewCatalogUrl`, inspect it before
`localReviewDataUrl`, reveal `#review-protected`, and dynamically import
`./review-local.js`. Preserve authenticated online mode when neither local
parameter is valid.

- [x] **Step 6: Package the loader in static builds**

Update `tools/build_web.mjs` to copy `web/review-local.js` beside
`review-page.js`, allowing the dynamic import to resolve in browser tests and
the production web build without including any catalog or audio data.

- [x] **Step 7: Run the focused browser tests and verify GREEN**

Run: `npm run test:browser -- --grep='local review library' --project=desktop-chromium`

Expected: PASS.

### Task 3: Package, document, and verify local use

**Files:**
- Modify: `README.md`
- Test: `web/test/app.spec.js`

- [x] **Step 1: Document the workflow**

Update the Human-reviewed sound library README section with:

```sh
make review-library
python3 -m http.server 8765
```

and the URL:

```text
http://127.0.0.1:8765/web/review.html?catalog=/firebase/functions/review-data/catalog.json
```

State that the catalog mode is loopback-only and the generated WAVs are not
part of the public web build.

- [x] **Step 2: Run focused and broad verification**

Run:

```sh
npm test
npm run test:browser -- --grep='local review library|virtual consumer|hosted review'
npm run build
make check
git diff --check
```

Expected: all commands pass.

- [x] **Step 3: Regenerate the library and serve the verified page**

Run:

```sh
make review-library
python3 -m http.server 8765
```

Open the documented local URL and verify both recordings appear, switching
recordings changes the audio URL, and the 4x8 virtual consumer remains populated.

Do not create a Git commit unless the user explicitly requests one.
