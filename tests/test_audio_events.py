"""Tests for deterministic semantic audio event extraction."""

from types import SimpleNamespace
import unittest

from audio_events import DroneEventConfig, SemanticEventDetector


def frame(drone=0.0, vocal=0.0, attack=0.0, yell=False, transient=False):
    return SimpleNamespace(
        drone=drone,
        vocal=vocal,
        attack=attack,
        yellEvent=yell,
        attackEvent=transient,
    )


class AudioEventTests(unittest.TestCase):
    def test_drone_hold_emits_start_and_stop_at_crossing_frames(self):
        config = DroneEventConfig(
            on_threshold=0.6,
            off_threshold=0.3,
            start_hold_s=0.10,
            stop_hold_s=0.20,
        )
        detector = SemanticEventDetector(config)
        times = (0, 100, 160, 300, 350, 430, 560)
        levels = (0.0, 0.7, 0.7, 0.7, 0.25, 0.25, 0.25)

        events = []
        for time_ms, level in zip(times, levels):
            events.extend(detector.update(frame(drone=level), time_ms))

        self.assertEqual(
            events,
            [
                {"type": "drone_start", "time_ms": 160, "confidence": 0.7},
                {"type": "drone_stop", "time_ms": 560, "confidence": 0.25},
            ],
        )

    def test_edge_flags_emit_yell_before_transient_with_clamped_confidence(self):
        detector = SemanticEventDetector()

        events = detector.update(
            frame(vocal=0.8, attack=0.7, yell=True, transient=True),
            512,
        )

        self.assertEqual(
            events,
            (
                {"type": "yell", "time_ms": 512, "confidence": 0.8},
                {"type": "transient", "time_ms": 512, "confidence": 0.7},
            ),
        )

    def test_confidences_are_clamped(self):
        detector = SemanticEventDetector()

        events = detector.update(
            frame(vocal=1.5, attack=-0.5, yell=True, transient=True),
            0,
        )

        self.assertEqual(events[0]["confidence"], 1.0)
        self.assertEqual(events[1]["confidence"], 0.0)

    def test_threshold_values_do_not_chatter(self):
        config = DroneEventConfig(start_hold_s=0.10, stop_hold_s=0.20)
        detector = SemanticEventDetector(config)
        events = []
        for time_ms, level in ((0, 0.45), (100, 0.45), (200, 0.45),
                               (300, 0.25), (400, 0.25), (500, 0.25), (600, 0.25)):
            events.extend(detector.update(frame(drone=level), time_ms))

        self.assertEqual(events, [])

    def test_non_increasing_update_timestamp_is_rejected(self):
        detector = SemanticEventDetector()
        detector.update(frame(), 100)

        with self.assertRaises(ValueError):
            detector.update(frame(), 100)
        with self.assertRaises(ValueError):
            detector.update(frame(), 99)

    def test_finish_closes_active_drone_once(self):
        config = DroneEventConfig(start_hold_s=0.10, stop_hold_s=0.20)
        detector = SemanticEventDetector(config)
        detector.update(frame(drone=0.8), 0)
        start = detector.update(frame(drone=0.8), 100)
        self.assertEqual(start[0]["type"], "drone_start")

        self.assertEqual(
            detector.finish(250),
            ({"type": "drone_stop", "time_ms": 250, "confidence": 0.8},),
        )
        self.assertEqual(detector.finish(300), ())

    def test_finish_allows_the_final_update_timestamp(self):
        config = DroneEventConfig(start_hold_s=0.10, stop_hold_s=0.20)
        detector = SemanticEventDetector(config)
        detector.update(frame(drone=0.8), 0)
        detector.update(frame(drone=0.8), 100)

        self.assertEqual(
            detector.finish(100),
            ({"type": "drone_stop", "time_ms": 100, "confidence": 0.8},),
        )

    def test_invalid_drone_config_is_rejected(self):
        for kwargs in (
            {"on_threshold": 0.2, "off_threshold": 0.2},
            {"on_threshold": 0.1, "off_threshold": 0.2},
            {"start_hold_s": 0},
            {"stop_hold_s": -0.1},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    DroneEventConfig(**kwargs)


if __name__ == "__main__":
    unittest.main()
