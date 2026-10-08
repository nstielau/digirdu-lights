"""Build the authenticated sound-review recording library for Firebase."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.record_fixture import validate_wav
from tools.sound_review import build_artifacts, load_labels, write_json


RECORDING_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CATALOG_FIELDS = frozenset(("id", "name", "audio", "labels"))


def validate_recording_id(value):
    if not isinstance(value, str) or not RECORDING_ID.fullmatch(value):
        raise ValueError("Recording id must be lowercase URL-safe words")
    return value


def _source_filename(value, field):
    if (
        not isinstance(value, str)
        or not value
        or Path(value).name != value
        or "/" in value
        or "\\" in value
    ):
        raise ValueError(f"Recording {field} must be a filename")
    return value


def load_recording_catalog(catalog_path):
    catalog_path = Path(catalog_path)
    document = json.loads(catalog_path.read_text())
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "recordings",
    }:
        raise ValueError("Recording catalog has invalid fields")
    if document["schema_version"] != 1 or not isinstance(
        document["recordings"], list
    ):
        raise ValueError("Recording catalog has invalid schema")
    normalized = []
    seen = set()
    for entry in document["recordings"]:
        if not isinstance(entry, dict) or set(entry) != CATALOG_FIELDS:
            raise ValueError("Recording entry has invalid fields")
        recording_id = validate_recording_id(entry["id"])
        if recording_id in seen:
            raise ValueError(f"Duplicate recording id: {recording_id}")
        seen.add(recording_id)
        if not isinstance(entry["name"], str) or not entry["name"].strip():
            raise ValueError("Recording name must be non-empty")
        normalized.append(
            {
                "id": recording_id,
                "name": entry["name"].strip(),
                "audio": _source_filename(entry["audio"], "audio"),
                "labels": _source_filename(entry["labels"], "labels"),
            }
        )
    if not normalized:
        raise ValueError("Recording catalog must contain at least one recording")
    return {"schema_version": 1, "recordings": normalized}


def _replace_directory(staged, output_dir):
    backup = None
    if output_dir.exists():
        backup = Path(
            tempfile.mkdtemp(prefix=f".{output_dir.name}-backup-", dir=output_dir.parent)
        )
        backup.rmdir()
        output_dir.rename(backup)
    try:
        staged.rename(output_dir)
    except Exception:
        if backup is not None and not output_dir.exists():
            backup.rename(output_dir)
        raise
    if backup is not None:
        shutil.rmtree(backup)


def build_review_library(catalog_path, output_dir):
    catalog_path = Path(catalog_path).resolve()
    output_dir = Path(output_dir).resolve()
    catalog = load_recording_catalog(catalog_path)
    source_dir = catalog_path.parent

    validated = []
    for entry in catalog["recordings"]:
        audio_path = source_dir / entry["audio"]
        labels_path = source_dir / entry["labels"]
        if not audio_path.is_file():
            raise ValueError(f"Missing recording audio: {entry['audio']}")
        if not labels_path.is_file():
            raise ValueError(f"Missing recording labels: {entry['labels']}")
        wav = validate_wav(audio_path, expected_duration_s=None)
        duration_ms = round(wav["duration_s"] * 1000)
        labels = load_labels(labels_path, duration_ms, wav["sample_rate_hz"])
        if labels["audio_file"] != audio_path.name:
            raise ValueError("Label audio_file does not match recording audio")
        validated.append((entry, audio_path, labels_path, labels))

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}-staged-", dir=output_dir.parent)
    )
    work = staged / ".analysis"
    runtime_entries = []
    try:
        for entry, audio_path, labels_path, labels in validated:
            paths = build_artifacts(audio_path, labels_path, work / entry["id"])
            bundle = json.loads(Path(paths["review_json"]).read_text())
            bundle.pop("audio_url", None)
            destination = staged / entry["id"]
            destination.mkdir()
            shutil.copyfile(audio_path, destination / "audio.wav")
            write_json(destination / "bundle.json", bundle)
            runtime_entries.append(
                {
                    "id": entry["id"],
                    "name": entry["name"],
                    "duration_ms": bundle["duration_ms"],
                    "label_counts": dict(
                        Counter(label["type"] for label in labels["labels"])
                    ),
                    "event_counts": dict(
                        Counter(event["type"] for event in bundle["events"])
                    ),
                }
            )
        shutil.rmtree(work)
        runtime_catalog = {"schema_version": 1, "recordings": runtime_entries}
        write_json(staged / "catalog.json", runtime_catalog)
        _replace_directory(staged, output_dir)
        return runtime_catalog
    except Exception:
        if staged.exists():
            shutil.rmtree(staged)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    catalog = build_review_library(args.catalog, args.output_dir)
    print(f"review_catalog={args.output_dir / 'catalog.json'}")
    print(f"recordings={len(catalog['recordings'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
