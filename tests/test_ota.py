"""Power-loss, malformed-package and rollback regression tests using real files."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from ota_manifest import APP_FILES, BOARDS, bundle_digest, sha256, validate
from ota_store import UpdateStore


def release(sequence=1, version="1.0.0"):
    data = {name: ("# " + name + "\n").encode() for name in APP_FILES}
    data['app_version.py'] = ('APP_VERSION = "%s"\nAPP_API_VERSION = 1\n' % version).encode()
    files = [{"name": name, "size": len(value), "sha256": sha256(value)} for name, value in data.items()]
    return {"schema": 1, "version": version, "git_commit": "a"*40, "app_api": 1,
            "minimum_base": "1.0.0", "circuitpython": "10.3.1", "boards": list(BOARDS),
            "roles": ["producer", "consumer"], "protocol_send": 3, "protocol_receive": [3],
            "files": files, "sha256": bundle_digest(files), "sequence": sequence}, data


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name + '/ota'
        self.store = self.open()

    def open(self):
        return UpdateStore(self.root, sync=lambda: None)

    def stage(self, sequence=1, corrupt=None):
        m, data = release(sequence, '1.0.%d' % sequence)
        def download(manifest, f, consume):
            value = data[f['name']]
            if corrupt == f['name']:
                value = b'x' * len(value)
            consume([value[:3], value[3:]])
        return self.store.stage(m, download)

    def confirmed(self):
        self.assertTrue(self.stage())
        self.assertEqual(self.open().select()['manifest']['sequence'], 1)
        self.store = self.open()
        self.store.confirm()
        self.store = self.open()
        self.assertEqual(self.store.state['outcome'], 'current')

    def test_first_trial_confirmation_and_slot_alternation(self):
        self.confirmed()
        active_path = self.store.path(self.store.state['active'])
        original = Path(active_path, 'app_version.py').read_bytes()
        self.assertTrue(self.stage(2))
        trial = self.open().select()
        self.assertEqual(trial['slot'], 1)
        self.assertEqual(Path(active_path, 'app_version.py').read_bytes(), original)
        self.store = self.open()
        self.store.confirm()
        self.assertEqual(self.open().select()['manifest']['sequence'], 2)

    def test_reset_during_trial_rolls_back_and_does_not_retry(self):
        self.confirmed()
        self.stage(2)
        self.open().select()  # Persist trial-start BEFORE app import.
        self.store = self.open()
        selected = self.store.select()
        self.assertEqual(selected['manifest']['sequence'], 1)
        self.assertEqual(self.store.state['floor'], 2)
        self.assertEqual(self.store.state['outcome'], 'rolled_back')
        self.assertFalse(self.stage(2))
        self.assertTrue(self.stage(3))

    def test_partial_and_corrupt_downloads_leave_active_untouched(self):
        self.confirmed()
        with self.assertRaisesRegex(ValueError, 'digest'):
            self.stage(2, 'effects.py')
        self.assertEqual(self.open().select()['manifest']['sequence'], 1)
        m, data = release(2)
        def interrupted(manifest, f, consume):
            if f['name'] == 'lights_app.py':
                raise OSError('power loss')
            consume([data[f['name']]])
        with self.assertRaises(OSError):
            self.store.stage(m, interrupted)
        self.assertEqual(self.open().select()['manifest']['sequence'], 1)

    def test_torn_journal_preserves_previous_generation(self):
        self.confirmed()
        generation = self.store.state['generation']
        path = Path(self.root, 'state%d.json' % ((generation + 1) % 2))
        path.write_text('{"body":')
        reopened = self.open()
        self.assertEqual(reopened.state['generation'], generation)
        self.assertEqual(reopened.select()['manifest']['sequence'], 1)

    def test_power_failure_before_journal_commit_cannot_select_candidate(self):
        self.confirmed()
        original_save = self.store.save
        self.store.save = lambda state: (_ for _ in ()).throw(OSError('power cut before commit'))
        with self.assertRaises(OSError):
            self.stage(2)
        self.assertEqual(self.open().select()['manifest']['sequence'], 1)
        self.store.save = original_save

    def test_invalid_slot_path_and_bad_checksum_are_ignored(self):
        self.confirmed()
        state = dict(self.store.state)
        state['active'] = dict(state['active'], slot='../../recovery')
        state['generation'] += 1
        body = json.dumps(state)
        Path(self.root, 'state%d.json' % (state['generation'] % 2)).write_text(
            json.dumps({'body': body, 'sha256': sha256(body.encode())}))
        self.assertEqual(self.open().select()['manifest']['sequence'], 1)

    def test_corrupt_active_falls_back_to_recovery(self):
        self.confirmed()
        Path(self.store.path(self.store.state['active']), 'effects.py').write_bytes(b'bad')
        self.assertIsNone(self.open().select())
        self.assertEqual(self.open().state['error'], 'active_corrupt')

    def test_failure_without_previous_slot_selects_recovery(self):
        self.stage()
        self.open().select()
        self.assertIsNone(self.open().select())
        self.assertEqual(self.open().state['floor'], 1)

    def test_full_storage_does_not_touch_active(self):
        from unittest.mock import patch
        self.confirmed()
        with patch('ota_store.os.statvfs', return_value=(4096, 4096, 0, 0, 0)):
            with self.assertRaisesRegex(OSError, 'insufficient_space'):
                self.stage(2)
        self.assertEqual(self.open().select()['manifest']['sequence'], 1)


class ManifestTests(unittest.TestCase):
    def test_compatibility_and_board_role(self):
        m, _ = release()
        self.assertEqual(validate(m, BOARDS[0], 'producer'), m)
        for args in ((BOARDS[1], 'producer'), ('unknown', 'consumer'), (BOARDS[0], 'unknown')):
            with self.assertRaises(ValueError):
                validate(m, *args)
        with self.assertRaises(ValueError):
            validate(m, BOARDS[0], 'producer', '9.0.0')

    def test_unknown_paths_duplicates_hashes_and_bounds_rejected(self):
        m, _ = release()
        variants = []
        for name, value in (('version', '1.0.01'), ('sequence', True), ('minimum_base', '9.0.0'),
                            ('sha256', 'b'*64), ('protocol_send', 2), ('unexpected', 'x')):
            candidate = copy.deepcopy(m)
            candidate[name] = value
            variants.append(candidate)
        for name in ('../code.py', 'node_config.py', 'settings.toml', '/boot.py', m['files'][1]['name']):
            candidate = copy.deepcopy(m)
            candidate['files'][0]['name'] = name
            candidate['sha256'] = bundle_digest(candidate['files'])
            variants.append(candidate)
        for candidate in variants:
            with self.assertRaises(ValueError):
                validate(candidate)
