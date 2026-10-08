"""Tests for offline review through the producer audio pipeline."""

import array
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from audio_features import AudioFeatures
from config import Config
from tools.sound_review import (
    analyze_wav,
    build_artifacts,
    compare_drone,
    compare_labels,
    group_pixels,
    load_labels,
    read_wav_hops,
    render_effects,
    serialize_features,
)
from tools.record_fixture import validate_wav as validate_fixture_wav


def write_pcm_wav(path, sample_rate_hz, samples):
    path = Path(path)
    little_endian = array.array("h", samples)
    if sys.byteorder != "little":
        little_endian.byteswap()
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(sample_rate_hz)
        destination.writeframes(little_endian.tobytes())
    return path


def fixture_feature_frames():
    """Small serialized feature timeline for deterministic renderer tests."""
    frames = []
    for time_ms in range(0, 1001, 100):
        level = 0.2 if time_ms < 500 else 0.8
        frames.append(
            {
                "time_ms": time_ms,
                "calibrating": False,
                "volume": level,
                "drone": level,
                "harmonics": 0.35,
                "timbre_position": 0.25,
                "growl": 0.15,
                "vocal": 0.1,
                "transient_strength": 0.0,
                "attack_event": False,
                "yell_event": False,
                "attack_age_s": 0.0,
                "yell_age_s": 0.0,
                "decay": level,
                "low_energy": 0.55,
                "mid_energy": 0.3,
                "high_energy": 0.15,
                "spectrum": (level, 0.5, 0.25, 0.1, 0.05, 0.0, 0.0, 0.0),
                "active": level > 0.0,
                "raw_rms": 100.0,
                "dominant_frequency_hz": 93.75,
            }
        )
    return frames


class SoundReviewWavTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.tempdir = Path(self.temporary.name)

    def test_read_wav_hops_uses_complete_1024_sample_frames(self):
        path = write_pcm_wav(
            self.tempdir / "take.wav", 16000, array.array("h", range(2048))
        )

        info, hops = read_wav_hops(path, Config())

        self.assertEqual(info["sample_rate_hz"], 16000)
        self.assertEqual([len(hop) for hop in hops], [1024, 1024])
        self.assertEqual(hops[0], array.array("h", range(1024)))
        self.assertEqual(hops[1], array.array("h", range(1024, 2048)))

    def test_read_wav_hops_rejects_non_integral_hop_count(self):
        path = write_pcm_wav(
            self.tempdir / "take.wav", 16000, array.array("h", range(1025))
        )

        with self.assertRaisesRegex(ValueError, "integral hop count"):
            read_wav_hops(path, Config())

    def test_read_wav_hops_rejects_invalid_wav_format(self):
        path = write_pcm_wav(
            self.tempdir / "take.wav", 8000, array.array("h", range(1024))
        )

        with self.assertRaises(ValueError):
            read_wav_hops(path, Config())

    def test_read_wav_hops_rejects_file_replacement_during_validation(self):
        path = write_pcm_wav(
            self.tempdir / "take.wav", 16000, array.array("h", range(2048))
        )
        replacement = write_pcm_wav(
            self.tempdir / "replacement.wav",
            16000,
            array.array("h", [42]) * 2048,
        )

        def validate_then_replace(*args, **kwargs):
            metadata = validate_fixture_wav(*args, **kwargs)
            os.replace(replacement, path)
            return metadata

        with patch(
            "tools.sound_review.validate_wav", side_effect=validate_then_replace
        ):
            with self.assertRaisesRegex(ValueError, "changed during validation"):
                read_wav_hops(path, Config())

    def test_read_wav_hops_rejects_metadata_changes_during_validation(self):
        path = write_pcm_wav(
            self.tempdir / "take.wav", 16000, array.array("h", range(2048))
        )

        def validate_with_stale_metadata(*args, **kwargs):
            metadata = dict(validate_fixture_wav(*args, **kwargs))
            metadata["frame_count"] = 1024
            return metadata

        with patch(
            "tools.sound_review.validate_wav",
            side_effect=validate_with_stale_metadata,
        ):
            with self.assertRaisesRegex(ValueError, "metadata changed"):
                read_wav_hops(path, Config())

    def test_load_labels_rejects_invalid_range_and_wrong_rate(self):
        path = self.tempdir / "labels.json"
        path.write_text(
            json.dumps(
                {
                    "audio_file": "take.wav",
                    "sample_rate_hz": 8000,
                    "labels": [
                        {"type": "drone", "start_ms": 900, "end_ms": 100}
                    ],
                }
            )
        )

        with self.assertRaises(ValueError):
            load_labels(path, duration_ms=1000, sample_rate_hz=16000)

    def test_load_labels_rejects_invalid_types_and_timestamps(self):
        invalid_labels = (
            {"type": "unknown", "start_ms": 100, "end_ms": 200},
            {"type": [], "start_ms": 100, "end_ms": 200},
            {"type": "drone", "start_ms": 100.5, "end_ms": 200},
            {"type": "drone", "start_ms": True, "end_ms": 200},
            {"type": "drone", "start_ms": -1, "end_ms": 200},
            {"type": "drone", "start_ms": 200, "end_ms": 100},
            {"type": "drone", "start_ms": 100, "end_ms": 1001},
        )
        for label in invalid_labels:
            with self.subTest(label=label):
                path = self.tempdir / "labels.json"
                path.write_text(
                    json.dumps(
                        {
                            "audio_file": "take.wav",
                            "sample_rate_hz": 16000,
                            "labels": [label],
                        }
                    )
                )
                with self.assertRaises(ValueError):
                    load_labels(path, duration_ms=1000, sample_rate_hz=16000)

    def test_load_labels_enforces_range_and_point_grammar(self):
        invalid_labels = (
            {"type": "drone", "start_ms": 100},
            {"type": "yell", "start_ms": 100, "end_ms": 100},
            {"type": "beat", "start_ms": 100, "end_ms": 101},
            {"type": "transient", "start_ms": 100, "end_ms": 200},
        )
        for index, label in enumerate(invalid_labels):
            with self.subTest(label=label):
                path = self.tempdir / f"invalid-grammar-{index}.json"
                path.write_text(
                    json.dumps(
                        {
                            "audio_file": "take.wav",
                            "sample_rate_hz": 16000,
                            "labels": [label],
                        }
                    )
                )
                with self.assertRaises(ValueError):
                    load_labels(path, duration_ms=1000, sample_rate_hz=16000)

        path = self.tempdir / "valid-points.json"
        path.write_text(
            json.dumps(
                {
                    "audio_file": "take.wav",
                    "sample_rate_hz": 16000,
                    "labels": [
                        {"type": "beat", "start_ms": 100},
                        {"type": "transient", "start_ms": 200, "end_ms": 200},
                    ],
                }
            )
        )
        self.assertEqual(
            load_labels(path, duration_ms=1000, sample_rate_hz=16000)["labels"],
            [
                {"type": "beat", "start_ms": 100, "end_ms": 100},
                {"type": "transient", "start_ms": 200, "end_ms": 200},
            ],
        )

    def test_load_labels_rejects_invalid_document_shapes(self):
        invalid_documents = (
            [],
            {"sample_rate_hz": 16000, "labels": []},
            {"audio_file": "", "sample_rate_hz": 16000, "labels": []},
            {"audio_file": "take.wav", "sample_rate_hz": True, "labels": []},
            {"audio_file": "take.wav", "sample_rate_hz": 16000, "labels": {}},
            {
                "audio_file": "take.wav",
                "sample_rate_hz": 16000,
                "labels": ["drone"],
            },
        )
        for index, document in enumerate(invalid_documents):
            with self.subTest(document=document):
                path = self.tempdir / f"labels-{index}.json"
                path.write_text(json.dumps(document))
                with self.assertRaises(ValueError):
                    load_labels(path, duration_ms=1000, sample_rate_hz=16000)

    def test_load_labels_rejects_duplicate_metadata(self):
        path = self.tempdir / "labels.json"
        path.write_text(
            '{"audio_file":"first.wav","audio_file":"second.wav",'
            '"sample_rate_hz":16000,"labels":[]}'
        )

        with self.assertRaises(ValueError):
            load_labels(path, duration_ms=1000, sample_rate_hz=16000)


class SoundReviewAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.tempdir = Path(self.temporary.name)

    def test_analyze_wav_uses_ordered_hop_end_timestamps_and_events(self):
        config = Config()
        frame_count = 10 * config.sample_rate // config.hop_size * config.hop_size
        samples = array.array("h")
        for index in range(frame_count):
            time_s = index / config.sample_rate
            value = 0.0
            if time_s >= 2.0:
                value += 3500 * math.sin(2 * math.pi * 93.75 * time_s)
            if 4.8 <= time_s < 5.2:
                value += 7000 * math.sin(2 * math.pi * 2500 * time_s)
            samples.append(round(value))
        audio_path = write_pcm_wav(
            self.tempdir / "take.wav", config.sample_rate, samples
        )
        duration_ms = round(frame_count * 1000 / config.sample_rate)
        labels_path = self.tempdir / "labels.json"
        labels_path.write_text(
            json.dumps(
                {
                    "audio_file": audio_path.name,
                    "sample_rate_hz": config.sample_rate,
                    "labels": [
                        {"type": "drone", "start_ms": 2000, "end_ms": duration_ms},
                        {"type": "yell", "start_ms": 4800, "end_ms": 5200},
                    ],
                }
            )
        )

        result = analyze_wav(audio_path, labels_path, config, fps=20)

        self.assertEqual(
            [frame["time_ms"] for frame in result["features"]],
            [
                round(index * config.hop_size * 1000 / config.sample_rate)
                for index in range(1, frame_count // config.hop_size + 1)
            ],
        )
        self.assertIn(
            result["events"][0]["type"], {"drone_start", "transient", "yell"}
        )
        self.assertEqual(result["fps"], 20)

    def test_analyze_wav_rejects_labels_for_a_different_audio_file(self):
        config = Config()
        audio_path = write_pcm_wav(
            self.tempdir / "take.wav",
            config.sample_rate,
            array.array("h", [0]) * config.hop_size,
        )
        labels_path = self.tempdir / "labels.json"
        labels_path.write_text(
            json.dumps(
                {
                    "audio_file": "other.wav",
                    "sample_rate_hz": config.sample_rate,
                    "labels": [],
                }
            )
        )

        with self.assertRaises(ValueError):
            analyze_wav(audio_path, labels_path, config)

    def test_analyze_wav_rejects_invalid_fps(self):
        config = Config()
        audio_path = write_pcm_wav(
            self.tempdir / "take.wav",
            config.sample_rate,
            array.array("h", [0]) * config.hop_size,
        )
        labels_path = self.tempdir / "labels.json"
        labels_path.write_text(
            json.dumps(
                {
                    "audio_file": audio_path.name,
                    "sample_rate_hz": config.sample_rate,
                    "labels": [],
                }
            )
        )

        for fps in (True, 0, -1, math.nan, math.inf, -math.inf):
            with self.subTest(fps=fps):
                with self.assertRaises(ValueError):
                    analyze_wav(audio_path, labels_path, config, fps=fps)

    def test_serialize_features_is_normalized_finite_and_non_mutating(self):
        current = AudioFeatures()
        current.volume = 0.4
        current.drone = 0.5
        current.harmonics = 0.35
        current.timbrePosition = 0.25
        current.growl = 0.6
        current.vocal = 0.7
        current.attack = 0.8
        current.attackEvent = True
        current.yellEvent = False
        current.attackAge = 0.02
        current.yellAge = 0.0
        current.decay = 0.9
        current.spectrum = tuple(index / 10 for index in range(8))
        before = dict(vars(current))
        raw = {
            "rms": 123.0,
            "drone_hz": 93.75,
            "bands": (5.0, 3.0, 1.0, 0.5, 0.5),
        }

        serialized = serialize_features(current, raw, 64)

        self.assertEqual(vars(current), before)
        self.assertEqual(
            set(serialized),
            {
                "time_ms",
                "calibrating",
                "volume",
                "drone",
                "harmonics",
                "timbre_position",
                "growl",
                "vocal",
                "transient_strength",
                "attack_event",
                "yell_event",
                "attack_age_s",
                "yell_age_s",
                "decay",
                "low_energy",
                "mid_energy",
                "high_energy",
                "spectrum",
                "active",
                "raw_rms",
                "dominant_frequency_hz",
            },
        )
        for name in (
            "volume",
            "drone",
            "growl",
            "vocal",
            "transient_strength",
            "low_energy",
            "mid_energy",
            "high_energy",
        ):
            self.assertGreaterEqual(serialized[name], 0.0)
            self.assertLessEqual(serialized[name], 1.0)
        self.assertEqual(serialized["low_energy"], 0.5)
        self.assertEqual(serialized["mid_energy"], 0.4)
        self.assertEqual(serialized["high_energy"], 0.1)
        self.assertEqual(serialized["harmonics"], 0.35)
        self.assertEqual(serialized["timbre_position"], 0.25)
        self.assertTrue(serialized["attack_event"])
        self.assertFalse(serialized["yell_event"])
        self.assertEqual(serialized["attack_age_s"], 0.02)
        self.assertEqual(serialized["yell_age_s"], 0.0)
        self.assertEqual(serialized["decay"], 0.9)
        self.assertEqual(
            serialized["spectrum"], tuple(index / 10 for index in range(8))
        )

    def test_serialize_features_rejects_non_finite_values(self):
        current = AudioFeatures()
        raw = {
            "rms": math.inf,
            "drone_hz": 93.75,
            "bands": (0.0, 0.0, 0.0, 0.0, 0.0),
        }

        with self.assertRaises(ValueError):
            serialize_features(current, raw, 64)


class SoundReviewMetricTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.tempdir = Path(self.temporary.name)

    def test_compare_events_reports_one_match_one_false_positive_and_one_miss(self):
        labels = [
            {"type": "yell", "start_ms": 1000, "end_ms": 1200},
            {"type": "yell", "start_ms": 3000, "end_ms": 3200},
        ]
        detected = [
            {"type": "yell", "time_ms": 1100, "confidence": 0.9},
            {"type": "yell", "time_ms": 5000, "confidence": 0.7},
        ]

        report = compare_labels(labels, detected, tolerance_ms=250)

        self.assertEqual(report["yell"]["true_positive"], 1)
        self.assertEqual(report["yell"]["false_positive"], 1)
        self.assertEqual(report["yell"]["false_negative"], 1)
        self.assertAlmostEqual(report["yell"]["precision"], 0.5)
        self.assertAlmostEqual(report["yell"]["recall"], 0.5)
        self.assertAlmostEqual(report["yell"]["f1"], 0.5)
        self.assertEqual(report["yell"]["timing_error_ms"], [100])
        self.assertEqual(report["yell"]["absolute_timing_error_ms"], [100])

    def test_compare_labels_matches_each_detection_only_once(self):
        labels = [
            {"type": "beat", "start_ms": 1000, "end_ms": 1000},
            {"type": "beat", "start_ms": 2000, "end_ms": 2000},
        ]
        detected = [
            {"type": "beat", "time_ms": 1050},
            {"type": "beat", "time_ms": 2050},
            {"type": "beat", "time_ms": 2100},
        ]

        report = compare_labels(labels, detected, tolerance_ms=100)

        self.assertEqual(report["beat"]["true_positive"], 2)
        self.assertEqual(report["beat"]["false_positive"], 1)
        self.assertEqual(report["beat"]["false_negative"], 0)
        self.assertEqual(report["beat"]["unmatched_labels"], [])
        self.assertEqual(report["beat"]["unmatched_events"], [{"type": "beat", "time_ms": 2100}])

    def test_compare_labels_maximizes_matches_for_overlapping_ranges(self):
        labels = [
            {"type": "yell", "start_ms": 1000, "end_ms": 3000},
            {"type": "yell", "start_ms": 2000, "end_ms": 2050},
        ]
        detected = [
            {"type": "yell", "time_ms": 1800},
            {"type": "yell", "time_ms": 2500},
        ]

        report = compare_labels(labels, detected, tolerance_ms=250)

        self.assertEqual(report["yell"]["true_positive"], 2)
        self.assertEqual(report["yell"]["false_positive"], 0)
        self.assertEqual(report["yell"]["false_negative"], 0)
        self.assertEqual(report["yell"]["timing_error_ms"], [1500, -200])

    def test_compare_drone_reports_bounds_and_time_errors(self):
        report = compare_drone(
            {"start_ms": 2000, "end_ms": 8000},
            [
                {"type": "drone_start", "time_ms": 2200},
                {"type": "drone_stop", "time_ms": 7600},
            ],
            duration_ms=10000,
        )

        self.assertEqual(report["start_error_ms"], 200)
        self.assertEqual(report["stop_error_ms"], -400)
        self.assertAlmostEqual(report["intersection_over_union"], 5400 / 6000)
        self.assertEqual(report["false_active_ms"], 0)
        self.assertEqual(report["false_inactive_ms"], 600)

    def test_compare_drone_scores_disjoint_detected_spans_as_a_union(self):
        report = compare_drone(
            {"start_ms": 2000, "end_ms": 8000},
            [
                {"type": "drone_start", "time_ms": 1000},
                {"type": "drone_stop", "time_ms": 3000},
                {"type": "drone_start", "time_ms": 5000},
                {"type": "drone_stop", "time_ms": 6000},
            ],
            duration_ms=10000,
        )

        self.assertEqual(report["start_error_ms"], -1000)
        self.assertEqual(report["stop_error_ms"], -2000)
        self.assertAlmostEqual(report["intersection_over_union"], 2 / 7)
        self.assertEqual(report["false_active_ms"], 1000)
        self.assertEqual(report["false_inactive_ms"], 4000)

    def test_compare_drone_accepts_repeated_human_spans_without_changing_report_shape(self):
        report = compare_drone(
            [
                {"start_ms": 1000, "end_ms": 2000},
                {"start_ms": 4000, "end_ms": 5000},
            ],
            [
                {"type": "drone_start", "time_ms": 1000},
                {"type": "drone_stop", "time_ms": 2000},
                {"type": "drone_start", "time_ms": 4000},
                {"type": "drone_stop", "time_ms": 5000},
            ],
            duration_ms=10000,
        )

        self.assertEqual(
            set(report),
            {
                "start_error_ms",
                "stop_error_ms",
                "intersection_over_union",
                "false_active_ms",
                "false_inactive_ms",
            },
        )
        self.assertEqual(report["intersection_over_union"], 1.0)
        self.assertEqual(report["false_active_ms"], 0)
        self.assertEqual(report["false_inactive_ms"], 0)

    def test_compare_drone_reports_missing_bounds_without_dividing_by_zero(self):
        label = {"start_ms": 2000, "end_ms": 8000}

        for events, expected_start, expected_stop in (
            ([], None, None),
            ([{"type": "drone_start", "time_ms": 2200}], 200, None),
            ([{"type": "drone_stop", "time_ms": 7600}], None, -400),
        ):
            with self.subTest(events=events):
                report = compare_drone(label, events, duration_ms=10000)
                self.assertEqual(report["start_error_ms"], expected_start)
                self.assertEqual(report["stop_error_ms"], expected_stop)
                self.assertEqual(report["intersection_over_union"], 0.0)
                self.assertEqual(report["false_active_ms"], 0)
                self.assertEqual(report["false_inactive_ms"], 6000)

    def test_compare_drone_rejects_zero_length_and_out_of_range_labels(self):
        invalid_labels = (
            {"start_ms": 2000, "end_ms": 2000},
            {"start_ms": 8000, "end_ms": 7000},
            {"start_ms": 0, "end_ms": 10001},
        )
        for label in invalid_labels:
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    compare_drone(label, [], duration_ms=10000)

        with self.assertRaises(ValueError):
            compare_drone(
                {"start_ms": 1000, "end_ms": 2000},
                [
                    {"type": "drone_start", "time_ms": 1500},
                    {"type": "drone_stop", "time_ms": 1500},
                ],
                duration_ms=10000,
            )

    def test_metrics_reject_extreme_finite_values_before_arithmetic(self):
        with self.assertRaises(ValueError):
            compare_drone(
                {"start_ms": 0, "end_ms": 1e308}, [], duration_ms=1e308
            )
        with self.assertRaises(ValueError):
            compare_labels(
                [{"type": "beat", "start_ms": 0, "end_ms": 0}],
                [],
                tolerance_ms=1e308,
            )

    def test_analyze_wav_adds_comparison_without_mutating_labels(self):
        config = Config()
        audio_path = write_pcm_wav(
            self.tempdir / "take.wav",
            config.sample_rate,
            array.array("h", [0]) * config.hop_size,
        )
        labels_path = audio_path.with_suffix(".labels.json")
        original = {
            "audio_file": audio_path.name,
            "sample_rate_hz": config.sample_rate,
            "labels": [],
        }
        labels_path.write_text(json.dumps(original))

        result = analyze_wav(audio_path, labels_path, config)

        self.assertIn("comparison", result)
        self.assertEqual(result["labels"]["labels"], [])
        self.assertEqual(json.loads(labels_path.read_text()), original)


class SoundReviewEffectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.tempdir = Path(self.temporary.name)

    def test_group_pixels_converts_grb_and_averages_equal_groups(self):
        grb = bytes((10, 20, 30, 30, 40, 50, 50, 60, 70, 70, 80, 90))

        self.assertEqual(
            group_pixels(grb, groups=2),
            [[30, 20, 40], [70, 60, 80]],
        )

    def test_render_effects_groups_renderer_output_for_three_nodes(self):
        effects = render_effects(
            fixture_feature_frames(),
            Config(),
            fps=20,
            node_distances_mm=(-5000, 0, 5000),
            virtual_wave_speed_mm_s=10000,
        )

        self.assertEqual(effects["node_distances_mm"], [-5000, 0, 5000])
        self.assertEqual(
            set(effects["effects"]),
            {"Spectrum", "Ember", "Aurora", "Ripple", "Chroma"},
        )
        self.assertEqual(
            len(effects["frames"]["Spectrum"]["0"][0]["pixels_rgb"]), 8
        )
        self.assertTrue(
            all(
                len(pixel) == 3
                for pixel in effects["frames"]["Spectrum"]["0"][0][
                    "pixels_rgb"
                ]
            )
        )

    def test_render_effects_uses_absolute_causal_delay_for_nodes(self):
        effects = render_effects(
            fixture_feature_frames(),
            Config(),
            fps=2,
            node_distances_mm=(-5000, 0, 5000),
            virtual_wave_speed_mm_s=10000,
        )

        midpoint = effects["frames"]["Spectrum"]["1"][1]
        outward = effects["frames"]["Spectrum"]["0"][1]
        opposite = effects["frames"]["Spectrum"]["2"][1]
        self.assertEqual(midpoint["time_ms"], 500)
        self.assertEqual(midpoint["source_time_ms"], 500)
        self.assertEqual(outward["source_time_ms"], 0)
        self.assertEqual(opposite["source_time_ms"], 0)

    def test_render_effects_preserves_semantic_event_bloom_and_pulse(self):
        plain = fixture_feature_frames()
        with_event = fixture_feature_frames()
        with_event[5]["transient_strength"] = 1.0
        with_event[5]["attack_event"] = True
        with_event[5]["attack_age_s"] = 0.0

        plain_output = render_effects(
            plain, Config(), fps=20, node_distances_mm=(0,), virtual_wave_speed_mm_s=10000
        )
        event_output = render_effects(
            with_event,
            Config(),
            fps=20,
            node_distances_mm=(0,),
            virtual_wave_speed_mm_s=10000,
        )

        plain_frames = plain_output["frames"]["Ember"]["0"]
        event_frames = event_output["frames"]["Ember"]["0"]
        self.assertTrue(
            any(
                left["pixels_rgb"] != right["pixels_rgb"]
                for left, right in zip(plain_frames, event_frames)
            )
        )

    def test_artifacts_are_byte_stable_and_manifest_is_hashed_without_clock_data(
        self,
    ):
        config = Config()
        audio_path = write_pcm_wav(
            self.tempdir / "take.wav",
            config.sample_rate,
            array.array("h", [0]) * (config.hop_size * 3),
        )
        labels_path = self.tempdir / "take.labels.json"
        labels_path.write_text(
            json.dumps(
                {
                    "audio_file": audio_path.name,
                    "sample_rate_hz": config.sample_rate,
                    "labels": [],
                }
            )
        )
        output_dir = self.tempdir / "artifacts"

        first = build_artifacts(audio_path, labels_path, output_dir, config)
        first_bytes = {
            name: Path(path).read_bytes()
            for name, path in first.items()
        }
        second = build_artifacts(audio_path, labels_path, output_dir, config)
        second_bytes = {
            name: Path(path).read_bytes()
            for name, path in second.items()
        }

        self.assertEqual(first_bytes, second_bytes)
        manifest = json.loads(Path(first["run_json"]).read_text())
        self.assertEqual(manifest["random_seed"], 0)
        self.assertNotIn("generated_at", manifest)
        self.assertEqual(manifest["analysis"]["feature_fps"], 16000 / 1024)
        self.assertEqual(manifest["effect_engine"]["fps"], 20)
        self.assertEqual(
            set(manifest["source_sha256"]),
            {"audio", "labels"},
        )
        self.assertEqual(
            set(manifest["module_sha256"]),
            {
                "audio_spectrum.py",
                "audio_features.py",
                "audio_events.py",
                "animation.py",
                "effects.py",
                "config.py",
                "tools/sound_review.py",
            },
        )


if __name__ == "__main__":
    unittest.main()
