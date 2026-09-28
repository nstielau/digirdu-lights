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
        self.assertEqual(c['state'],'LOST');self.assertEqual(c['labels'][1],'NEXT')
        self.assertEqual(d.snapshot('leader',0,calibrating=True)['state'],'CALIBRATING')
        self.assertEqual(d.snapshot('leader',0,fault=True)['state'],'MIC FAULT')
        self.assertEqual(d.snapshot('leader',0)['state'],'QUIET')

    def test_maintenance_mode_adds_a_persistent_banner(self):
        d=self.module()
        state=d.snapshot('consumer',0,maintenance=True)
        self.assertTrue(state['maintenance'])
        self.assertEqual(d.page_content(state,0)['banner'],'USB MAINTENANCE')

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
        ui.ready.return_value=False
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


class FourPageTests(unittest.TestCase):
    def test_cycle_and_effect_updates_do_not_navigate(self):
        import dashboard as d
        ui=d.Dashboard(Mock());self.assertEqual(ui.page,0)
        pages=[]
        for _ in range(4):ui.toggle();pages.append(ui.page)
        self.assertEqual(pages,[1,2,3,0])
        ui.toggle()
        ui.update(1,d.snapshot('leader',4),spare=1)
        self.assertEqual(ui.page,1)

    def test_spectrum_status_and_never_received(self):
        import dashboard as d
        p=d.snapshot('producer',0,spectrum=(-1,.1,.2,.3,.4,.5,.6,2),
                     seen=32,full=True,rate=15,tx_failed=3,
                     battery={'status':'measured','percent':78.9,'voltage':3.9})
        self.assertEqual(p['spectrum'],(0,.1,.2,.3,.4,.5,.6,1))
        self.assertEqual(p['status_rows'],(('Battery','78%'),('Seen / 10s','32+'),('TX / sec','15.0'),('TX failed','3')))
        c=d.snapshot('consumer',0,age=None)
        self.assertEqual(c['state'],'LOST')
        self.assertEqual(c['status_rows'],(('Battery','--'),('Link','LOST'),('RX / sec','0.0'),('Last RX','--')))
        self.assertEqual(d.snapshot('consumer',0,age=.04)['status_rows'][3][1],'40ms')
        self.assertLessEqual(len(d.snapshot('consumer',0,age=1e20)['status_rows'][3][1]),11)

    def test_page_content_faults_countdown_and_field_bounds(self):
        import dashboard as d
        from effects import EFFECT_NAMES
        for role in ('producer','consumer'):
            for effect in range(len(EFFECT_NAMES)):
                for page in range(3):
                    for message in ('','Hold D2: 2.0s','SLEEP / fading'):
                        state=d.snapshot(role,effect,fault=True,age=None,message=message)
                        content=d.page_content(state,page)
                        self.assertEqual(content['page'],'%d/4'%(page+1))
                        self.assertIn(message or ('MIC FAULT' if role=='producer' else 'LOST'),content.values())
                        for name,_,_,count,_,_ in d.TFT_FIELDS:
                            self.assertLessEqual(len(content.get(name,'')),count,(page,name))
        for _,x,y,count,scale,_ in d.TFT_FIELDS:
            self.assertLessEqual(x+count*6*scale,240)
            self.assertLessEqual(y+14*scale,135)


class RenderTests(unittest.TestCase):
    def test_maintenance_banner_uses_the_amber_strip(self):
        import dashboard as d
        class Bitmap:
            def fill(self,value):pass
        ui=d.TFTBackend.__new__(d.TFTBackend)
        ui.back=Bitmap();ui.fill_region=Mock();ui._text=Mock()
        ui._prepare(d.snapshot('consumer',0,maintenance=True),0)
        ui.fill_region.assert_any_call(ui.back,40,0,240,22,15)

    def test_frame_transfer_is_bounded_and_switching_replaces_pending_page(self):
        import dashboard as d
        from types import SimpleNamespace
        ui=d.TFTBackend.__new__(d.TFTBackend)
        ui.front=object();ui.back=object();ui.row=135;ui.pending=False;ui.page=None
        ui._prepare=Mock();ui.blit=Mock();ui.display=Mock();ui.overlay=None
        state=d.snapshot('consumer',0)
        ui.draw(state,0)
        ui._prepare.assert_called_once_with(state,0)
        ui.blit.assert_not_called()
        self.assertTrue(ui.pending)
        for row in range(0,135,12):
            ui.draw(state,0)
            self.assertEqual(ui.blit.call_args.kwargs,{'x1':0,'y1':row,'x2':240,'y2':min(135,row+12)})
        self.assertFalse(ui.pending)
        self.assertEqual(ui.display.refresh.call_count,12)
        ui.draw(state,1);ui.draw(state,1)
        ui.draw(state,0)
        self.assertEqual(ui.row,0)
        self.assertEqual(ui.page,0)
        self.assertEqual(ui._prepare.call_count,3)

    def test_pending_strips_continue_without_waiting_another_frame_interval(self):
        import dashboard as d
        backend=Mock(pending=True)
        ui=d.Dashboard(backend)
        self.assertTrue(ui.update(1,d.snapshot('consumer',0),spare=1))
        self.assertTrue(ui.update(1.03,d.snapshot('consumer',0),spare=1))
        backend.draw.side_effect=lambda *args:setattr(backend,'pending',False)
        self.assertTrue(ui.update(1.06,d.snapshot('consumer',0),spare=1))
        self.assertFalse(ui.update(1.1,d.snapshot('consumer',0),spare=1))
        self.assertTrue(ui.update(1.21,d.snapshot('consumer',0),spare=1))


