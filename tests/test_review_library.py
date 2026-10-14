"""Tests for the tracked, deployable sound-review recording library."""

import array
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import wave

from tools.review_library import (
    build_review_library,
    load_recording_catalog,
    validate_recording_id,
)


def write_wav(path, seconds=1):
    samples = array.array("h", [0] * (16000 * seconds))
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(16000)
        destination.writeframes(samples.tobytes())


def write_labels(path, audio_file, labels=None):
    path.write_text(
        json.dumps(
            {
                "audio_file": audio_file,
                "sample_rate_hz": 16000,
                "labels": labels
                if labels is not None
                else [{"type": "drone", "start_ms": 100, "end_ms": 900}],
            }
        )
        + "\n"
    )


class ReviewLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = self.root / "recordings"
        self.sources.mkdir()
        for recording_id in ("take-one", "take-two"):
            write_wav(self.sources / f"{recording_id}.wav")
            write_labels(
                self.sources / f"{recording_id}.labels.json",
                f"{recording_id}.wav",
            )
        self.catalog = self.sources / "catalog.json"
        self.write_catalog(("take-one", "take-two"))

    def write_catalog(self, recording_ids):
        self.catalog.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "recordings": [
                        {
                            "id": recording_id,
                            "name": recording_id.replace("-", " ").title(),
                            "audio": f"{recording_id}.wav",
                            "labels": f"{recording_id}.labels.json",
                        }
                        for recording_id in recording_ids
                    ],
                }
            )
            + "\n"
        )

    def test_recording_ids_are_url_safe(self):
        self.assertEqual(validate_recording_id("high-yell-01"), "high-yell-01")
        for invalid in ("", "../take", "Take One", "a/b"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_recording_id(invalid)

    def test_review_library_cli_is_executable_from_repository_root(self):
        root = Path(__file__).parent.parent
        result = subprocess.run(
            [sys.executable, "tools/review_library.py", "--help"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_web_test_rebuilds_review_library_before_deployment(self):
        root = Path(__file__).parent.parent
        makefile = (root / "Makefile").read_text()
        target = re.search(r"^web-test:([^\n]*)$", makefile, re.MULTILINE)
        self.assertIsNotNone(target)
        self.assertIn("review-library", target.group(1).split())

    def test_build_is_ordered_deterministic_and_removes_stale_entries(self):
        output = self.root / "review-data"
        first_catalog = build_review_library(self.catalog, output)
        self.assertEqual(
            [entry["id"] for entry in first_catalog["recordings"]],
            ["take-one", "take-two"],
        )
        self.assertEqual(first_catalog["recordings"][0]["duration_ms"], 1000)
        self.assertEqual(first_catalog["recordings"][0]["label_counts"], {"drone": 1})
        self.assertIsInstance(first_catalog["recordings"][0]["event_counts"], dict)
        for recording_id in ("take-one", "take-two"):
            self.assertEqual(
                {path.name for path in (output / recording_id).iterdir()},
                {"audio.wav", "bundle.json"},
            )
            bundle = json.loads((output / recording_id / "bundle.json").read_text())
            self.assertNotIn("audio_url", bundle)
            self.assertEqual(bundle["schema_version"], 2)
            self.assertEqual(
                bundle["spectrogram"]["columns"], len(bundle["waveform"])
            )
            self.assertEqual(bundle["spectrogram"]["rows"], 64)

        comparison = self.root / "comparison"
        build_review_library(self.catalog, comparison)
        self.assertEqual(
            {
                path.relative_to(output): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            },
            {
                path.relative_to(comparison): path.read_bytes()
                for path in comparison.rglob("*")
                if path.is_file()
            },
        )

        self.write_catalog(("take-one",))
        build_review_library(self.catalog, output)
        self.assertFalse((output / "take-two").exists())

    def test_catalog_and_sources_are_strictly_validated(self):
        document = json.loads(self.catalog.read_text())
        document["recordings"].append(dict(document["recordings"][0]))
        self.catalog.write_text(json.dumps(document))
        with self.assertRaisesRegex(ValueError, "Duplicate recording id"):
            load_recording_catalog(self.catalog)

        self.write_catalog(("missing",))
        with self.assertRaisesRegex(ValueError, "Missing recording audio"):
            build_review_library(self.catalog, self.root / "missing-output")

        self.write_catalog(("take-one",))
        write_labels(self.sources / "take-one.labels.json", "another.wav")
        with self.assertRaisesRegex(ValueError, "audio_file"):
            build_review_library(self.catalog, self.root / "mismatch-output")

        write_labels(
            self.sources / "take-one.labels.json",
            "take-one.wav",
            [{"type": "drone", "start_ms": 100, "end_ms": 1001}],
        )
        with self.assertRaisesRegex(ValueError, "outside audio duration"):
            build_review_library(self.catalog, self.root / "outside-output")


if __name__ == "__main__":
    unittest.main()
