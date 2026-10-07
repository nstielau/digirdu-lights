import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

S3 = 'adafruit_feather_esp32s3_reverse_tft'

class StateTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('node_state'), 'saved identity missing')
        import node_state
        self.state = node_state
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'node_state.json')

    def test_precedence_and_explicit_source(self):
        self.assertNotIn('radio_role', self.state.resolve(S3, {}, self.path))
        data = {'schema':1, 'radio_role':'consumer', 'radio_group':2, 'leader_mac':'01:23:45:67:89:ab'}
        self.state.save(data, self.path, writable=True)
        self.assertEqual(self.state.resolve(S3, {}, self.path)['radio_group'], 2)
        self.assertEqual(self.state.resolve(S3, {'radio_role':'producer'}, self.path)['radio_role'], 'producer')
        with self.assertRaisesRegex(ValueError, 'source'):
            self.state.validate({'schema':1,'radio_role':'consumer','radio_group':1})

    def test_corruption_types_and_host_ownership(self):
        for value in ({'schema':True,'radio_role':'producer','radio_group':1},
                      {'schema':1,'radio_role':'producer','radio_group':True},
                      {'schema':1,'radio_role':'producer','radio_group':1,'script':'evil'},
                      {'schema':1,'radio_role':'producer','radio_group':1,'leader_mac':'invalid'}):
            with self.assertRaises(ValueError): self.state.validate(value)
        Path(self.path).write_text('{broken')
        self.assertNotIn('radio_role', self.state.resolve(S3, {}, self.path))
        data = {'schema':1,'radio_role':'producer','radio_group':1}
        with self.assertRaisesRegex(RuntimeError,'host'):
            self.state.save(data, self.path, writable=False)
        with self.assertRaisesRegex(ValueError,'enrolled'):
            self.state.save(data, self.path, writable=True, enrolled_role='consumer')
        self.state.save(data, self.path, writable=True, enrolled_role='producer')
        self.assertEqual(json.loads(Path(self.path).read_text()), data)
        Path(self.path).write_text(' ' * 2049)
        self.assertEqual(self.state.load(self.path), {})
