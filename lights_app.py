"""FeatherS2 microphone producer and FeatherS2/ESP32 V2 wireless lighting."""

import array
import gc
import time

import board
import digitalio
from neopixel_write import neopixel_write
from config import CONFIG
from audio_spectrum import Spectrum
from audio_features import Analyzer
from animation import CulvertAnimation
from sound_reactive import measure
from effects import ButtonGesture, SleepTransition, EFFECT_NAMES
from battery import BatteryMonitor

from hardware import profile, microphone as profile_microphone
PROFILE = profile(board.board_id)
# The soldered S3 producer uses D6 for I2S word-select, so its FeatherWing
# data line cannot share that pin. Keep the common profile for consumers, but
# drive the Reverse TFT's onboard pixel on D33 while this node is a producer.
PIXEL_NAME = ('NEOPIXEL' if PROFILE['id'] == 'adafruit_feather_esp32s3_reverse_tft'
              and CONFIG.radio_role == 'leader' else PROFILE['wing'])
PIXEL_PIN = getattr(board, PIXEL_NAME)
if PROFILE['mic'] is None and CONFIG.radio_role != 'follower':
    raise RuntimeError('ESP32 V2 wiring is configured for consumer mode only')
DISPLAY = None
SAMPLE_RATE = CONFIG.sample_rate
SAMPLE_COUNT = CONFIG.hop_size
TFT_WAKE_BUTTONS = (
    ('D0', False, digitalio.Pull.UP),
    ('D1', True, digitalio.Pull.DOWN),
    ('D2', True, digitalio.Pull.DOWN),
)


class EffectButtons:
    def __init__(self):
        self.inputs = []
        try:
            for gpio, step in ((CONFIG.button_next_gpio, 1),
                               (CONFIG.button_extra_next_gpio, 1),
                               (CONFIG.button_previous_gpio, -1)):
                if gpio is None:
                    continue
                pin = digitalio.DigitalInOut(getattr(board, "IO%d" % gpio))
                self.inputs.append((pin, ButtonGesture(CONFIG.button_debounce_s, CONFIG.button_sleep_hold_s), step))
                pin.switch_to_input(pull=digitalio.Pull.UP)
                print("BUTTON GPIO%d step=%+d pull=UP" % (gpio, step))
        except Exception:
            self.deinit()
            raise

    def poll(self, animation, now, sleep, allow_sleep=True, radio=None):
        for pin, button, step in self.inputs:
            gesture = button.update(not pin.value, now)
            if sleep.started is not None:
                continue
            if gesture == ButtonGesture.HOLD:
                if allow_sleep:
                    sleep.request(now, CONFIG.sleep_fade_s)
                    print("SLEEP requested: red fade %.1f s" % CONFIG.sleep_fade_s)
                else:
                    print("SLEEP ignored during OTA trial; retry after confirmation")
            elif gesture == ButtonGesture.SHORT:
                animation.set_effect((animation.effect + step) % len(EFFECT_NAMES))
                print("EFFECT %d %s display=%d" %
                      (animation.effect, EFFECT_NAMES[animation.effect], animation.effect + 1))

    def deinit(self):
        for pin, _, _ in self.inputs:
            pin.deinit()


