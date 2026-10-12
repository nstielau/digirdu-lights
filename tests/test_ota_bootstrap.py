"""Health confirmation and complete application import isolation."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch,mock_open
from types import SimpleNamespace
from audio_features import AudioFeatures
from ota_bootstrap import Health,TrialReady,main,OTAIndicator,network,telemetry_on_sleep,app_protocol,app_targets,validate_app_manifest,report_body
from telemetry_store import TelemetryQueue


class OTAIndicatorTests(unittest.TestCase):
    def test_offline_sleep_keeps_batch_for_next_boot(self):
        with tempfile.TemporaryDirectory() as folder:
            queue=TelemetryQueue(folder+'/telemetry',sync=lambda:None)
            radio=Mock();radio.connect.side_effect=OSError('offline')
            cfg={'id':'a'*16,'ssid':'openwireless.org','token':'b'*64,'api':'unused'}
            with patch.dict(sys.modules,{'wifi':SimpleNamespace(radio=radio),'socketpool':SimpleNamespace()}), \
                 patch('ota_bootstrap.TelemetryQueue',return_value=queue),patch('ota_bootstrap.nvm_flag'):
                telemetry_on_sleep({'schema':1},cfg,Mock())
            self.assertEqual(len(queue.pending()),1)
            radio.stop_station.assert_called_once()

    def test_verified_pins_single_cyan_pixel_timing_wrap_and_cleanup(self):
        for board_id, pin_name in (('unexpectedmaker_feathers2','IO38'),
                                   ('adafruit_feather_esp32_v2','D32')):
            clock=[0.0]; frames=[]; pin=Mock(); gpio=object()
            digital=Mock(return_value=pin)
            modules={'board':SimpleNamespace(board_id=board_id,**{pin_name:gpio}),
                     'digitalio':SimpleNamespace(DigitalInOut=digital),
                     'neopixel_write':SimpleNamespace(neopixel_write=lambda p,b:frames.append(bytes(b)))}
            with patch.dict(sys.modules,modules), patch('ota_bootstrap.time.monotonic',side_effect=lambda:clock[0]):
                indicator=OTAIndicator()
                digital.assert_called_once_with(gpio)
                for step in range(33):
                    clock[0]=step*0.5; indicator.update()
                    frame=frames[-1]
                    self.assertEqual(len(frame),96)
                    self.assertEqual(sum(bool(v) for v in frame),2)
                    self.assertEqual(frame[(step%32)*3:(step%32)*3+3],bytes((7,0,7)))
                    count=len(frames);clock[0]+=.1;indicator.update()
                    self.assertEqual(len(frames),count)
                indicator.close()
                self.assertEqual(frames[-1],bytes(96))
                pin.deinit.assert_called_once()

    def test_network_releases_indicator_on_success_and_connection_failure(self):
        for failure in (False,True):
            radio=Mock()
            if failure:radio.connect.side_effect=OSError('no access point')
            progress=Mock();store=Mock();store.state={'report_pending':False}
            client=Mock();client.request.return_value=None
            modules={'wifi':SimpleNamespace(radio=radio),
                     'socketpool':SimpleNamespace(SocketPool=Mock())}
            cfg={'ssid':'openwireless.org','id':'test','token':'unused','api':'unused'}
            with patch.dict(sys.modules,modules), \
                 patch('ota_bootstrap.OTAIndicator',return_value=progress), \
                 patch('ota_bootstrap.DeviceHTTP',return_value=client), \
                 patch('ota_bootstrap.report_body',return_value={}), \
                 patch('ota_bootstrap.upload_telemetry'), \
                 patch('ota_bootstrap.nvm_flag'), patch('ota_bootstrap.time.sleep'):
                self.assertFalse(network(store,cfg,'1.0.6','session',1,Mock()))
                progress.update.assert_called()
                progress.close.assert_called_once()
                radio.stop_station.assert_called_once()

    def test_pin_released_even_if_blackout_write_fails(self):
        indicator=object.__new__(OTAIndicator)
        indicator.pin=Mock();indicator.pixels=bytearray(96)
        indicator.write=Mock(side_effect=OSError('write failure'))
        with self.assertRaises(OSError):indicator.close()
        indicator.pin.deinit.assert_called_once()

    def test_battery_app_requires_base_with_shared_sensor(self):
        from tools.bundle import application,manifest
        self.assertEqual(manifest(application(),'a'*40)['minimum_base'],'1.0.5')

    def test_release_targets_and_protocol_come_from_app_identity(self):
        from tools.bundle import application,manifest,full_fleet_recovery,deployment_contents
        self.assertTrue(full_fleet_recovery(manifest(application(),'a'*40)))
        contents=application()
        contents['app_version.py'] += (b'\nAPP_BOARDS = ("unexpectedmaker_feathers2",)\n'
                                       b'APP_ROLES = ("producer",)\n'
                                       b'PROTOCOL_SEND = 4\nPROTOCOL_RECEIVE = (3, 4)\n')
        release=manifest(contents,'a'*40)
        self.assertFalse(full_fleet_recovery(release))
        with patch('tools.bundle.application',return_value=contents):
            with self.assertRaisesRegex(ValueError,'USB recovery requires'):
                deployment_contents()
        release['sequence']=1
        self.assertEqual(release['boards'],['unexpectedmaker_feathers2'])
        self.assertEqual(release['roles'],['producer'])
        self.assertEqual(release['protocol_send'],4)
        self.assertEqual(release['protocol_receive'],[3,4])
        self.assertEqual(app_protocol({}), (3,[3]))  # Older installed apps.
        self.assertEqual(app_protocol({'PROTOCOL_SEND':4,'PROTOCOL_RECEIVE':(3,4)}),(4,[3,4]))
        self.assertEqual(app_targets({}), (['unexpectedmaker_feathers2','adafruit_feather_esp32_v2'],
                                           ['producer','consumer']))
        self.assertEqual(app_targets({'APP_BOARDS':('unexpectedmaker_feathers2',),
                                      'APP_ROLES':('producer',)}),
                         (['unexpectedmaker_feathers2'],['producer']))
        identity={'APP_BOARDS':('unexpectedmaker_feathers2',),'APP_ROLES':('producer',),
                  'PROTOCOL_SEND':4,'PROTOCOL_RECEIVE':(3,4)}
        self.assertIs(validate_app_manifest(release,identity,'unexpectedmaker_feathers2','producer','10.3.1'),release)
        with self.assertRaisesRegex(ValueError,'manifest_targets_mismatch'):
            validate_app_manifest(release,{**identity,'APP_ROLES':('consumer',)},
                                  'unexpectedmaker_feathers2','producer','10.3.1')
        with self.assertRaisesRegex(ValueError,'manifest_protocol_mismatch'):
            validate_app_manifest(release,{**identity,'PROTOCOL_SEND':3},
                                  'unexpectedmaker_feathers2','producer','10.3.1')
        cfg={'id':'test','board':'unexpectedmaker_feathers2','role':'producer'}
        store=SimpleNamespace(state={'outcome':'current','floor':11,'error':''})
        with patch('ota_bootstrap.read_battery',return_value={'voltage':None,'status':'unsupported'}):
            body=report_body(store,cfg,'1.0.9','session',1,identity={'PROTOCOL_SEND':4,'PROTOCOL_RECEIVE':(3,4)})
        self.assertEqual((body['protocol_send'],body['protocol_receive']),(4,[3,4]))
        for invalid in ({'PROTOCOL_SEND':0},{'PROTOCOL_RECEIVE':()},
                        {'PROTOCOL_RECEIVE':(3,3)},{'PROTOCOL_SEND':True}):
            with self.assertRaises(ValueError):app_protocol(invalid)
        for invalid in ({'APP_BOARDS':()},{'APP_ROLES':('producer','producer')},
                        {'APP_BOARDS':('unknown',)},{'APP_ROLES':'producer'}):
            with self.assertRaises(ValueError):app_targets(invalid)

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
                self.assertEqual(set(app.main.call_args.kwargs),{'health'})

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
