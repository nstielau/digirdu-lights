"""Check signal processing with controlled silence, DC offset, and sound bursts."""

import math
import unittest

from sound_reactive import RainbowMotion, measure


class SoundTests(unittest.TestCase):
    def test_dc_is_not_sound(self):
        self.assertEqual(measure([1200] * 64, 64), (0, 0, 0))

    def test_known_sine_level(self):
        samples = [int(1000 * math.sin(index * 2 * math.pi / 64)) + 900
                   for index in range(64)]
        rms, peak, span = measure(samples, 64)
        self.assertAlmostEqual(rms, 1000 / math.sqrt(2), delta=1)
        self.assertEqual(peak, 1000)
        self.assertEqual(span, 2000)

    def test_empty_capture_fails(self):
        with self.assertRaises(ValueError):
            measure([], 0)

    def test_noise_floor_ignores_quiet_and_sound_accelerates(self):
        motion = RainbowMotion(10)
        _, quiet_speed, quiet_beat = motion.update(10, 0, 0.016)
        _, loud_speed, loud_beat = motion.update(300, 0.1, 0.016)
        self.assertFalse(quiet_beat)
        self.assertTrue(loud_beat)
        self.assertGreater(loud_speed, quiet_speed * 5)
        _, decaying_speed, _ = motion.update(10, 0.2, 0.1)
        self.assertLess(decaying_speed, loud_speed)
        self.assertGreater(decaying_speed, quiet_speed)

    def test_beat_debounce_and_hue_wrap(self):
        motion = RainbowMotion(10)
        motion.phase = 250
        phase, _, first = motion.update(300, 1.0, 0.016)
        _, _, second = motion.update(500, 1.05, 0.016)
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(motion.beats, 1)
        self.assertGreaterEqual(phase, 0)
        self.assertLess(phase, 256)


if __name__ == "__main__":
    unittest.main()