class TFTButtons:
    def __init__(self):
        from effects import TFTControls
        self.inputs = []
        self.logic = TFTControls(CONFIG.radio_role, CONFIG.button_debounce_s, CONFIG.button_sleep_hold_s)
        try:
            for name in ('D0', 'D1', 'D2'):
                pin = digitalio.DigitalInOut(getattr(board,name))
                self.inputs.append(pin)
                pin.switch_to_input(pull=digitalio.Pull.UP if name == 'D0' else digitalio.Pull.DOWN)
        except Exception:
            self.deinit()
            raise

    def poll(self, animation, now, sleep, allow_sleep=True, radio=None):
        levels=tuple(pin.value for pin in self.inputs)
        if DISPLAY and not DISPLAY.failed and DISPLAY.button_activity(now,not levels[0] or levels[1] or levels[2]):
            # Feed released levels so no wake press becomes NEXT or a long sleep.
            self.logic.update((True,False,False),now)
            return
        action = self.logic.update(levels,now)
        if sleep.started is not None:
            return
        if action == 'page' and DISPLAY:
            DISPLAY.toggle()
            print('TFT page=%d' % (DISPLAY.page + 1))
        else:
            brightness_page=DISPLAY and DISPLAY.page==2
            if action=='next' and brightness_page:action='brighter'
            elif action=='decrease':
                if not brightness_page:return
                action='dimmer'
            if action not in ('next','sleep','brighter','dimmer'):return
            if action=='sleep' and not allow_sleep:
                if radio and radio.control:radio.control.feedback('SLEEP BLOCKED',now)
                if DISPLAY:DISPLAY.set_banner('SLEEP BLOCKED',now)
                print('SLEEP ignored during OTA trial')
                return
            if CONFIG.radio_role=='follower':
                from radio_protocol import NEXT_EFFECT,GROUP_SLEEP,BRIGHTER,DIMMER
                command={'next':NEXT_EFFECT,'sleep':GROUP_SLEEP,'brighter':BRIGHTER,'dimmer':DIMMER}[action]
                if radio:radio.request_control(command,now)
            elif action=='next':
                animation.set_effect((animation.effect+1)%len(EFFECT_NAMES))
                if DISPLAY:DISPLAY.set_banner('CHANGING EFFECT',now)
                print('EFFECT %d %s'%(animation.effect,EFFECT_NAMES[animation.effect]))
            elif action in ('brighter','dimmer'):
                animation.adjust_brightness(CONFIG.brightness_step*(1 if action=='brighter' else -1))
                if radio:radio.next_brightness=now
                if DISPLAY:DISPLAY.set_banner('SETTING BRIGHTNESS',now)
            else:
                sleep.request(now,CONFIG.sleep_fade_s)
                print('SLEEP requested from any button; broadcasting group sleep')

    def deinit(self):
        for pin in self.inputs:pin.deinit()


def start_dashboard():
    global DISPLAY
    DISPLAY = None
    if PROFILE['display'] and CONFIG.display_enabled:
        from dashboard import create
        DISPLAY = create(CONFIG)
    elif PROFILE['display']:
        try:
            board.DISPLAY.auto_refresh = False
            board.DISPLAY.brightness = 0
            board.DISPLAY.root_group = None
        except Exception as error:
            print('TFT off unavailable:',type(error).__name__)
    import hardware
    close_boot=getattr(hardware,'close_boot',None)
    if close_boot:close_boot()
    return DISPLAY


def update_dashboard(now, features, animation, battery, radio, rate, spare,
                     overruns=0, sleep=None, buttons=None, fault=False):
    if not DISPLAY or DISPLAY.failed:
        return
    from dashboard import sleep_overlay
    remaining=max(0,sleep.duration-sleep.elapsed(now)) if sleep and sleep.started is not None else None
    holding=buttons.logic.countdown if buttons and hasattr(buttons,'logic') else 0
    if DISPLAY.page==2 and holding>CONFIG.button_sleep_hold_s-.5:holding=0
    control=getattr(radio,'control',None) if radio else None
    overlay=sleep_overlay(holding=holding,remaining=remaining)
    DISPLAY.set_overlay(overlay)
    DISPLAY.set_banner(control.status(now) if control else '',now)
    if not DISPLAY.visible(now):return
    if now < DISPLAY.next_refresh:return
    if not DISPLAY.ready(now, spare):
        DISPLAY.skipped += 1
        return
    preparation_started = time.monotonic()
    from dashboard import snapshot, device_information
    receiver = radio.receiver if radio else None
    presence = radio.presence if radio else None
    seen = presence.count(now) if presence else 0
    age = now-receiver.last_audio if receiver and receiver.audio_sequence is not None else None
    count = receiver.accepted if receiver else radio.sent if radio else 0
    message = ''
    if sleep and sleep.started is not None:message='SLEEP / fading'
    elif buttons and hasattr(buttons,'logic') and buttons.logic.countdown:
        message='Hold any button: %.1fs'%buttons.logic.countdown
    reading = battery.update(now)
    try:
        import ota_status
        maintenance = ota_status.snapshot().get('state') == 'maintenance'
    except Exception:
        maintenance = False
    state = snapshot(CONFIG.radio_role, animation.effect, rms=features.rms, volume=features.volume,
                     clipped=features.clipped, calibrating=features.calibrating, active=features.active,
                     fault=fault, age=age,timeout=CONFIG.radio_timeout_s,seen=seen,
                     full=presence.full if presence else False,rate=rate.update(count,now),
                     battery=reading,spectrum=features.spectrum,
                     tx_failed=radio.radio.send_failure if radio else 0,message=message,overlay=overlay,
                     brightness=CONFIG.brightness,brightness_max=CONFIG.brightness_max,
                     banner=DISPLAY.banner,animation_frame=int(now*2)%4,
                     maintenance=maintenance,
                     device=(device_information(
                         CONFIG.radio_role,
                         (radio.local_mac if radio and radio.receiver is None else CONFIG.leader_mac)
                     ) if DISPLAY.page==3 and not overlay else None))
    preparation = time.monotonic() - preparation_started
    DISPLAY.update(now,state,spare,preparation=preparation)


