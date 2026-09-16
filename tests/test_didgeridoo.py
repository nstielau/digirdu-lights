"""Deterministic PCM scenarios exercise the real FFT, detectors and renderer."""

import array
import math
import unittest

import numpy as np

from config import Config
from audio_spectrum import Spectrum
from audio_features import Analyzer, AudioFeatures
from animation import CulvertAnimation


class Rig:
    def __init__(self, **overrides):
        self.c = Config(**overrides)
        self.spectrum = Spectrum(self.c)
        self.analyzer = Analyzer(self.c)
        self.index = 0
        self.rng = np.random.default_rng(42)

    def play(self, seconds, tones=(), noise=0, dc=0, modulation=0):
        result = []
        for _ in range(max(1, round(seconds * self.c.sample_rate / self.c.hop_size))):
            t = (np.arange(self.c.hop_size) + self.index) / self.c.sample_rate
            values = np.zeros(self.c.hop_size) + dc
            for hz, amplitude in tones:
                values += amplitude * np.sin(2 * math.pi * hz * t)
            if noise:
                # Band-limit noise to the low/mid formant area before adding it.
                white = self.rng.normal(0, 1, self.c.hop_size)
                spectrum = np.fft.rfft(white)
                freq = np.fft.rfftfreq(self.c.hop_size, 1 / self.c.sample_rate)
                spectrum[(freq < 180) | (freq > 1000)] = 0
                grain = np.fft.irfft(spectrum, n=self.c.hop_size)
                grain /= max(float(np.std(grain)), 1e-12)
                values += noise * grain * (1 + modulation * np.sin(2 * math.pi * 9 * t))
            samples = array.array("h", np.clip(values, -32768, 32767).astype(np.int16).tolist())
            self.index += self.c.hop_size
            raw = self.spectrum.push(samples)
            if raw is not None:
                f = self.analyzer.update(raw, self.c.hop_size / self.c.sample_rate)
                result.append(dict(vars(f)))
        return result

    def calibrate(self):
        self.play(2.5)


