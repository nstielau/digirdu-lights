"""Host-only immutable source snapshots for USB and GitHub releases."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ota_manifest import APP_FILES, APP_MINIMUM_BASE, BASE_VERSION, BOARDS, bundle_digest, sha256, validate

BASE_FILES = ('ota_manifest.py', 'ota_store.py', 'ota_http.py', 'ota_bootstrap.py',
              'certs/google-roots.pem', 'boot.py', 'code.py')


def application(root=ROOT):
    return {name: (root / name).read_bytes() for name in APP_FILES}


def manifest(contents, commit):
    identity = {}
    exec(contents['app_version.py'], identity)
    files = [{'name': name, 'size': len(contents[name]), 'sha256': sha256(contents[name])} for name in APP_FILES]
    result = {'schema': 1, 'version': identity['APP_VERSION'], 'app_api': identity['APP_API_VERSION'],
              'git_commit': commit, 'minimum_base': APP_MINIMUM_BASE, 'circuitpython': '10.3.1',
              'boards': list(BOARDS), 'roles': ['producer', 'consumer'], 'protocol_send': 3,
              'protocol_receive': [3], 'files': files, 'sha256': bundle_digest(files)}
    validate(result, require_sequence=False)
    return result


def deployment_contents():
    contents = {'node_config.py': (ROOT / 'node_config.py').read_bytes()}
    contents.update({'recovery/' + name: data for name, data in application().items()})
    contents.update({name: (ROOT / name).read_bytes() for name in BASE_FILES})
    return contents