DIAGNOSTIC_NEXT = 0


def log_device_diagnostics(now, radio, overruns=0):
    global DIAGNOSTIC_NEXT
    if not PROFILE['display'] or radio is None or now < DIAGNOSTIC_NEXT:
        return
    DIAGNOSTIC_NEXT = now + 10
    from app_version import APP_VERSION
    rx = radio.receiver or radio.presence
    print('DEVICE v%s role=%s CH%d G%d source=%s TX=%d ok=%d failed=%d errors=%d skipped=%d RX=%d rejected=%d overruns=%d' %
          (APP_VERSION,CONFIG.radio_role,CONFIG.radio_channel,CONFIG.radio_group,
           CONFIG.leader_mac if radio.receiver else 'local',radio.sent,
           radio.radio.send_success,radio.radio.send_failure,radio.errors,radio.skipped,
           rx.accepted if rx else 0,rx.rejected if rx else 0,overruns))


def show_mic_fault():
    print('AUDIO microphone fault; role unchanged')
    if PROFILE['display']:
        from hardware import BootScreen
        screen = BootScreen()
        screen.phase('MIC FAULT - check wiring / reset')


def microphone():
    return profile_microphone(SAMPLE_RATE)


def read_level(mic, samples):
    count = mic.record(samples, len(samples))
    if count != len(samples):
        raise RuntimeError("Incomplete I2S capture: %d/%d" % (count, len(samples)))
    return measure(samples, count)


def test_microphone(seconds=10):
    """Print levels without driving LEDs; call with make test-mic."""
    samples = array.array("h", [0] * SAMPLE_COUNT)
    print("MIC TEST: stay quiet, then clap or speak near the microphone")
    with microphone() as mic:
        start = time.monotonic()
        next_log = start + 0.5
        lowest = 32768.0
        highest = 0.0
        max_span = 0
        while time.monotonic() - start < seconds:
            rms, peak, span = read_level(mic, samples)
            # Ignore the microphone's initial wake-up interval.
            if time.monotonic() - start < 0.2:
                continue
            lowest = min(lowest, rms)
            highest = max(highest, rms)
            max_span = max(max_span, span)
            if time.monotonic() >= next_log:
                print("MIC rms=%.1f peak=%.1f span=%d" % (rms, peak, span))
                next_log = time.monotonic() + 0.5
    print("MIC TEST RESULT min_rms=%.1f max_rms=%.1f max_span=%d" %
          (lowest, highest, max_span))
    if max_span == 0:
        raise RuntimeError("Microphone data is flat; check power, SEL, and the configured I2S pins")


def benchmark(seconds=5):
    """Finite live capture/FFT/render benchmark, without driving the LEDs."""
    run(seconds=seconds, drive_pixels=False)


