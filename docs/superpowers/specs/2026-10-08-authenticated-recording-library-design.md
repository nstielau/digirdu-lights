# Authenticated Recording Library Design

## Context

The sound-review page currently loads one generated review bundle through a
`?data=...` query parameter and is intended for local use. One generated
drone/yell fixture is already committed, while the new `high-yell-01.wav` take
and its human labels remain in ignored local artifacts. The user has explicitly
authorized committing both recordings and publishing them for online review.

The hosted review library must reuse the Firebase site's existing Google login,
App Check, and fleet administrator allowlist. Hiding publicly hosted files
behind client-side UI is insufficient: review bundles and audio bytes must also
cross an authenticated server boundary.

## Recording library

A tracked recording-library directory will contain the canonical source WAV,
authoritative human-label JSON, and catalog metadata for each take. Initially
the catalog contains:

- the generated drone/yell fixture; and
- `high-yell-01`, including the reviewed drone interval from 1020–6950 ms and
  yell interval from 2950–3050 ms.

Catalog entries have a stable, URL-safe ID, a human-readable display name, the
source WAV and label filenames, and explicit display order. The build rejects
duplicate or unsafe IDs, missing files, invalid WAVs, labels that name another
audio file, and labels outside the recording duration.

Generated features, detector events, comparisons, virtual LED frames, waveform
preview, and run metadata remain derived data. A deterministic review-library
build generates one deployment bundle per catalog entry and a runtime catalog.
Generated deployment files are ignored rather than treated as authoritative
source. The build verifies that every generated bundle refers only to its
catalog entry and removes stale generated entries before writing replacements.

The existing test fixture will move into the canonical recording library so
the WAV is not duplicated in Git. Python tests and Make defaults will use its
new path. The README will document the approved recording exception, both
human label sets, and the add/build/deploy workflow.

## Authenticated service boundary

Two new Firebase callable functions will serve the library:

- `reviewCatalog` returns only the ordered recording IDs, display names,
  durations, and label/event summary counts needed by the selector.
- `reviewRecording` accepts one recording ID and returns that recording's
  generated review bundle plus its WAV encoded for transport.

Both callables use the same browser function settings as fleet administration:
Google authentication, verified email, App Check, allowed production origins,
and the existing `admins/<email-hash>` enabled record. A signed-in Google user
who is not on the administrator allowlist receives permission denied.

Recording lookup uses the generated catalog rather than constructing a path
directly from request input. Unknown, malformed, or unlisted IDs return a
not-found or invalid-argument error without filesystem traversal. The server
sets no public download URL and returns only the requested recording. With the
current ten-second PCM WAVs and review bundles, each response remains well
within the callable response limit. This deliberately favors a small,
repository-backed review corpus; a later large corpus can migrate audio bytes
to authenticated object storage without changing the page-level selector.

Function unit and emulator tests will verify unauthenticated, missing-App-Check,
non-admin, malformed-ID, unknown-ID, and authorized success cases. Existing
fleet authorization behavior must remain unchanged.

## Hosted review experience

`review.html` will gain the same site header, navigation, account dropdown, and
sign-in behavior as the fleet and Effects pages. Review content stays hidden
until an authorized catalog request succeeds. The navigation on the other
hosted pages will link to Review.

After authorization, a native `Recording` select control lists the catalog in
its declared order. A dropdown is preferred to tabs because the library is
expected to grow. The selected recording's display name and duration remain
visible near the control.

Selecting another recording will:

1. pause the current audio and revoke its temporary browser object URL;
2. show a loading state and disable playback controls;
3. request only the selected recording through the authenticated callable;
4. decode the returned WAV into a temporary object URL;
5. configure the existing synchronized reviewer with the returned bundle; and
6. reset playback time, selected label, zoom, pan, replay bounds, and event
   filters to the new recording's defaults.

The existing event controls retain their behavior: Transient starts hidden,
Yell and Drone boundaries start visible, and unknown event types start visible.
Human labels and detector-comparison metrics are never altered by presentation
filters.

If a selection request fails, the old recording does not resume. The page
revokes any temporary audio URL, leaves playback disabled, reports the error,
and allows another selection or retry. Rapid changes use a monotonically
increasing request generation so a slow earlier response cannot replace a
newer selection. Signing out immediately stops playback, revokes audio, clears
the catalog and review DOM, and hides the protected content.

The page is a review surface, not an editor. Human label changes continue to be
made in the tracked JSON and require rebuilding and deploying the library.
The waveform remains the current normalized peak-amplitude preview: one bar per
1024-sample hop, approximately 64 ms at 16 kHz. A frequency-over-time
spectrogram is not part of this change.

## Local review mode

The explicit `?data=...` bundle workflow remains available when the page is
served from `localhost` or `127.0.0.1`. This preserves generated local review,
Playwright fixtures, and offline development without Firebase authentication.
Production hosts ignore the query parameter and always use the authenticated
catalog. A query parameter therefore cannot turn the deployed page into an
unauthenticated bundle loader.

The browser implementation will keep the current review renderer independent
from Firebase. A small online entry module will initialize the shared account
control and callables only in hosted mode. This boundary preserves local review
without requiring bare Firebase imports in the copied local artifact.

## Build and deployment

A dedicated build command will validate the tracked catalog, run the existing
sound-analysis pipeline for every entry, and stage the generated runtime files
inside the Firebase Functions deployment package. The web build will bundle the
online review entry and continue copying the renderer and static page assets.

`make web-test` will exercise catalog/build tests, Functions unit tests,
Firestore emulator authorization tests, and the browser matrix. `make
web-deploy` will build the review library before deploying Functions, Hosting,
and Firestore. A failed validation or analysis stops deployment before any
remote mutation.

The recordings, label files, catalog, application code, tests, README changes,
design, and implementation plan will be committed. Generated staging files and
temporary local review artifacts remain ignored.

## Verification

Automated verification will cover:

- catalog validation and deterministic output for both recordings;
- preserved source hashes and human-label intervals;
- administrator-only catalog and recording responses;
- rejection of unauthenticated, non-admin, malformed, and unknown requests;
- no regression to fleet callable authorization;
- signed-out, unauthorized, loading, failure, and authorized browser states;
- switching between both recordings and rejecting stale responses;
- playback/object-URL cleanup on switch and sign-out;
- reset of playhead, selection, zoom, pan, replay, and event filters;
- localhost-only `?data=...` behavior;
- responsive layout and keyboard-accessible selector/account controls; and
- the full host, Functions, emulator, and three-browser regression suites.

After tests pass, deployment verification will confirm that an allowlisted
administrator can sign in, see both catalog entries, switch between them, play
their distinct audio, and inspect the expected labels. A signed-out request and
a direct unlisted-recording request must not return recording data.
