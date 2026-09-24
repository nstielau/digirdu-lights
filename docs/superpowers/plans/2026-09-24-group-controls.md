# Group controls and full-screen sleep

**Goal:** D1 on any TFT requests one shared effect change; D2 hold requests group
sleep, with full-screen hold/countdown, sending, fade and release-to-sleep UI.

**Architecture:** Consumers send bounded retryable control requests addressed to
the configured producer MAC/boot session and group. Producer validates freshness,
limits its request history and deduplicates per sender boot/sequence, then changes
the authoritative effect or starts existing DGRS sleep broadcasts. Acknowledgments
stop retries; failures are visible. Existing v3 audio and DGRS bytes stay unchanged.
Old consumers can follow new producer changes; initiating TFT and producer need
updated apps. No router/cloud dependency. No automatic role/source changes.

Full-screen overlay preempts Audio/Status and uses large digits with a red
background. Early release cancels the hold locally. Confirmed fade cannot be
cancelled. Consumer requests wait for producer sleep broadcast before local sleep.
The old FeatherS2's buttons retain their existing effect/hold functions.
All means reachable awake nodes following that producer; radio cannot guarantee
all nodes receive packets or wake sleeping devices. No authentication claim.

- [x] Pure control protocol tests: wrong sender/group/session, replay, bounded
  capacity, duplicate retry, expiry, wrap, timeout and failed/old producer.
- [x] Transport tests: single outstanding native send, bounded receive drain,
  producer applies once and sends ACK without starving audio/sleep broadcasts.
- [x] Button tests: both roles D1 next and D2 hold group request; OTA trial sleep
  rejection applies to local and remote controls.
- [x] Dashboard tests: full screen with countdown/fade, early release restoration,
  page-independent takeover; sleep changes preempt one-second status cadence.
- [x] Implement and run make check, native renderer test, verified USB deployment.
- [ ] Update docs with protocol/controls and validate producer+consumer together
  when the producer is available for installing this app.

## Brightness extension requested during implementation

D0 cycles Audio/Status/Brightness. Brightness has percentage, bar and +/-
labels. D1/D2 short releases request plus/minus5 percentage points, clamped
0–50% (user-approved maximum); startup remains15%. D2 hold still sleeps.
Consumers send deduplicated BRIGHTER/DIMMER requests; producer broadcasts DGRB
current+maximum every0.5s, including after restart and for new consumers.
State requires the configured producer/session/recent audio and monotonic
sequence. Cache updates cover Spectrum and effect-number overlays, while
Battery retains its separate3% cap. Existing v3 audio is unchanged; brightness
replication requires all receiving nodes to be updated. Producer reset restores
configured brightness; no per-press flash writes. TFT backlight stays12%.

- [x] Test/render/replication/button routing and capped caches, including ACK load.
- [x] Install combined app on connected TFT; native preview and startup checks.
- [ ] Upgrade producer and other consumers when physically available; verify
  effect, sleep and brightness across real nodes.