def run(seconds=None, drive_pixels=True, health=None):
    CONFIG.validate()
    # Allocate the FFT/renderer BEFORE starting the continuous I2S DMA stream.
    spectrum = Spectrum(CONFIG)
    analyzer = Analyzer(CONFIG)
    animation = CulvertAnimation(CONFIG)
    battery = BatteryMonitor(CONFIG.battery_sample_s, PROFILE['battery'] == 'max17048')
    start_dashboard()
    rate = None
    if DISPLAY:
        from dashboard import Rate
        rate = Rate()
    radio = None
    if CONFIG.radio_role == "leader":
        from wireless import Wireless
        radio = Wireless(CONFIG)
    samples = array.array("h", [0] * CONFIG.hop_size)
    period = CONFIG.hop_size / CONFIG.sample_rate
    buttons = TFTButtons() if PROFILE["display"] else EffectButtons()
    sleep = SleepTransition()
    gc.collect()
    with digitalio.DigitalInOut(PIXEL_PIN) as pin:
        pin.switch_to_output(value=False)
        try:
            with microphone() as mic:
                print("AUDIO calibration: keep quiet for %.1f seconds" % CONFIG.calibration_s)
                print("Didgeridoo: %d Hz, FFT=%d hop=%d, %d pixels, brightness=%.2f" %
                      (CONFIG.sample_rate, CONFIG.fft_size, CONFIG.hop_size,
                       CONFIG.pixel_count, CONFIG.brightness))
                print("EFFECT %d %s; BOOT advances while running" % (animation.effect, EFFECT_NAMES[animation.effect]))
                started = previous = next_log = time.monotonic()
                flat_since = None
                frames = overruns = discontinuities = 0
                total_work = max_work = 0.0
                while seconds is None or time.monotonic() - started < seconds:
                    count = mic.record(samples, len(samples))
                    now = time.monotonic()
                    dt = now - previous
                    previous = now
                    # ESP32-S2's driver cannot report every DMA overflow; a long
                    # wall-clock gap is an additional warning, not proof of loss.
                    if count != len(samples) or mic.overflow or dt > 3 * period:
                        discontinuities += 1
                        spectrum.reset_history()
                        analyzer.discontinuity()
                        print("AUDIO discontinuity: samples=%d gap_ms=%.1f" % (count, dt * 1000))
                        if count != len(samples):
                            continue
                    raw = spectrum.push(samples)
                    if raw is None:
                        continue
                    features = analyzer.update(raw, max(period / 2, dt))
                    if raw["span"] == 0:
                        if flat_since is None:
                            flat_since = now
                    else:
                        flat_since = None
                    if flat_since is not None and now - flat_since > CONFIG.flat_timeout_s:
                        raise RuntimeError("Microphone data is flat; check the configured I2S pins, power, and SEL wiring")
                    if radio is not None:
                        radio.receive_presence(now,animation,sleep,allow_sleep=not (health and health.trial))
                    buttons.poll(animation, now, sleep, allow_sleep=not (health and health.trial),radio=radio)
                    if animation.effect == 5:
                        animation.battery_voltage = battery.update(now)["voltage"]
                    pixels = (sleep.pixels(now, CONFIG) if sleep.started is not None else
                              animation.render(features, max(period / 2, dt)))
                    if drive_pixels:
                        neopixel_write(pin, pixels)
                    if radio is not None:
                        radio.publish(features, animation, now, sleep)
                    if health is not None:
                        health(features, radio)
                    if sleep.done(now):
                        raise SleepRequested()
                    if features.attackEvent:
                        print("ATTACK strength=%.2f" % features.attack)
                    if features.yellEvent:
                        print("YELL vocal=%.2f" % features.vocal)
                    if now >= next_log:
                        print("AUDIO rms=%.1f noise=%.1f vol=%.2f drone=%.2f harm=%.2f timbre=%.2f growl=%.2f vocal=%.2f rough=%.2f active=%s clip=%s" %
                              (features.rms, features.noiseFloor, features.volume, features.drone,
                               features.harmonics, features.timbrePosition, features.growl,
                               features.vocal, features.roughness, features.active, features.clipped))
                        print("SPECTRUM levels=" + str(tuple(round(v, 2) for v in features.spectrum)))
                        log_device_diagnostics(now,radio,overruns)
                        next_log = now + CONFIG.log_interval_s
                        # Explicit collections bound fragmentation; include them
                        # and LED output in the processing-time measurement.
                        gc.collect()
                    update_dashboard(now,features,animation,battery,radio,rate,
                                     period-(time.monotonic()-now),overruns,sleep,buttons)
                    work = time.monotonic() - now
                    frames += 1
                    total_work += work
                    max_work = max(max_work, work)
                    if work > period:
                        overruns += 1
                        if overruns == 1 or overruns % 100 == 0:
                            print("AUDIO processing over budget: %.1f ms / %.1f ms" %
                                  (work * 1000, period * 1000))
                print("AUDIO BENCH frames=%d fps=%.1f work_mean_ms=%.1f work_max_ms=%.1f budget_ms=%.1f overruns=%d discontinuities=%d" %
                      (frames, frames / (time.monotonic() - started),
                       total_work * 1000 / max(frames, 1), max_work * 1000,
                       period * 1000, overruns, discontinuities))
                if radio is not None:
                    print("RADIO BENCH sent=%d errors=%d skipped=%d" %
                          (radio.sent, radio.errors, radio.skipped))
        except (OSError, RuntimeError):
            show_mic_fault()
            raise
        finally:
            neopixel_write(pin, bytes(CONFIG.pixel_count * 3))
            buttons.deinit()
            if radio is not None:
                radio.deinit()


