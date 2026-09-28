"""Current-boot OTA display metadata must never authorize firmware."""
import importlib.util
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
import sys


class StatusTests(unittest.TestCase):
    def status(self):
        self.assertIsNotNone(importlib.util.find_spec('ota_status'), 'base status module missing')
        import ota_status
        ota_status.reset()
        return ota_status

    def test_valid_block_and_success_clear_previous_warning(self):
        s=self.status()
        payload={'schema':1,'state':'checked','blocked':{'version':'2.0.0','minimum_base':'2.0.0'}}
        s.accept({'update_status':payload},'1.1.0')
        self.assertEqual(s.snapshot(),payload)
        payload['blocked']['version']='9.0.0'
        self.assertEqual(s.snapshot()['blocked']['version'],'2.0.0')
        view=s.snapshot();view['blocked']['version']='8.0.0'
        self.assertEqual(s.snapshot()['blocked']['version'],'2.0.0')
        s.accept({'update_status':{'schema':1,'state':'checked','blocked':None}},'1.1.0')
        self.assertIsNone(s.snapshot()['blocked'])
        s.reset('maintenance');self.assertEqual(s.snapshot()['state'],'maintenance')

    def test_missing_malformed_and_non_newer_blocks_are_unknown(self):
        s=self.status()
        valid={'schema':1,'state':'checked','blocked':{'version':'2.0.0','minimum_base':'2.0.0'}}
        candidates=[None,{}, {'update_status':[]},
                    {'update_status':dict(valid,schema=True)},
                    {'update_status':dict(valid,extra='ignored?')},
                    {'update_status':dict(valid,state='paused')},
                    {'update_status':dict(valid,blocked={'version':'1.1.0','minimum_base':'2.0.0'})},
                    {'update_status':dict(valid,blocked={'version':'2.0.0','minimum_base':'1.1.0'})},
                    {'update_status':dict(valid,blocked={'version':'2.00.0','minimum_base':'2.0.0'})}]
        for candidate in candidates:
            s.accept(candidate,'1.1.0')
            self.assertEqual(s.snapshot()['state'],'unavailable',candidate)
            self.assertIsNone(s.snapshot()['blocked'])

    def test_disabled_paused_no_release_and_reset_do_not_claim_current(self):
        s=self.status()
        self.assertEqual(s.snapshot()['state'],'not_checked')
        for state in ('disabled','maintenance','checking','unavailable'):
            s.reset(state);self.assertEqual(s.snapshot()['state'],state)
        for state in ('paused','no_release'):
            s.accept({'update_status':{'schema':1,'state':state,'blocked':None}},'1.1.0')
            self.assertEqual(s.snapshot()['state'],state)

    def test_unavailable_reason_is_bounded_and_kept_separate_from_state(self):
        s=self.status()
        s.reset('unavailable','HTTP 400')
        self.assertEqual(s.snapshot(),{'schema':1,'state':'unavailable',
                                       'blocked':None,'reason':'HTTP 400'})

    def test_failure_reason_classifies_wifi_timeout_and_http_status(self):
        s=self.status()
        self.assertEqual(s.failure_reason(OSError('offline'),'wifi'),'Wi-Fi')
        self.assertEqual(s.failure_reason(OSError('http_deadline'),'http'),'timeout')
        self.assertEqual(s.failure_reason(TimeoutError(),'wifi'),'timeout')
        self.assertEqual(s.failure_reason(OSError('http_status_400'),'http'),'HTTP 400')
        self.assertEqual(s.failure_reason(ValueError('invalid_headers'),'http'),'HTTP')

    def test_network_retains_status_and_failure_clears_it_without_staging(self):
        s=self.status()
        import ota_bootstrap as boot
        for failure in (False,True):
            radio=Mock();client=Mock();store=Mock(state={'report_pending':False})
            client.request.return_value={'manifest':None,'update_status':{
                'schema':1,'state':'checked','blocked':{'version':'2.0.0','minimum_base':'2.0.0'}}}
            if failure:radio.connect.side_effect=OSError('offline')
            modules={'wifi':SimpleNamespace(radio=radio),'socketpool':SimpleNamespace(SocketPool=Mock())}
            with patch.dict(sys.modules,modules),patch.object(boot,'OTAIndicator'), \
                 patch.object(boot,'DeviceHTTP',return_value=client),patch.object(boot,'report_body',return_value={}), \
                 patch.object(boot,'nvm_flag'),patch.object(boot.time,'sleep'):
                boot.network(store,{'ssid':'test','id':'id','token':'secret','api':'test'},'1.1.0','s',1,Mock())
            self.assertEqual(s.snapshot()['state'],'unavailable' if failure else 'checked')
            store.stage.assert_not_called()

    def test_incompatible_manifest_still_rejected_before_staging(self):
        s=self.status()
        import ota_bootstrap as boot
        from tools.bundle import application, manifest
        m=manifest(application(),'a'*40);m.update(minimum_base='9.0.0',sequence=99)
        store=Mock(state={'report_pending':False});client=Mock()
        client.request.return_value={'manifest':m,'update_status':{'schema':1,'state':'checked','blocked':None}}
        modules={'wifi':SimpleNamespace(radio=Mock()),'socketpool':SimpleNamespace(SocketPool=Mock())}
        with patch.dict(sys.modules,modules),patch.object(boot,'OTAIndicator'), \
             patch.object(boot,'DeviceHTTP',return_value=client), \
             patch.object(boot,'report_body',return_value={'circuitpython':'10.3.1'}), \
             patch.object(boot,'nvm_flag'),patch.object(boot.time,'sleep'):
            self.assertFalse(boot.network(store,{'ssid':'x','id':'x','token':'x','api':'x',
                'board':'adafruit_feather_esp32s3_reverse_tft','role':'consumer'},'1.1.0','s',1,Mock()))
        store.stage.assert_not_called();self.assertEqual(client.request.call_count,1)

    def test_report_only_preserves_snapshot_and_bad_metadata_cannot_block_valid_update(self):
        s=self.status()
        import ota_bootstrap as boot
        from tools.bundle import application,manifest
        m=manifest(application(),'a'*40);m.update(version='1.1.2',sequence=99)
        for report_only in (True,False):
            s.reset('paused')
            store=Mock(state={'report_pending':False});store.stage.return_value=False
            client=Mock();client.request.return_value={'manifest':m,'update_status':'bad metadata'}
            modules={'wifi':SimpleNamespace(radio=Mock()),'socketpool':SimpleNamespace(SocketPool=Mock())}
            with patch.dict(sys.modules,modules),patch.object(boot,'OTAIndicator'), \
                 patch.object(boot,'DeviceHTTP',return_value=client), \
                 patch.object(boot,'report_body',return_value={'circuitpython':'10.3.1'}), \
                 patch.object(boot,'nvm_flag'),patch.object(boot.time,'sleep'):
                boot.network(store,{'ssid':'x','id':'x','token':'x','api':'x',
                    'board':'adafruit_feather_esp32s3_reverse_tft','role':'consumer'},'1.1.0','s',1,Mock(),report_only=report_only)
            if report_only:
                store.stage.assert_not_called();self.assertEqual(s.snapshot()['state'],'paused')
            else:
                store.stage.assert_called_once();self.assertEqual(s.snapshot()['state'],'unavailable')
