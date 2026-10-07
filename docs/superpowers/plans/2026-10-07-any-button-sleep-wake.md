# Any-Button Sleep/Wake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with review checkpoints.

**Goal:** Bring the Reverse TFT implementation into this issue branch and make D0, D1, and D2 equivalent for hold-to-sleep and wake while preserving their existing short actions.

**Architecture:** Retain the existing `TFTControls` gesture state machine and role-specific `TFTButtons` action routing. Make `HOLD` a shared action for all three inputs, then construct three CircuitPython `PinAlarm` wake sources using each button’s verified active level. Keep the current red fade, radio packets, OTA trial guard, display idle handling, and output-preservation sequence unchanged.

**Tech Stack:** CircuitPython 10.3.1, Python `unittest`, `alarm.pin.PinAlarm`, existing Reverse TFT dashboard and ESP-NOW control code.

---

## Baseline and file map

The current issue worktree is based on `main`; the complete Reverse TFT implementation is on the local `feature/reverse-tft` branch. The baseline task must combine that branch with the current hardware revision-11 additions without discarding either side. NIC-6 then changes only the following behavior/doc surfaces:

- `effects.py`: shared Reverse TFT button gesture and countdown policy.
- `lights_app.py`: Reverse TFT release gating, wake alarms, and generic hold messages.
- `dashboard.py`: neutral button rail label and generic hold guidance.
- `tests/test_controls.py`, `tests/test_sleep.py`, `tests/test_dashboard.py`: red/green regression coverage.
- `app_version.py`: application version `1.1.1` → `1.1.2`.
- `README.md`, `AGENTS.md`, `TODO.md`: current behavior documentation and completed TODO cleanup.
- `docs/superpowers/specs/2026-10-07-any-button-sleep-wake-design.md`: approved design, retained in the final commit.

Historical design/release records describing the original D2-only behavior remain historical records and are not rewritten as if they described the new release.

Implementation note: the worktree Git admin path prevented `git merge --squash`
from updating `ORIG_HEAD`, so the approved baseline was imported file-wise and
the overlapping guidance files were merged against their common ancestor before
the feature changes were applied.

### Task 1: Combine the approved Reverse TFT baseline

**Files:**
- Modify: the worktree through Git’s squash merge; preserve current hardware revision-11 files.

- [x] **Step 1: Confirm the worktree only contains the approved spec before the baseline merge.**

Run:

```bash
git status --short
git diff --check
```

Expected: only the new design spec is untracked and there are no whitespace errors.

- [x] **Step 2: Import the local Reverse TFT branch into the issue branch without committing.**

Run:

```bash
git merge --squash feature/reverse-tft
```

Expected: the Reverse TFT files are staged in the index, current hardware revision-11 files remain present, and Git does not create a commit. If a merge conflict occurs, stop and resolve only the overlapping source/doc file after inspecting both sides; never discard the hardware assets.

- [x] **Step 3: Verify the combined baseline before feature edits.**

Run:

```bash
test -f hardware.py
test -f dashboard.py
test -f tests/test_controls.py
git diff --check
```

Expected: all three Reverse TFT files exist and the combined index/worktree has no whitespace errors.

### Task 2: Add failing control-state tests

**Files:**
- Modify: `tests/test_controls.py`
- Test: `effects.TFTControls`

- [x] **Step 1: Add a polarity-aware level helper and one test for all short actions.**

Use the board’s verified idle/pressed levels:

```python
def levels(index, pressed):
    result = [True, False, False]  # D0 idle HIGH; D1/D2 idle LOW.
    if pressed:
        result[index] = False if index == 0 else True
    return tuple(result)


def settle(controls, now=0):
    controls.update(levels(0, False), now)
    controls.update(levels(0, False), now + .05)


def test_short_releases_keep_d0_d1_d2_actions(self):
    # D0 short release remains page navigation.
    controls = self.controls()
    controls.update(levels(0, True), 1)
    controls.update(levels(0, True), 1.05)
    controls.update(levels(0, False), 1.1)
    self.assertEqual(controls.update(levels(0, False), 1.15), 'page')

    # D1 short release remains next effect.
    controls = self.controls()
    controls.update(levels(1, True), 2)
    controls.update(levels(1, True), 2.05)
    controls.update(levels(1, False), 2.1)
    self.assertEqual(controls.update(levels(1, False), 2.15), 'next')

    # D2 short release remains the brightness-decrease action.
    controls = self.controls()
    controls.update(levels(2, True), 3)
    controls.update(levels(2, True), 3.05)
    controls.update(levels(2, False), 3.1)
    self.assertEqual(controls.update(levels(2, False), 3.15), 'decrease')
```

The exact helper can be folded into the test class if that matches the existing test style; the required assertions are the three action results above.

- [x] **Step 2: Add the failing any-button hold test.**

```python
def test_three_second_hold_on_any_button_requests_sleep(self):
    for index in range(3):
        controls = self.controls()
        controls.update(levels(index, True), 1)
        controls.update(levels(index, True), 1.05)
        self.assertEqual(controls.update(levels(index, True), 4.05), 'sleep')
        self.assertIsNone(controls.update(levels(index, True), 5))
```