def run_follower(health=None):
    from wireless import Wireless
    animation = CulvertAnimation(CONFIG)
    battery = BatteryMonitor(CONFIG.battery_sample_s, PROFILE['battery'] == 'max17048')
    start_dashboard()
    rate = None
    if DISPLAY:
        from dashboard import Rate
        rate = Rate()
    radio = Wireless(CONFIG)
    buttons = TFTButtons() if PROFILE["display"] else None
    with digitalio.DigitalInOut(PIXEL_PIN) as pin:
        pin.switch_to_output(value=False)
        try:
            previous = next_log = time.monotonic()
            frames = 0
            sleep_announced = False
            while True:
                now = time.monotonic()
                dt = max(0.001, now - previous)
                previous = now
                features = radio.receive(now, animation)
                lost = radio.receiver.fade_if_lost(now, dt)
                if animation.effect == 5:
                    animation.battery_voltage = battery.update(now)["voltage"]
                # Ignore sleep during the initial OTA health trial. An intentional
                # sleep/reset must not be mistaken for a failed candidate.
                sleep = radio.receiver.sleep
                if health and health.trial:
                    if sleep.started is not None:
                        print("SLEEP ignored during OTA trial; retry after confirmation")
                        sleep.started = None
                if buttons:
                    buttons.poll(animation,now,sleep,allow_sleep=not (health and health.trial),radio=radio)
                radio.heartbeat(now)
                if sleep.started is not None and not sleep_announced:
                    print("SLEEP received: red fade remaining=%.2f s" %
                          max(0.0, sleep.duration - sleep.elapsed(now)))
                    sleep_announced = True
                pixels = (sleep.pixels(now, CONFIG) if sleep.started is not None else
                          animation.render(features, dt))
                neopixel_write(pin, pixels)
                radio.receiver.clear_events()
                if health is not None:
                    health(features, radio)
                if sleep.done(now):
                    raise SleepRequested()
                frames += 1
                if now >= next_log:
                    age_ms = (int((now - radio.receiver.last_receive) * 1000)
                              if radio.receiver.accepted else -1)
                    lit = sum(1 for i in range(0, len(pixels), 3)
                              if pixels[i] or pixels[i + 1] or pixels[i + 2])
                    print("LIGHTS frame=%d received=%d rejected=%d effect=%s indicator=%d link=%s age_ms=%d active=%s vol=%.2f drone=%.2f growl=%.2f vocal=%.2f lit=%d/%d peak=%d" %
                          (frames, radio.receiver.accepted, radio.receiver.rejected,
                           EFFECT_NAMES[animation.effect],
                           animation.effect + 1 if animation.indicator_remaining > 0 else 0,
                           "lost/fading" if lost else "live", age_ms, features.active,
                           features.volume, features.drone, features.growl, features.vocal,
                           lit, CONFIG.pixel_count, max(pixels)))
                    print("SPECTRUM levels=" + str(tuple(round(v, 2) for v in features.spectrum)))
                    log_device_diagnostics(now,radio)
                    next_log = now + CONFIG.log_interval_s
                    gc.collect()
                update_dashboard(now,features,animation,battery,radio,rate,
                                 CONFIG.receiver_frame_s-(time.monotonic()-now),sleep=sleep,buttons=buttons)
                time.sleep(max(0, CONFIG.receiver_frame_s - (time.monotonic() - now)))
        finally:
            neopixel_write(pin, bytes(CONFIG.pixel_count * 3))
            radio.deinit()
            if buttons:buttons.deinit()


