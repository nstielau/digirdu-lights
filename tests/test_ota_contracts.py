import copy
import unittest
from test_ota import release
from ota_manifest import validate, bundle_digest, sha256, safe_app_name

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

    def test_legacy_contract_and_modern_base_floor(self):
        self.assertEqual(validate(release()[0])['schema'], 1)
        self.assertEqual(validate(self.modern(), S3, 'producer')['schema'], 2)
        for change in (lambda m:m.update(schema=1), lambda m:m.update(minimum_base='1.0.4'),
                       lambda m:m['files'].remove(next(f for f in m['files'] if f['name']=='lights_app.py'))):
            m = self.modern(); change(m)
            with self.assertRaises(ValueError): validate(m)
        with self.assertRaises(ValueError): validate(release()[0], S3, 'consumer')

    def test_modern_manifest_accepts_safe_assets_targets_and_protocol(self):
        m=self.modern()
        m['boards']=[S3]
        m['roles']=['consumer']
        m['protocol_send']=4
        m['protocol_receive']=[3,4]
        for name in ('telemetry.py','palette.json','intro.bmp'):
            m['files'].append({'name':name,'size':1,'sha256':sha256(b'x')})
        m['sha256']=bundle_digest(m['files'])
        self.assertEqual(validate(m,S3,'consumer'),m)
        with self.assertRaises(ValueError):validate(m,S3,'producer')
        for name in ('boot.json','credentials.py','settings.json','node_config.py',
                     'telemetry_store.py','hardware.bmp','../escape.py','a/b.json'):
            self.assertFalse(safe_app_name(name))
        for name in ('telemetry.py','palette.json','intro.bmp'):
            self.assertTrue(safe_app_name(name))
        for edit in (lambda x:x.update(protocol_send=256),lambda x:x.update(protocol_receive=[]),
                     lambda x:x.update(protocol_receive=[3,3]),lambda x:x.update(boards=[]),
                     lambda x:x.update(roles=['consumer','consumer'])):
            bad=copy.deepcopy(m);edit(bad)
            with self.assertRaises(ValueError):validate(bad)

    def test_modern_bundle_stages_opaque_data_assets(self):
        import tempfile
        from pathlib import Path
        from ota_store import UpdateStore
        m,data=release()
        m=self.modern()
        data.update({'dashboard.py':b'x','device_setup.py':b'x',
                     'palette.json':b'{"hue":42}', 'intro.bmp':b'BM\x00\xff'})
        for name in ('palette.json','intro.bmp'):
            m['files'].append({'name':name,'size':len(data[name]),'sha256':sha256(data[name])})
        m['sha256']=bundle_digest(m['files'])
        with tempfile.TemporaryDirectory() as root:
            store=UpdateStore(root,sync=lambda:None)
            self.assertTrue(store.stage(m,lambda release,f,consume:consume([data[f['name']]])))
            selected=store.select()
            for name in ('palette.json','intro.bmp'):
                self.assertEqual((Path(store.path(selected))/name).read_bytes(),data[name])

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
