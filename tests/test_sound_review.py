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
    load_labels,
    read_wav_hops,
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
        current.growl = 0.6
        current.vocal = 0.7
        current.attack = 0.8
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
                "growl",
                "vocal",
                "transient_strength",
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


if __name__ == "__main__":
    unittest.main()
