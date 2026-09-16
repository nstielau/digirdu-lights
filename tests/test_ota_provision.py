import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from ota_provision import render_settings
import tomllib
class SettingsTests(unittest.TestCase):
    def test_preserves_unrelated_settings_and_tables(self):
        c={'api':'https://digirdu-lights.firebaseapp.com/device-api/v1','id':'1234','token':'a'*64}
        previous='NAME = "left wing"\nOTA_ENABLED = "0"\n[other]\nvalue = 3\n'
        value=tomllib.loads(render_settings(previous,c,True).decode())
        self.assertEqual(value['NAME'],'left wing');self.assertEqual(value['other'],{'value':3})
        self.assertEqual(value['OTA_ENABLED'],'1');self.assertEqual(value['OTA_DEVICE_TOKEN'],c['token'])
