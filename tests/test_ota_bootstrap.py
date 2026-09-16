"""Health confirmation and complete application import isolation."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
from audio_features import AudioFeatures
from ota_bootstrap import Health,TrialReady

class HealthTests(unittest.TestCase):
    def test_trial_requires_completed_calibration_and_sustained_progress(self):
        clock=[0]
        with patch('ota_bootstrap.time.monotonic',side_effect=lambda:clock[0]):
            wd=Mock();h=Health(wd,True);f=AudioFeatures()
            for t in (0,10,20,29):clock[0]=t;h(f,None)
            f.calibrating=False
            clock[0]=30;h(f,None)
            clock[0]=59;h(f,None)
            clock[0]=60
            with self.assertRaises(TrialReady):h(f,None)
            self.assertEqual(wd.feed.call_count,7)
    def test_consumer_health_does_not_require_producer_or_internet(self):
        clock=[0]
        with patch('ota_bootstrap.time.monotonic',side_effect=lambda:clock[0]):
            f=AudioFeatures();f.calibrating=False;h=Health(Mock(),True)
            h(f,None);clock[0]=30
            with self.assertRaises(TrialReady):h(f,None)
    def test_nonfinite_features_rejected(self):
        f=AudioFeatures();f.volume=float('nan')
        with self.assertRaisesRegex(ValueError,'invalid_audio'):Health(Mock(),True)(f,None)
    def test_calibration_cannot_confirm_forever(self):
        clock=[0]
        with patch('ota_bootstrap.time.monotonic',side_effect=lambda:clock[0]):
            h=Health(Mock(),True);clock[0]=121
            with self.assertRaisesRegex(ValueError,'timeout'):h(AudioFeatures(),None)

class ImportTests(unittest.TestCase):
    def test_missing_slot_module_never_falls_back_to_root_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/'app_version.py').write_text('APP_VERSION="1.0.0"\nAPP_API_VERSION=1\n')
            (p/'lights_app.py').write_text('import config\nVALUE=config.SLOT\n')
            command='from ota_bootstrap import load_app; app,_=load_app(%r); print(app.VALUE)'%folder
            failed=subprocess.run([sys.executable,'-c',command],capture_output=True,text=True)
            self.assertNotEqual(failed.returncode,0)
            self.assertIn("No module named 'config'",failed.stderr)
            (p/'config.py').write_text('SLOT="new-slot"\n')
            okay=subprocess.run([sys.executable,'-c',command],capture_output=True,text=True,check=True)
            self.assertEqual(okay.stdout.strip(),'new-slot')