- [x] **Step 3: Run the focused tests and verify the new behavior fails for the intended reason.**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_controls.py' -v
```

Expected: the existing D2 hold may pass, but the new D0/D1 hold assertions fail because the current state machine only returns `sleep` for D2. Short-action assertions must remain green; fix test setup errors before implementation if they do not.

### Task 3: Implement shared any-button hold behavior

**Files:**
- Modify: `effects.py:TFTControls.update`

- [x] **Step 1: Make the countdown represent any currently held button.**

At the beginning of `TFTControls.update`, reset `self.countdown` to zero. For each armed input, compute its active level using the existing D0 active-low/D1-D2 active-high mapping. If that button is pressed and has a `pressed_at`, update the countdown with the maximum remaining hold time across pressed inputs:

```python
self.countdown = 0
...
if pressed and button.pressed_at is not None:
    self.countdown = max(
        self.countdown,
        max(0, button.hold_s - (now - button.pressed_at)),
    )
```

- [x] **Step 2: Route every `HOLD` gesture to the shared sleep action before short-action routing.**

Replace the D2-only branch with this ordering:

```python
if gesture == ButtonGesture.HOLD:
    action = 'sleep'
elif gesture == ButtonGesture.SHORT:
    if index == 0:
        action = 'page'
    elif index == 1:
        action = 'next'
    else:
        action = 'decrease'
```

Keep the existing release-gate behavior and polarity calculation unchanged.

- [x] **Step 3: Run the focused control tests and verify they pass.**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_controls.py' -v
```

Expected: all control tests pass, including short actions for D0/D1/D2 and long holds for each button.

### Task 4: Add failing wake-alarm and all-button release tests

**Files:**
- Modify: `tests/test_sleep.py`
- Test: the Reverse TFT `lights_app.wait_for_wake_release` and `enter_deep_sleep` paths.

- [x] **Step 1: Extend the Reverse TFT sleep mock board with D0, D1, and D2.**

The test loader must provide `board.D0`, `board.D1`, and `board.D2` in addition to the existing wing/display test attributes. Keep the non-display shutdown test unchanged so legacy boards still assert no wake alarms.

- [x] **Step 2: Change the Reverse TFT alarm assertion to require three active-level alarms.**

The test should assert three calls equivalent to:

```python
alarm.pin.PinAlarm(pin=board.D0, value=False, pull=True)
alarm.pin.PinAlarm(pin=board.D1, value=True, pull=True)
alarm.pin.PinAlarm(pin=board.D2, value=True, pull=True)
```

`pull=True` is intentional: CircuitPython’s `PinAlarm` pull is opposite the trigger value, so it supplies D0’s pull-up and D1/D2’s pull-down. Compare the `call_args_list` in order and assert `exit_and_deep_sleep_until_alarms` receives all three alarms before the preserved output pins.

- [x] **Step 3: Add a failing release-gate test for all three pins.**

Mock three `DigitalInOut` objects with D0/D1/D2 levels and verify `wait_for_wake_release()` does not finish until every button has been stably released. Exercise an initially pressed D0, D1, and D2 one at a time, then provide stable idle readings for all three and assert each temporary input is deinitialized by its context manager.

- [x] **Step 4: Run the focused sleep tests and verify the new expectations fail before implementation.**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_sleep.py' -v
```

Expected: the old D2-only alarm assertion and D2-only release helper fail; legacy non-display shutdown, radio fade, trial suppression, and protocol tests remain green.

### Task 5: Implement all-button release gating and wake alarms

**Files:**
- Modify: `lights_app.py:wait_for_wake_release`
- Modify: `lights_app.py:enter_deep_sleep`

- [x] **Step 1: Generalize the release wait to all Reverse TFT buttons.**

Use the verified button table and one `ReleaseGate` per input:

```python
TFT_WAKE_BUTTONS = (
    ('D0', False, digitalio.Pull.UP),
    ('D1', True, digitalio.Pull.DOWN),
    ('D2', True, digitalio.Pull.DOWN),
)
```

For each temporary `DigitalInOut`, configure the listed pull and feed `button.value == active_level` to its gate. Keep the screen title, replace the D2-specific note with `Release buttons`, refresh once, and loop until every gate reports stable release. Close the screen and all temporary inputs before returning.

- [x] **Step 2: Construct one `PinAlarm` per Reverse TFT button.**

Inside the existing `PROFILE['display']` branch, after the all-button release wait and display/power teardown, create:

```python
alarms = tuple(
    alarm.pin.PinAlarm(pin=getattr(board, name), value=active, pull=True)
    for name, active, _ in TFT_WAKE_BUTTONS
)
```

Keep `alarms = ()` for legacy boards. Pass the tuple as positional alarms to `alarm.exit_and_deep_sleep_until_alarms`, followed by the existing `preserve_dios` keyword. Do not add a `TimeAlarm`, change `edge`, or alter the wing output hold.

- [x] **Step 3: Update sleep log wording.**

Change the Reverse TFT log from D2-specific wording to `any button wakes this board`; retain `reset each board to wake` for legacy boards.

- [x] **Step 4: Run the focused sleep tests and verify they pass.**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_sleep.py' -v
```