class SpectrumTests(unittest.TestCase):
    def test_dc_and_silence_have_no_energy_or_events(self):
        rig = Rig()
        frames = rig.play(4, dc=1500)
        for f in frames:
            self.assertEqual(f["rms"], 0)
            self.assertEqual(f["volume"], 0)
            self.assertFalse(f["attackEvent"] or f["yellEvent"])

    def test_fft_power_and_band_placement(self):
        for size in (512, 1024):
            for band, hz in enumerate((93.75, 312.5, 750, 2000, 5000)):
                rig = Rig(fft_size=size, hop_size=size // 2)
                frames = rig.play(0.2, ((hz, 1000),))
                energy = frames[-1]["bandEnergy"]
                self.assertEqual(max(range(5), key=lambda i: energy[i]), band)
                self.assertAlmostEqual(sum(energy), 500000, delta=3000)
                self.assertAlmostEqual(frames[-1]["rms"], 1000 / math.sqrt(2), delta=2)

    def test_dc_removal_and_gain_do_not_move_centroid(self):
        values = []
        for gain, dc in ((1, 0), (3, 5000)):
            rig = Rig(gain=gain)
            rig.calibrate()
            f = rig.play(3, ((93.75, 400), (750, 300)), dc=dc)[-1]
            values.append(f)
        self.assertAlmostEqual(values[0]["centroid"], values[1]["centroid"], delta=0.01)
        self.assertAlmostEqual(values[0]["timbrePosition"], values[1]["timbrePosition"], delta=0.01)

    def test_supported_rate_and_invalid_configuration(self):
        rig = Rig(sample_rate=22050, bands=((45, 180), (180, 450), (450, 1000),
                                           (1000, 3500), (3500, 11025)))
        rig.calibrate()
        self.assertGreater(rig.play(2, ((100, 1000),))[-1]["drone"], 0.8)
        for kwargs in ({"fft_size": 256}, {"hop_size": 100}, {"sample_rate": 8000},
                       {"decay_s": 0}, {"pixel_count": 0}, {"made_up": 1}):
            with self.assertRaises(ValueError):
                Config(**kwargs)


class DetectorTests(unittest.TestCase):
    def rig(self):
        rig = Rig()
        rig.calibrate()
        return rig

    def test_sustained_drone_across_range_and_loudness(self):
        for hz in (50, 93.75, 140, 175):
            for amplitude in (100, 10000):
                rig = self.rig()
                frames = rig.play(3, ((hz, amplitude),))
                self.assertGreater(frames[-1]["drone"], 0.75, (hz, amplitude, frames[-1]))
                self.assertLess(frames[-1]["vocal"], 0.01)
                self.assertLess(frames[-1]["growl"], 0.1)
                self.assertFalse(any(f["yellEvent"] for f in frames))
                self.assertFalse(any(f["attackEvent"] for f in frames[-30:]))

    def test_equal_volume_timbre_moves_without_losing_drone(self):
        rig = self.rig()
        a = rig.play(3, ((93.75, 1000), (281.25, 600)))[-1]
        b = rig.play(3, ((93.75, 1000), (750, 600)))[-1]
        self.assertAlmostEqual(a["rms"], b["rms"], delta=3)
        self.assertGreater(b["timbrePosition"], a["timbrePosition"] + 0.35)
        self.assertGreater(min(a["drone"], b["drone"]), 0.8)

    def test_growl_uses_texture_not_volume(self):
        rig = self.rig()
        clean = rig.play(3, ((93.75, 4000), (375, 1600)))[-1]
        growl = rig.play(3, ((93.75, 1000),), noise=1000, modulation=0.7)[-1]
        self.assertLess(growl["rms"], clean["rms"])
        self.assertGreater(growl["growl"], clean["growl"] + 0.15)
        self.assertGreater(growl["roughness"], clean["roughness"] + 0.2)
        self.assertGreater(growl["drone"], 0.7)

    def test_vocal_layer_yell_once_and_rearms(self):
        rig = self.rig()
        rig.play(2, ((93.75, 1000),))
        vocal = rig.play(2, ((93.75, 1000), (1500, 1600), (2500, 900)))
        self.assertEqual(sum(f["yellEvent"] for f in vocal), 1)
        self.assertGreater(vocal[-1]["vocal"], 0.7)
        self.assertGreater(vocal[-1]["drone"], 0.8)
        rig.play(1, ((93.75, 1000),))
        again = rig.play(1, ((93.75, 1000), (2000, 2200)))
        self.assertEqual(sum(f["yellEvent"] for f in again), 1)

    def test_simultaneous_drone_growl_and_vocal(self):
        rig = self.rig()
        rig.play(2, ((93.75, 1000),))
        layers = rig.play(3, ((93.75, 1000), (1800, 1500)), noise=1200, modulation=0.7)
        f = layers[-1]
        self.assertGreater(f["drone"], 0.6)
        self.assertGreater(f["growl"], 0.1)
        self.assertGreater(f["vocal"], 0.35)

    def test_attack_rearm_and_echo_decay(self):
        rig = self.rig()
        rig.play(2, ((93.75, 500),))
        burst = rig.play(0.096, ((93.75, 3000),), noise=1500)
        self.assertTrue(any(f["attackEvent"] and f["attack"] > 0.5 for f in burst))
        tail = []
        for i in range(50):
            tail += rig.play(0.032, ((93.75, 3000 * math.exp(-i / 8)),))
        self.assertLessEqual(sum(f["attackEvent"] for f in tail), 1)
        rig.play(1)
        again = rig.play(0.096, ((93.75, 3000),), noise=1500)
        self.assertTrue(any(f["attackEvent"] for f in again))

    def test_loud_event_does_not_poison_normalization(self):
        rig = self.rig()
        rig.play(3, ((93.75, 800),))
        noise = rig.analyzer.noise
        level = rig.analyzer.level_reference
        rig.play(0.064, ((93.75, 25000), (2000, 5000)))
        self.assertAlmostEqual(rig.analyzer.noise, noise, delta=0.01)
        self.assertLess(rig.analyzer.level_reference, level * 1.02)
        self.assertGreater(rig.play(1, ((93.75, 800),))[-1]["drone"], 0.8)

    def test_sustained_playing_is_not_learned_as_background(self):
        rig = self.rig()
        noise = rig.analyzer.noise
        f = rig.play(60, ((93.75, 1000),))[-1]
        self.assertAlmostEqual(rig.analyzer.noise, noise, delta=0.01)
        self.assertGreater(f["drone"], 0.8)

    def test_calibration_rejects_brief_loud_outlier(self):
        rig = Rig()
        rig.play(0.6)
        rig.play(0.128, ((100, 20000),))
        rig.play(1.8)
        self.assertFalse(rig.analyzer.features.calibrating)
        self.assertLess(rig.analyzer.noise, 3)

    def test_stop_decays_and_event_flags_clear(self):
        rig = self.rig()
        before = rig.play(3, ((93.75, 1000),))[-1]
        after = rig.play(1)[-1]
        late = rig.play(25)[-1]
        self.assertFalse(after["active"])
        self.assertGreater(after["decay"], 0.2)
        self.assertLess(after["drone"], before["drone"])
        self.assertGreater(after["drone"], 0)
        self.assertFalse(after["attackEvent"] or after["yellEvent"])
        self.assertLess(late["decay"], 0.002)

    def test_bounds_clipping_and_discontinuity(self):
        rig = self.rig()
        rig.analyzer.discontinuity()
        frames = rig.play(0.096, ((100, 45000), (1300, 15000)), noise=5000)
        self.assertTrue(any(f["clipped"] for f in frames))
        self.assertFalse(any(f["attackEvent"] or f["yellEvent"] for f in frames))
        for f in frames:
            for name in ("volume", "drone", "harmonics", "timbrePosition", "growl", "vocal",
                         "roughness", "centroid", "attack", "decay", "flatness", "flux"):
                self.assertTrue(math.isfinite(f[name]) and 0 <= f[name] <= 1, (name, f[name]))


class AnimationTests(unittest.TestCase):
    def test_layers_and_brightness_cap(self):
        c = Config()
        a = CulvertAnimation(c)
        f = AudioFeatures()
        self.assertEqual(a.render(f, 0.032), bytes(c.pixel_count * 3))
        f.drone = f.volume = f.decay = 0.8
        base = bytes(a.render(f, 0.032))
        f.timbrePosition = 0.9
        changed = bytes(a.render(f, 0.032))
        self.assertNotEqual(base, changed)
        f.growl = f.vocal = f.attack = 1
        f.attackEvent = f.yellEvent = True
        for _ in range(100):
            pixels = a.render(f, 0.032)
            self.assertLessEqual(max(pixels), int(255 * c.brightness))
        self.assertEqual(len(a.pulses), c.max_pulses)

    def test_pulse_moves_outward_and_trails_fade(self):
        # Isolate the traveling pulse from the default effect's whole-wing hit.
        a = CulvertAnimation(Config(trail_s=0.02, responsive_trail_s=0.02,
                                    responsive_flash_gain=0))
        f = AudioFeatures()
        f.attack = 1
        f.attackEvent = True
        first = bytes(a.render(f, 0.032))
        f.attackEvent = False
        for _ in range(25):
            later = bytes(a.render(f, 0.032))
        def distance(pixels):
            weights = [sum(pixels[i * 3:i * 3 + 3]) for i in range(32)]
            return sum(abs(-1 + 2 * i / 31) * w for i, w in enumerate(weights)) / sum(weights)
        self.assertGreater(distance(later), distance(first) + 0.2)
        for _ in range(500):
            final = a.render(f, 0.032)
        self.assertEqual(final, bytes(96))

    def test_multiple_wings_and_coordinate_mapping(self):
        c = Config(pixel_count=96)
        a = CulvertAnimation(c)
        f = AudioFeatures()
        f.drone = 1
        self.assertEqual(len(a.render(f, 0.032)), 288)
        c = Config(pixel_count=2, pixel_positions=((-0.5, 0.2), (0.5, 0.2)))
        pixels = CulvertAnimation(c).render(f, 0.032)
        self.assertEqual(pixels[:3], pixels[3:])


if __name__ == "__main__":
    unittest.main()
