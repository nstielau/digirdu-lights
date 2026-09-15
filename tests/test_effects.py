"""Human controls and distinct, bounded effects."""

import unittest

from effects import DebouncedButton, EFFECT_NAMES
from config import Config
from audio_features import AudioFeatures
from animation import CulvertAnimation


class EffectTests(unittest.TestCase):
    def test_bounce_hold_and_second_press(self):
        b = DebouncedButton(.04)
        for state, now in ((True, 0), (False, .01), (True, .02), (True, .04)):
            self.assertFalse(b.update(state, now))
        self.assertTrue(b.update(True, .08))
        self.assertFalse(b.update(True, 5))
        self.assertFalse(b.update(False, 6))
        self.assertFalse(b.update(False, 6.1))
        self.assertFalse(b.update(True, 7))
        self.assertTrue(b.update(True, 7.1))

    def test_effect_library_has_distinct_renderings(self):
        f = AudioFeatures()
        f.drone = f.harmonics = f.growl = f.vocal = .7
        f.timbrePosition = .4
        outputs = []
        for effect in range(len(EFFECT_NAMES)):
            a = CulvertAnimation(Config(effect_index=effect))
            output = a.render(f, .064)
            self.assertLessEqual(max(output), int(.15 * 255))
            outputs.append(output)
        self.assertEqual(len(set(outputs)), len(EFFECT_NAMES))

    def test_defaults_are_consumers_and_producer_is_explicit(self):
        self.assertEqual(Config().radio_role, "follower")
        self.assertEqual(Config(radio_role="producer").radio_role, "leader")
        self.assertEqual(Config(radio_role="consumer").radio_role, "follower")
        with self.assertRaises(ValueError):
            Config(button_next_gpio=38)


if __name__ == "__main__":
    unittest.main()
