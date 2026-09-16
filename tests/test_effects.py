"""Human controls and distinct, bounded effects."""

import unittest

from effects import DebouncedButton, EFFECT_NAMES, effect_indicator_pixels, FEATHERWING_PORTRAIT
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

    def test_default_has_clear_volume_contrast_despite_reverberant_tail(self):
        f = AudioFeatures()
        f.drone = .15
        f.decay = .8  # A previous loud note must not hide a fresh change.
        f.volume = .05
        quiet = CulvertAnimation(Config()).render(f, .064)
        f.volume = .8
        loud = CulvertAnimation(Config()).render(f, .064)
        self.assertGreater(sum(loud), 3 * sum(quiet))
        self.assertLessEqual(max(loud), 38)

    def test_default_attack_is_visible_across_wing_and_releases(self):
        a = CulvertAnimation(Config())
        f = AudioFeatures()
        self.assertEqual(a.render(f, .064), bytes(96))
        f.attackEvent = True
        f.attack = .8
        hit = a.render(f, .064)
        self.assertTrue(all(max(hit[i:i+3]) >= 20 for i in range(0, 96, 3)))
        f.attackEvent = False
        f.attack = 0
        for _ in range(12):
            released = a.render(f, .064)
        self.assertLess(sum(released), .35 * sum(hit))
        self.assertLessEqual(max(hit), 38)

    def test_default_flash_respects_wireless_event_age(self):
        f = AudioFeatures()
        f.attackEvent = True
        f.attack = .8
        fresh = CulvertAnimation(Config()).render(f, .064)
        f.attackAge = .4
        late = CulvertAnimation(Config()).render(f, .064)
        self.assertLess(sum(late), .4 * sum(fresh))

    def test_indicator_number_two_matches_factory_wiring_on_black(self):
        pixels = effect_indicator_pixels(1, Config())
        # These physical indices are the digit 2 in portrait on progressive 8x4 wiring.
        expected = {7, 15, 23, 22, 21, 4, 12, 20, 3, 2, 1, 9, 17}
        actual = {i for i in range(32) if any(pixels[i*3:i*3+3])}
        self.assertEqual(actual, expected)
        self.assertEqual(len(pixels), 96)
        self.assertEqual(pixels[7*3:7*3+3], bytes((7, 38, 0)))  # Orange, GRB.

    def test_indicators_are_distinct_bounded_and_rotate(self):
        outputs = [effect_indicator_pixels(i, Config()) for i in range(4)]
        self.assertEqual(len(set(outputs)), 4)
        for effect, pixels in enumerate(outputs):
            self.assertLessEqual(max(pixels), 38)
            rotated = effect_indicator_pixels(effect, Config(effect_indicator_rotation=180))
            for logical in range(32):
                i = FEATHERWING_PORTRAIT[logical] * 3
                j = FEATHERWING_PORTRAIT[31-logical] * 3
                self.assertEqual(pixels[i:i+3], rotated[j:j+3])

    def test_indicator_expires_despite_repeated_radio_state(self):
        c = Config(effect_indicator_s=.5)
        a = CulvertAnimation(c)
        f = AudioFeatures()
        a.set_effect(1)
        glyph = a.render(f, .1)
        self.assertTrue(any(glyph))  # Indicator is visible even in silence.
        for _ in range(6):
            a.set_effect(1)  # Repeated feature packets must not restart it.
            result = a.render(f, .1)
        self.assertEqual(a.indicator_remaining, 0)
        self.assertEqual(result, bytes(96))

    def test_indicator_hides_scene_but_does_not_pause_it(self):
        a = CulvertAnimation(Config(effect_indicator_s=.5))
        f = AudioFeatures()
        f.volume = f.drone = 1
        f.attackEvent = True
        f.attack = .8
        a.set_effect(1)
        glyph = a.render(f, .1)
        self.assertEqual(glyph, effect_indicator_pixels(1, a.c))
        f.attackEvent = False
        for _ in range(6):
            scene = a.render(f, .1)
        self.assertAlmostEqual(a.time, .7)
        self.assertGreater(a.pulses[0][0], .5)
        self.assertTrue(any(scene))
        self.assertNotEqual(scene, glyph)
        a.set_effect(2)
        a.set_effect(3)
        self.assertEqual(a.render(f, .1), effect_indicator_pixels(3, a.c))
        a.set_effect(0)  # Wrap back to display number 1.
        self.assertEqual(a.render(f, .1), effect_indicator_pixels(0, a.c))

    def test_indicator_layout_overrides_and_non_wing_layout(self):
        one = effect_indicator_pixels(0, Config())
        self.assertEqual(effect_indicator_pixels(0, Config(pixel_count=64)), one * 2)
        self.assertIsNone(effect_indicator_pixels(0, Config(pixel_count=2)))
        self.assertIsNone(effect_indicator_pixels(0, Config(effect_indicator_enabled=False)))
        remapped = effect_indicator_pixels(0, Config(effect_indicator_map=tuple(range(32))))
        self.assertEqual(remapped[3:6], bytes((0, 0, 38)))
        for overrides in ({"effect_indicator_rotation": 90},
                          {"effect_indicator_map": (0,)*32}, {"effect_indicator_s": 0}):
            with self.assertRaises(ValueError):
                Config(**overrides)


if __name__ == "__main__":
    unittest.main()
