#!/usr/bin/env python3
"""Hash, verify, and package a numbered hardware release directory."""

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


MANIFEST = "bundle-manifest.json"


def files_in(directory: Path):
    return sorted(
        p for p in directory.rglob("*")
        if p.is_file() and p.name != MANIFEST and ".DS_Store" not in p.parts
    )


def entry(directory: Path, path: Path):
    data = path.read_bytes()
    return {
        "file": path.relative_to(directory).as_posix(),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def verify(directory: Path):
    manifest = json.loads((directory / MANIFEST).read_text())
    expected = sorted(manifest["files"], key=lambda item: item["file"])
    actual = [entry(directory, path) for path in files_in(directory)]
    if actual != expected:
        absent = sorted(set(e["file"] for e in expected) - set(e["file"] for e in actual))
        extra = sorted(set(e["file"] for e in actual) - set(e["file"] for e in expected))
        changed = sorted(e["file"] for e, a in zip(expected, actual) if e != a)
        raise SystemExit(f"release mismatch: missing={absent}, extra={extra}, changed={changed}")
    return [path.relative_to(directory).as_posix() for path in files_in(directory)] + [MANIFEST]


def package(directory: Path, destination: Path):
    names = verify(directory)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for name in names:
            info = ZipInfo(f"{directory.name}/{name}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (directory / name).read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
    with ZipFile(destination) as archive:
        assert archive.testzip() is None
        for name in names:
            assert archive.read(f"{directory.name}/{name}") == (directory / name).read_bytes()
    print(f"{destination} ({len(names)} files, sha256 {hashlib.sha256(destination.read_bytes()).hexdigest()})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("update-manifest", "verify", "package"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, help="ZIP destination for package")
    args = parser.parse_args()
    directory = args.directory.resolve()
    if args.action == "update-manifest":
        path = directory / MANIFEST
        manifest = json.loads(path.read_text()) if path.exists() else {}
        manifest["files"] = [entry(directory, p) for p in files_in(directory)]
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"updated {path} ({len(manifest['files'])} files)")
    elif args.action == "verify":
        print(f"verified {len(verify(directory))} files in {directory}")
    else:
        if not args.output:
            parser.error("--output is required for package")
        package(directory, args.output.resolve())


if __name__ == "__main__":
    main()
