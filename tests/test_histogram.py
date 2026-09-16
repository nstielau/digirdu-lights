"""Diagnostic frequency placement, dynamics, physical wiring and RF mirroring."""
import unittest

from config import Config
from audio_features import AudioFeatures
from animation import CulvertAnimation
from radio_protocol import Transmitter, Receiver, SIZE
from test_didgeridoo import Rig


class HistogramTests(unittest.TestCase):
    def test_eight_actual_frequency_buckets_and_dc_rejection(self):
        for size in (512, 1024):
            for bucket, hz in enumerate((62.5, 125, 250, 500, 1000, 2000, 4000, 6000)):
                rig = Rig(fft_size=size, hop_size=size)
                rig.calibrate()
                levels = rig.play(.5, ((hz, 100),), dc=1500)[-1]['spectrum']
                self.assertEqual(max(range(8), key=lambda i: levels[i]), bucket)
                self.assertGreater(levels[bucket], .35)
                self.assertTrue(all(0 <= v <= 1 for v in levels))
        rig = Rig()
        self.assertEqual(rig.play(3, dc=1000)[-1]['spectrum'], (0,) * 8)

    def test_volume_rises_without_framewise_auto_stretch_and_releases(self):
        rig = Rig()
        rig.calibrate()
        quiet = rig.play(.5, ((500, 20),))[-1]['spectrum'][3]
        loud = rig.play(.5, ((500, 160),))[-1]['spectrum'][3]
        self.assertGreater(loud, 2 * quiet)
        reference = rig.analyzer.level_reference
        rig.play(.064, ((500, 20000),))
        self.assertLess(rig.analyzer.level_reference, reference * 1.02)
        decay = rig.play(2)
        self.assertGreater(decay[0]['spectrum'][3], 0)
        self.assertLess(decay[-1]['spectrum'][3], .003)

    def test_calibrated_background_stays_dark(self):
        rig = Rig()
        rig.play(4, ((500, 20),))
        self.assertLess(max(rig.analyzer.features.spectrum), .01)
        loud = rig.play(.5, ((500, 400),))[-1]['spectrum']
        self.assertGreater(loud[3], .4)

    def test_bottom_up_columns_fractional_top_and_brightness(self):
        f = AudioFeatures()
        f.spectrum = (0, .25, .5, .75, 1, .125, .375, .625)
        pixels = CulvertAnimation(Config()).render(f, .064)
        for x, level in enumerate(f.spectrum):
            for y in range(4):
                index = ((3-y)*8+x)*3
                peak = max(pixels[index:index+3])
                self.assertEqual(peak, int(38.25 * max(0, min(1, level*4-y))))
        self.assertLessEqual(max(pixels), 38)
        self.assertEqual(CulvertAnimation(Config()).render(AudioFeatures(), .064), bytes(96))

    def test_rotation_tiling_and_coordinate_independence(self):
        f = AudioFeatures()
        f.spectrum = tuple(i/8 for i in range(8))
        pixels = CulvertAnimation(Config()).render(f, .064)
        rotated = CulvertAnimation(Config(spectrum_rotation=180)).render(f, .064)
        for i in range(32):
            self.assertEqual(pixels[i*3:i*3+3], rotated[(31-i)*3:(32-i)*3])
        self.assertEqual(CulvertAnimation(Config(pixel_count=64)).render(f, .064), pixels*2)
        self.assertEqual(CulvertAnimation(Config(pixel_positions=((.5, 0),)*32)).render(f, .064), pixels)
        self.assertEqual(CulvertAnimation(Config(pixel_count=2)).render(f, .064), bytes(6))

    def test_wireless_bars_roundtrip_and_link_loss(self):
        c = Config()
        f = AudioFeatures()
        f.spectrum = tuple(i/7 for i in range(8))
        a = CulvertAnimation(c)
        rx = Receiver(c)
        packet = Transmitter(c, 99).encode(f, a, 0)
        self.assertEqual(SIZE, 51)
        self.assertTrue(rx.accept(rx.leader, packet, 0))
        for sent, received in zip(f.spectrum, rx.features.spectrum):
            self.assertAlmostEqual(sent, received, delta=1/255)
        producer = a.render(f, .064)
        consumer = CulvertAnimation(c).render(rx.features, .064)
        self.assertLessEqual(max(abs(p-q) for p, q in zip(producer, consumer)), 1)
        rx.fade_if_lost(1, 1)
        self.assertLess(max(rx.features.spectrum), 1)
        for _ in range(50):
            rx.fade_if_lost(2, 1)
        self.assertEqual(CulvertAnimation(c).render(rx.features, .064), bytes(96))

    def test_configuration_rejects_invalid_bands_and_display_parameters(self):
        for overrides in ({'spectrum_edges': (0,)*9}, {'spectrum_edges': (45, 8000)},
                          {'spectrum_edges': (45, 50, 180, 350, 700, 1400, 2800, 5000, 8000)},
                          {'spectrum_rotation': 90}, {'spectrum_curve': 0}, {'spectrum_gain': 0}):
            with self.assertRaises(ValueError):
                Config(**overrides)