Expected: all sleep tests pass, including all three pin alarms, release-before-alarm ordering, output preservation, and legacy reset-only behavior.

### Task 6: Update dashboard labels and generic user-facing copy

**Files:**
- Modify: `dashboard.py`
- Modify: `lights_app.py:TFTButtons.poll` and `lights_app.py:update_dashboard`
- Modify: `tests/test_dashboard.py`

- [x] **Step 1: Change the permanent rail label from `SLEEP` to `AUX`.**

In `dashboard.snapshot`, change:

```python
'labels': ('PAGE', 'NEXT', 'AUX')
```

Keep the Brightness page’s dynamic `+`/`-` labels unchanged.

- [x] **Step 2: Replace D2-specific transient wording.**

Use the following user-facing strings:

```python
message = 'Hold any button: %.1fs' % buttons.logic.countdown
...
state['state'] ... else 'Hold any button to sleep'
...
print('SLEEP requested from any button; broadcasting group sleep')
```

Do not change the `HOLD TO SLEEP`, `SLEEPING`, or `Release to cancel` overlay text. Keep display-idle first-press consumption intact.

- [x] **Step 3: Update dashboard tests before running them.**

Change label assertions from `('PAGE','NEXT','SLEEP')` to `('PAGE','NEXT','AUX')` and message fixtures from `Hold D2: 2.0s` to `Hold any button: 2.0s`. Add one assertion that the default page content contains no `SLEEP` button-rail label.

- [x] **Step 4: Run dashboard and control tests.**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_dashboard.py' -v
python3 -m unittest discover -s tests -p 'test_controls.py' -v
```

Expected: both suites pass with no D2-specific permanent menu label or hold guidance.

### Task 7: Update version, current documentation, and TODO

**Files:**
- Modify: `app_version.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `TODO.md`

- [x] **Step 1: Bump the app version.**

Change only the application identity:

```python
APP_VERSION = "1.1.2"
```

Do not change `APP_API_VERSION`, the OTA base version, or wire-format versions.

- [x] **Step 2: Update the current Reverse TFT control documentation.**

In the active controls section, document D0/D1/D2 short-release behavior and state that a three-second hold on any button starts the existing group/local sleep path. State that any button wakes a sleeping board without a hold, the waking gesture is consumed until release, and reset remains valid. Remove current-menu wording that identifies D2 as `SLEEP`; retain historical release notes unchanged.

- [x] **Step 3: Update project guidance and close the completed TODO.**

Change active guidance from D2-only hold/wake wording to any-button wording while preserving the D0 active-low/D1-D2 active-high wiring facts. Remove only the TODO line “Let D0, D1, and D2 wake a sleeping Reverse TFT”; keep the separate hardware button-assembly TODO.

- [x] **Step 4: Review the documentation diff for contradictions.**

Run:

```bash
rg -n -i 'Hold D2|D2.*sleep|SLEEP.*D2|D2.*wake|labels.*SLEEP' README.md AGENTS.md TODO.md dashboard.py lights_app.py tests docs/superpowers/specs/2026-10-07-any-button-sleep-wake-design.md
```

Expected: only historical references outside the active behavior sections and the approved design’s explanatory references remain. No current dashboard or runtime message may identify D2 as the only sleep/wake button.

### Task 8: Full verification and one final commit

**Files:**
- Review all staged and unstaged files; no new source files beyond the approved spec/plan.

- [x] **Step 1: Run targeted tests after all edits.**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_controls.py' -v
python3 -m unittest discover -s tests -p 'test_sleep.py' -v
python3 -m unittest discover -s tests -p 'test_dashboard.py' -v
```

Expected: all targeted tests pass.

- [x] **Step 2: Run the project verification command.**

Run:

```bash
make check
```

Expected: Python compilation, all host unit tests, and `git diff --check` pass. Do not run hardware deployment or claim physical wake qualification from host mocks.

- [x] **Step 3: Inspect the final diff and status.**

Run:

```bash
git status --short
git diff --stat
git diff --check
git diff -- app_version.py effects.py lights_app.py dashboard.py tests/test_controls.py tests/test_sleep.py tests/test_dashboard.py README.md AGENTS.md TODO.md docs/superpowers/specs/2026-10-07-any-button-sleep-wake-design.md
```

Expected: the Reverse TFT baseline is present, NIC-6 changes are limited to the approved scope, the design/plan are included, and no credentials, recordings, `.venv`, `.artifacts`, firmware, or board backups are staged.

- [x] **Step 4: Create the single requested commit.**

Run:

```bash
git add -A
git commit -m "Simplify Reverse TFT sleep and wake buttons"
```

Expected: one commit contains the Reverse TFT baseline, NIC-6 implementation, tests, documentation, and approved design/plan. Report the commit hash and verification results; do not claim hardware wake validation.
