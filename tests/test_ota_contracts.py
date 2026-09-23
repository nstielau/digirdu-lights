import copy
import unittest
from test_ota import release
from ota_manifest import validate, bundle_digest, sha256

S3 = 'adafruit_feather_esp32s3_reverse_tft'

class ContractsTests(unittest.TestCase):
    def modern(self):
        m, data = release()
        m['schema'] = 2
        m['minimum_base'] = '1.1.0'
        m['boards'].append(S3)
        for name in ('dashboard.py','device_setup.py'):
            m['files'].append({'name':name, 'size':1, 'sha256':sha256(b'x')})
        m['sha256'] = bundle_digest(m['files'])
        return m

    def test_both_exact_contracts_and_base_floor(self):
        self.assertEqual(validate(release()[0])['schema'], 1)
        self.assertEqual(validate(self.modern(), S3, 'producer')['schema'], 2)
        for change in (lambda m:m.update(schema=1), lambda m:m.update(minimum_base='1.0.4'),
                       lambda m:m['boards'].pop(), lambda m:m['files'].pop()):
            m = self.modern(); change(m)
            with self.assertRaises(ValueError): validate(m)
        with self.assertRaises(ValueError): validate(release()[0], S3, 'consumer')

    def test_legacy_confirmed_slot_survives_new_candidate_rollback(self):
        import tempfile
        from ota_store import UpdateStore
        with tempfile.TemporaryDirectory() as root:
            old, data = release()
            store = UpdateStore(root, sync=lambda:None)
            store.stage(old, lambda m,f,consume:consume([data[f['name']]]))
            store.select(); store.confirm()
            new = self.modern(); new['sequence'] = 2
            data.update({'dashboard.py':b'x','device_setup.py':b'x'})
            store.stage(new, lambda m,f,consume:consume([data[f['name']]]))
            self.assertEqual(store.select()['manifest']['schema'], 2)
            reboot = UpdateStore(root, sync=lambda:None)
            self.assertEqual(reboot.select()['manifest']['schema'], 1)
