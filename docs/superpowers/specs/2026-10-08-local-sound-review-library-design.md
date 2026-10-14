# Local Sound Review Library Design

Date: 2026-10-08
Status: Approved

## Goal

Make both approved sound-review recordings available from the local Sound
Analysis page, including working audio playback, without copying recordings
into the public web build or weakening production authentication.

## Local catalog mode

The review page will accept a `catalog` query parameter only on `localhost` and
`127.0.0.1`. The parameter points to the generated catalog produced by
`make review-library`, for example:

```text
/review.html?catalog=/firebase/functions/review-data/catalog.json
```

The browser loads the catalog, preserves its declared recording order, and
populates the existing Recording selector. Selecting a recording loads
`<recording-id>/bundle.json` and uses the adjacent
`<recording-id>/audio.wav` as that bundle's audio source. URLs are resolved
relative to the catalog response URL so the page works when the repository root
is served by a basic static server.

The existing loopback-only `data` query parameter remains available for loading
a single review bundle directly. If both `catalog` and `data` are present,
`catalog` takes precedence because it represents the complete local library.

## Security and build boundaries

Catalog mode is rejected on non-loopback hosts. Production continues to use the
authenticated Firebase callable path and does not fetch static review data.
The WAV files and generated review bundles remain outside `web/` and
`web/dist`; no recording is added to Firebase Hosting or another public asset
directory.

The local catalog reuses `firebase/functions/review-data/`, which is ignored,
generated, and already contains the same analyzed bundles used by the protected
callables. `make review-library` remains the only required data-generation step.

## Page behavior

Local catalog mode reveals the protected review controls, shows both approved
recordings in the existing selector, loads the first recording initially, and
uses the same view reset behavior as online recording changes. The selected
recording summary, waveform, labels, events, features, comparisons, effect
selector, 4x8 virtual consumer, and audio player all update from the selected
bundle.

Loading failures keep the controls visible and report a useful local catalog or
recording error. A failed recording can be retried or replaced by selecting the
other recording. Object URLs are unnecessary because local audio is referenced
by an ordinary static URL.

## File boundaries

- `web/review-mode.mjs` validates and returns loopback-only local catalog URLs.
- A small local review loader owns catalog fetches, recording selection, and
  bundle/audio URL resolution.
- `web/review-page.js` chooses catalog mode, single-bundle mode, or authenticated
  online mode without changing the shared renderer contract.
- `tools/build_web.mjs` copies the local loader beside the review page.
- Browser and unit tests cover loopback restrictions, two-recording discovery,
  switching, playback URLs, failures, and production isolation.
- `README.md` documents the generation, server, and local catalog URL.

## Acceptance

After `make review-library` and serving the repository root, the local Sound
Analysis page lists both `Generated drone/yell fixture` and `High yell 01`.
Either selection loads its derived analysis and a playable WAV, while the
virtual consumer remains synchronized. Non-loopback pages ignore local catalog
parameters and continue through authenticated online loading.
