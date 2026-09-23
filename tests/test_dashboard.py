import importlib.util
import unittest
from unittest.mock import Mock

class DashboardTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('dashboard'), 'dashboard missing')
        import dashboard
        return dashboard

    def test_units_health_and_left_labels(self):
        d=self.module()
        p=d.snapshot('leader',0,rms=3276.8,volume=.8,clipped=True)
        self.assertEqual(p['level_units'],'dBFS');self.assertAlmostEqual(p['level'],-20)
        self.assertEqual(p['state'],'CLIPPING');self.assertEqual(p['labels'],('PAGE','NEXT','SLEEP'))
        c=d.snapshot('follower',2,volume=.25,age=1)
        self.assertEqual(c['level_units'],'%');self.assertEqual(c['level'],25)
        self.assertEqual(c['state'],'LOST');self.assertEqual(c['labels'][1],'FOLLOW')
        self.assertEqual(d.snapshot('leader',0,calibrating=True)['state'],'CALIBRATING')
        self.assertEqual(d.snapshot('leader',0,fault=True)['state'],'MIC FAULT')
        self.assertEqual(d.snapshot('leader',0)['state'],'QUIET')

    def test_rate_wrap_reset_and_bounded_updates(self):
        d=self.module();r=d.Rate()
        self.assertEqual(r.update(4294967294,0),0)
        self.assertEqual(r.update(2,1),4)
        self.assertEqual(r.update(0,2),0)
        backend=Mock();ui=d.Dashboard(backend,interval=.2)
        state=d.snapshot('leader',0)
        self.assertTrue(ui.update(0,state,spare=.02))
        self.assertFalse(ui.update(.1,state,spare=.02))
        self.assertFalse(ui.update(.3,state,spare=0))
        self.assertTrue(ui.update(.4,state,spare=.02))
        backend.draw.side_effect=RuntimeError('display lost')
        self.assertFalse(ui.update(.7,state,spare=.02))
        self.assertFalse(ui.update(1,state,spare=.02))
        self.assertEqual(backend.draw.call_count,3)

    def test_audio_budget_gate_precedes_snapshot_and_sensor_work(self):
        from test_sleep import load_app
        from audio_features import AudioFeatures
        from types import SimpleNamespace
        from unittest.mock import patch
        app=load_app();ui=Mock(failed=False,next_refresh=0,cost=.005,skipped=0)
        battery=Mock();battery.update.return_value={}
        rate=Mock();rate.update.return_value=0
        with patch.object(app,'DISPLAY',ui),patch('dashboard.snapshot') as snapshot:
            app.update_dashboard(1,AudioFeatures(),SimpleNamespace(effect=0),battery,None,rate,spare=0)
        battery.update.assert_not_called();snapshot.assert_not_called();ui.update.assert_not_called()

    def test_disabled_dashboard_blanks_native_display_for_real_off_benchmark(self):
        from test_sleep import load_app
        from types import SimpleNamespace
        from unittest.mock import patch
        app=load_app();native=Mock(brightness=1,auto_refresh=True,root_group=object())
        with patch.object(app,'PROFILE',{'display':True}), \
             patch.object(app,'CONFIG',SimpleNamespace(display_enabled=False)), \
             patch.object(app,'board',SimpleNamespace(DISPLAY=native)):
            self.assertIsNone(app.start_dashboard())
        self.assertEqual(native.brightness,0)
        self.assertFalse(native.auto_refresh)
        self.assertIsNone(native.root_group)
