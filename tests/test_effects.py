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
        f.spectrum = tuple(i / 8 for i in range(8))
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

    def test_indicator_number_two_matches_factory_wiring_on_black(self):
        pixels = effect_indicator_pixels(1, Config())
        # These physical indices are the digit 2 in portrait on progressive 8x4 wiring.
        expected = {7, 15, 23, 22, 21, 4, 12, 20, 3, 2, 1, 9, 17}
        actual = {i for i in range(32) if any(pixels[i*3:i*3+3])}
        self.assertEqual(actual, expected)
        self.assertEqual(len(pixels), 96)
        self.assertEqual(pixels[7*3:7*3+3], bytes((7, 38, 0)))  # Orange, GRB.

    def test_additional_button_cannot_claim_an_existing_input_or_output(self):
        for pin in (0, 5, 6, 9, 38):
            with self.assertRaises(ValueError):
                Config(button_extra_next_gpio=pin)
        with self.assertRaises(ValueError):
            Config(button_previous_gpio=43)
        # A profile may move the main button to 43 if it disables the extra input.
        Config(button_next_gpio=43, button_extra_next_gpio=None)

    def test_indicators_are_distinct_bounded_and_rotate(self):
        outputs = [effect_indicator_pixels(i, Config()) for i in range(len(EFFECT_NAMES))]
        self.assertEqual(len(set(outputs)), len(EFFECT_NAMES))
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

    def test_measured_growl_and_timbre_ranges_change_musical_scenes(self):
        # Representative ranges from the labelled didgeridoo feature capture.
        def scene(effect, growl=.05, timbre=.2):
            a = CulvertAnimation(Config(effect_index=effect))
            f = AudioFeatures()
            f.volume = f.decay = .88
            f.drone = 1
            f.harmonics = .45
            f.growl, f.timbrePosition = growl, timbre
            frames = []
            for _ in range(32):
                frames.extend(a.render(f, .064))
            return frames
        for effect in (1, 2, 3):
            base = scene(effect)
            growl = scene(effect, growl=.21)
            timbre = scene(effect, timbre=.3)
            self.assertGreater(sum(abs(a-b) for a, b in zip(base, growl)) / len(base), 4)
            self.assertGreater(sum(abs(a-b) for a, b in zip(base, timbre)) / len(base), .8)
            self.assertLessEqual(max(base + growl + timbre), 38)

    def test_accents_are_visible_age_correctly_and_fade(self):
        for effect in (1, 2, 3):
            def accent(age):
                a = CulvertAnimation(Config(effect_index=effect))
                f = AudioFeatures()
                f.attackEvent = f.yellEvent = True
                f.attack = f.vocal = 1
                f.attackAge = f.yellAge = age
                pixels = a.render(f, .064)
                return a, f, pixels
            a, f, fresh = accent(0)
            delayed, _, old = accent(.45)
            self.assertTrue(all(any(fresh[i:i+3]) for i in range(0,96,3)))
            self.assertLess(delayed.attack_bloom, a.attack_bloom / 10)
            self.assertLess(sum(old), sum(fresh))
            self.assertLessEqual(max(fresh), 38)
            f.attackEvent = f.yellEvent = False
            f.vocal = 0
            for _ in range(250):
                pixels = a.render(f, .064)
            self.assertEqual(pixels, bytes(96))

    def test_visual_ranges_and_gains_are_bounded(self):
        for overrides in ({'visual_growl_range': (.3, .1)},
                          {'visual_vocal_range': (.2, .2)},
                          {'visual_timbre_range': (-1, 1)},
                          {'attack_bloom_gain': -1}, {'wave_floor': 2}):
            with self.assertRaises(ValueError):
                Config(**overrides)


if __name__ == "__main__":
    unittest.main()