class RuntimeTelemetryTests(unittest.TestCase):
    def test_never_received_audio_and_existing_spectrum_reach_dashboard(self):
        from test_sleep import load_app
        from audio_features import AudioFeatures
        from types import SimpleNamespace
        from unittest.mock import patch
        app=load_app();features=AudioFeatures()
        ui=Mock(failed=False,next_refresh=0,cost=.001,skipped=0)
        battery=Mock();battery.update.return_value={}
        rate=Mock();rate.update.return_value=0
        radio=SimpleNamespace(receiver=SimpleNamespace(audio_sequence=None,last_audio=0,accepted=0),presence=None,radio=SimpleNamespace(send_failure=2))
        with patch.object(app,'DISPLAY',ui),patch('dashboard.snapshot',return_value={}) as snap:
            app.update_dashboard(1,features,SimpleNamespace(effect=0),battery,radio,rate,spare=1)
        self.assertIsNone(snap.call_args.kwargs['age'])
        self.assertIs(snap.call_args.kwargs['spectrum'],features.spectrum)
        self.assertEqual(snap.call_args.kwargs['tx_failed'],2)

    def test_serial_diagnostics_preserve_details_at_bounded_rate(self):
        from test_sleep import load_app
        from types import SimpleNamespace
        from unittest.mock import patch
        app=load_app()
        radio=SimpleNamespace(sent=22,errors=1,skipped=3,radio=SimpleNamespace(send_success=20,send_failure=1),
                              receiver=SimpleNamespace(accepted=9,rejected=2),presence=None)
        with patch.object(app,'PROFILE',{'display':True}),patch('builtins.print') as output:
            app.log_device_diagnostics(10,radio,4)
            app.log_device_diagnostics(11,radio,5)
            self.assertEqual(output.call_count,1)
            line=output.call_args.args[0]
            for item in ('TX=22','ok=20','failed=1','skipped=3','RX=9','rejected=2','overruns=4','source=','v1.1.1'):
                self.assertIn(item,line)
            app.log_device_diagnostics(20,radio,6)
            self.assertEqual(output.call_count,2)


class CircuitPythonMathTests(unittest.TestCase):
    def test_producer_level_uses_supported_math_functions(self):
        import dashboard as d
        import math
        from types import SimpleNamespace
        from unittest.mock import patch
        with patch.object(d,'math',SimpleNamespace(log=math.log)):
            self.assertAlmostEqual(d.snapshot('producer',0,rms=3276.8)['level'],-20)

class ResponsiveDashboardTests(unittest.TestCase):
    def test_recovers_after_slow_draw_without_ignoring_empty_audio_budget(self):
        import dashboard as d
        ui=d.Dashboard(Mock(pending=False));ui.cost=.08
        state=d.snapshot('consumer',0)
        self.assertFalse(ui.update(.1,state,spare=0))
        self.assertTrue(ui.update(1,state,spare=.015))
        ui.cost=.08;ui.toggle()
        self.assertFalse(ui.update(1.01,state,spare=0))
        self.assertTrue(ui.update(1.02,state,spare=.015))

    def test_status_is_slow_and_page_switch_is_immediate(self):
        import dashboard as d
        ui=d.Dashboard(Mock(pending=False));state=d.snapshot('consumer',2,age=0)
        ui.toggle();self.assertEqual(ui.page,1)
        self.assertTrue(ui.update(1,state))
        self.assertFalse(ui.update(1.3,state))
        self.assertTrue(ui.update(2.1,state))
        ui.toggle();ui.toggle();ui.toggle();self.assertEqual(ui.page,0)
        self.assertTrue(ui.update(2.11,state))
        content=d.page_content(state,1)
        self.assertIn('3 Aurora',content.values())
        self.assertIn('Battery',content.values())

    def test_runtime_counts_preparation_once_in_total_budget(self):
        from test_sleep import load_app
        from audio_features import AudioFeatures
        from types import SimpleNamespace
        from unittest.mock import patch
        import dashboard as d
        app=load_app();backend=Mock(pending=False);ui=d.Dashboard(backend)
        ui.cost=.024
        battery=Mock();battery.update.return_value={}
        rate=Mock();rate.update.return_value=0
        with patch.object(app,'DISPLAY',ui),patch('time.monotonic',side_effect=[10,10.004,10.004,10.024]):
            app.update_dashboard(.1,AudioFeatures(),SimpleNamespace(effect=0),battery,None,rate,spare=.027)
        backend.draw.assert_called_once()
