# NIC-10 RF telemetry implementation plan

Goal: record enough packet evidence to compare producer transmission with each consumer's reception, without flash or Wi-Fi work in the music loop. Upload a bounded record after intentional sleep and retry at boot. Show historical sessions on the authenticated fleet page.

1. Add pure, bounded session recorder in the app. Write tests first for 16-bit wrap, compact packet windows, RSSI, receiver rejects/native drops, producer outcomes, sleep-control exclusion, and overflow. Then connect it to the existing ESP-NOW send/receive paths without changing the receive completion gate or send bound.
2. Add a USB-base queue with atomic writes, stable batch IDs, strict size limits, acknowledged deletion, and boot retry. Write tests first for power interruption, failed upload, duplicate retry, full queue, and malformed files. Add a callback after the app's sleep cleanup that persists the recorder, makes one bounded Wi-Fi attempt, and always proceeds to deep sleep. Keep OTA trial behavior.
3. Add a separately authenticated, validated device telemetry API and historical Firestore storage. Write contract and emulator tests first for exact schema, identity, idempotency, mismatch/revocation, and bounded reads. Keep existing check-in report contract unchanged.
4. Add an authenticated historical telemetry view to the fleet page. Test session comparison, missing vs unobserved packets, freshness, and empty states. Document limits and use in README/operations.
5. Update the app/base file contracts and versions, run `make check` and `make web-test`, inspect diff, and report hardware/deployment work separately. Do not publish firmware or deploy production cloud changes in this code task.