class SleepRequested(BaseException):
    """Unwind hardware contexts without triggering the OTA failure handler."""


def wait_for_wake_release():
    from effects import ReleaseGate
    from hardware import TextScreen
    screen = TextScreen((('title',12,22,18,2,0xff4596),
                         ('note',12,72,18,2,0xffffff)),
                        brightness=CONFIG.display_brightness,rotation=CONFIG.display_rotation)
    screen.text('title','SLEEP READY')
    screen.text('note','Release buttons')
    screen.refresh()
    gates = [ReleaseGate(CONFIG.button_debounce_s) for _ in TFT_WAKE_BUTTONS]
    buttons = []
    try:
        for name, _, pull in TFT_WAKE_BUTTONS:
            button = digitalio.DigitalInOut(getattr(board,name))
            button.switch_to_input(pull=pull)
            buttons.append(button)
        while True:
            now = time.monotonic()
            released = True
            for gate, button, (_, active, _) in zip(gates,buttons,TFT_WAKE_BUTTONS):
                if not gate.update(button.value == active,now):
                    released = False
            if released:
                break
            time.sleep(.01)
    finally:
        for button in buttons:
            button.deinit()
        screen.close()


def enter_deep_sleep():
    import alarm
    import microcontroller
    import supervisor
    import wifi
    # The caller has already blacked out LEDs and closed I2S, GPIO and ESP-NOW.
    # Disable the watchdog also for CircuitPython's USB-connected simulated sleep.
    microcontroller.watchdog.mode = None
    supervisor.runtime.autoreload = False
    wifi.radio.enabled = False
    alarms = ()
    held = ()
    if PROFILE['display']:
        wait_for_wake_release()
        if DISPLAY:DISPLAY.close()
        from hardware import sleep_power
        held = sleep_power()
        alarms = tuple(
            alarm.pin.PinAlarm(pin=getattr(board,name),value=active,pull=True)
            for name, active, _ in TFT_WAKE_BUTTONS)
    # Keep the powered wing's data input LOW through VM teardown and sleep.
    # Releasing it to high impedance can latch stray bits after the black frame.
    # Do not use a with/finally here: DeepSleepRequest unwinds Python contexts.
    sleep_pin = digitalio.DigitalInOut(PIXEL_PIN)
    sleep_pin.switch_to_output(value=False)
    neopixel_write(sleep_pin, bytes(CONFIG.pixel_count * 3))
    sleep_pin.value = False
    time.sleep(0.001)  # Allow the all-black frame to latch before holding the pin.
    print("SLEEP entering deep sleep; wing data held LOW; " +
          ("any button or reset wakes this board" if PROFILE["display"] else "reset each board to wake"))
    # Pin preservation is an output hold, NOT a PinAlarm or other wake source.
    alarm.exit_and_deep_sleep_until_alarms(*alarms, preserve_dios=(sleep_pin,) + held)


def main(health=None):
    try:
        if CONFIG.radio_role == "follower":
            run_follower(health=health)
        else:
            run(health=health)
    except SleepRequested:
        enter_deep_sleep()


if __name__ == "__main__":
    main()
