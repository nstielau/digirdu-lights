"""Health confirmation and complete application import isolation."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch,mock_open
from types import SimpleNamespace
from audio_features import AudioFeatures
from ota_bootstrap import Health,TrialReady,main

class RecoveryBootTests(unittest.TestCase):
    def test_new_rollback_skips_network_but_later_boot_reports(self):
        class AppRunning(BaseException):
            pass
        for recovered in (True,False):
            store=Mock()
            store.state={'generation':5,'trial':None,'outcome':'rolled_back'}
            def select():
                if recovered:store.state['generation']+=1
                return None
            store.select.side_effect=select
            app=Mock();app.main.side_effect=AppRunning
            modules={'board':SimpleNamespace(),
                     'storage':SimpleNamespace(getmount=lambda _:SimpleNamespace(readonly=False)),
                     'microcontroller':SimpleNamespace(watchdog=Mock()),
                     'watchdog':SimpleNamespace(WatchDogMode=SimpleNamespace(RESET=1))}
            with patch.dict(sys.modules,modules), \
                 patch('ota_bootstrap.os.getenv',return_value='1'), \
                 patch('ota_bootstrap.settings',return_value={}), \
                 patch('ota_bootstrap.UpdateStore',return_value=store), \
                 patch('ota_bootstrap.nvm_flag',return_value=False), \
                 patch('ota_bootstrap.open',mock_open(read_data='APP_VERSION="1.0.1"')), \
                 patch('ota_bootstrap.load_app',return_value=(app,'1.0.1')), \
                 patch('ota_bootstrap.network',return_value=False) as network:
                with self.assertRaises(AppRunning):main()
                self.assertEqual(network.call_count,0 if recovered else 1)

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
