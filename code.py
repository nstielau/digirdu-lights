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
from effects import DebouncedButton, EFFECT_NAMES

if board.board_id == "unexpectedmaker_feathers2":
    PIXEL_PIN = board.IO38  # Factory jumper's physical position, not D6 alias.
elif board.board_id == "adafruit_feather_esp32_v2":
    PIXEL_PIN = board.D32
    if CONFIG.radio_role != "follower":
        raise RuntimeError("ESP32 V2 wiring is configured for consumer mode only")
else:
    raise RuntimeError("Unconfigured board: " + board.board_id)
SAMPLE_RATE = CONFIG.sample_rate
SAMPLE_COUNT = CONFIG.hop_size


class EffectButtons:
    def __init__(self):
        self.inputs = []
        try:
            for gpio, step in ((CONFIG.button_next_gpio, 1), (CONFIG.button_previous_gpio, -1)):
                if gpio is None:
                    continue
                pin = digitalio.DigitalInOut(getattr(board, "IO%d" % gpio))
                pin.switch_to_input(pull=digitalio.Pull.UP)
                self.inputs.append((pin, DebouncedButton(CONFIG.button_debounce_s), step))
        except Exception:
            self.deinit()
            raise

    def poll(self, animation, now):
        for pin, button, step in self.inputs:
            if button.update(not pin.value, now):
                animation.set_effect((animation.effect + step) % len(EFFECT_NAMES))
                print("EFFECT %d %s display=%d" %
                      (animation.effect, EFFECT_NAMES[animation.effect], animation.effect + 1))

    def deinit(self):
        for pin, _, _ in self.inputs:
            pin.deinit()


def microphone():
    if board.board_id != "unexpectedmaker_feathers2":
        raise RuntimeError("Microphone wiring is configured only for FeatherS2")
    import audioi2sin
    # SEL/LR grounded selects the left channel. ICS43434 uses standard I2S
    # with 24 significant bits inside 32-bit slots, then scaled to signed 16-bit.
    return audioi2sin.I2SIn(
        board.IO5, board.IO6, board.IO9, sample_rate=SAMPLE_RATE,
        bit_depth=32, output_bit_depth=16, mono=True,
        left_justified=False, samples_signed=True,
    )


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
        raise RuntimeError("Microphone data is flat; check power, SEL, and GPIO 5/6/9")


def benchmark(seconds=5):
    """Finite live capture/FFT/render benchmark, without driving the LEDs."""
    run(seconds=seconds, drive_pixels=False)


def run(seconds=None, drive_pixels=True):
    CONFIG.validate()
    # Allocate the FFT/renderer BEFORE starting the continuous I2S DMA stream.
    spectrum = Spectrum(CONFIG)
    analyzer = Analyzer(CONFIG)
    animation = CulvertAnimation(CONFIG)
    radio = None
    if CONFIG.radio_role == "leader":
        from wireless import Wireless
        radio = Wireless(CONFIG)
    samples = array.array("h", [0] * CONFIG.hop_size)
    period = CONFIG.hop_size / CONFIG.sample_rate
    buttons = EffectButtons()
    gc.collect()
    with digitalio.DigitalInOut(PIXEL_PIN) as pin:
        pin.switch_to_output(value=False)
        try:
            with microphone() as mic:
                print("AUDIO calibration: keep quiet for %.1f seconds" % CONFIG.calibration_s)
                print("Didgeridoo: %d Hz, FFT=%d hop=%d, IO38, %d pixels, brightness=%.2f" %
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
                        raise RuntimeError("Microphone data is flat; check GPIO 5/6/9, power and SEL=GND")
                    buttons.poll(animation, now)
                    pixels = animation.render(features, max(period / 2, dt))
                    if drive_pixels:
                        neopixel_write(pin, pixels)
                    if radio is not None:
                        radio.publish(features, animation, now)
                    if features.attackEvent:
                        print("ATTACK strength=%.2f" % features.attack)
                    if features.yellEvent:
                        print("YELL vocal=%.2f" % features.vocal)
                    if now >= next_log:
                        print("AUDIO rms=%.1f noise=%.1f vol=%.2f drone=%.2f harm=%.2f timbre=%.2f growl=%.2f vocal=%.2f rough=%.2f active=%s clip=%s" %
                              (features.rms, features.noiseFloor, features.volume, features.drone,
                               features.harmonics, features.timbrePosition, features.growl,
                               features.vocal, features.roughness, features.active, features.clipped))
                        next_log = now + CONFIG.log_interval_s
                        # Explicit collections bound fragmentation; include them
                        # and LED output in the processing-time measurement.
                        gc.collect()
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
        finally:
            neopixel_write(pin, bytes(CONFIG.pixel_count * 3))
            buttons.deinit()
            if radio is not None:
                radio.deinit()


def run_follower():
    from wireless import Wireless
    animation = CulvertAnimation(CONFIG)
    radio = Wireless(CONFIG)
    with digitalio.DigitalInOut(PIXEL_PIN) as pin:
        pin.switch_to_output(value=False)
        try:
            previous = next_log = time.monotonic()
            frames = 0
            while True:
                now = time.monotonic()
                dt = max(0.001, now - previous)
                previous = now
                features = radio.receive(now, animation)
                lost = radio.receiver.fade_if_lost(now, dt)
                pixels = animation.render(features, dt)
                neopixel_write(pin, pixels)
                radio.receiver.clear_events()
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
                    next_log = now + CONFIG.log_interval_s
                    gc.collect()
                time.sleep(max(0, CONFIG.receiver_frame_s - (time.monotonic() - now)))
        finally:
            neopixel_write(pin, bytes(CONFIG.pixel_count * 3))
            radio.deinit()


def main():
    if CONFIG.radio_role == "follower":
        run_follower()
    else:
        run()


if __name__ == "__main__":
    main()
