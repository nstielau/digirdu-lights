import unittest
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import dashboard as d
from config import Config


class DisplayActivityTests(unittest.TestCase):
    def test_maintenance_border_is_ready_before_boot_splash_closes(self):
        events=[]
        def bitmap(width,height,_colors):
            return SimpleNamespace(width=width,height=height,fill=Mock())
        display=SimpleNamespace(auto_refresh=True,brightness=0,root_group=None,
                                refresh=lambda **_kw:events.append('refresh'))
        font=SimpleNamespace(bitmap=SimpleNamespace(width=6,height=12),
                             get_bounding_box=lambda:(6,12))
        displayio=SimpleNamespace(Bitmap=bitmap,Palette=lambda n:[0]*n,
                                  Group=lambda:SimpleNamespace(append=Mock()),
                                  TileGrid=Mock())
        bitmaptools=SimpleNamespace(fill_region=Mock(),blit=Mock(),arrayblit=Mock(),
                                    rotozoom=Mock(),replace_color=Mock())
        modules={'board':SimpleNamespace(DISPLAY=display),'displayio':displayio,
                 'bitmaptools':bitmaptools,'terminalio':SimpleNamespace(FONT=font),
                 'hardware':SimpleNamespace(finish_boot=lambda:events.append('close'))}
        with patch.dict(sys.modules,modules), \
             patch.object(d.TFTBackend,'_border',lambda _self,_bitmap:events.append('border')):
            d.TFTBackend(SimpleNamespace(display_rotation=0,display_brightness=.2),
                         maintenance=True)
        self.assertLess(events.index('border'),events.index('close'))
        self.assertLess(events.index('close'),events.index('refresh'))

    def test_all_three_chord_can_start_while_display_is_idle(self):
        from test_sleep import load_app
        from effects import TFTControls, SleepTransition
        app=load_app();ui=d.Dashboard(Mock(),idle_s=30)
        buttons=app.TFTButtons.__new__(app.TFTButtons)
        buttons.inputs=[SimpleNamespace(value=v) for v in (True,False,False)]
        buttons.logic=TFTControls('follower',.04,3)
        sleep=SleepTransition();radio=Mock()
        def poll(now,levels):
            for pin,value in zip(buttons.inputs,levels):pin.value=value
            buttons.poll(Mock(),now,sleep,radio=radio)
        with patch.object(app,'DISPLAY',ui):
            ui.visible(0)
            poll(0,(True,False,False));poll(.05,(True,False,False))
            self.assertFalse(ui.visible(30))
            for now in (31,31.05,35.06):poll(now,(False,True,True))
            self.assertTrue(buttons.logic.maintenance_ready)
            poll(35.1,(True,False,False))
            with self.assertRaises(app.MaintenanceRequested):poll(35.16,(True,False,False))
        radio.request_control.assert_not_called()

    def test_idle_stops_drawing_and_wake_preserves_page(self):
        backend=Mock(pending=False)
        ui=d.Dashboard(backend,idle_s=30)
        ui.page=2
        state=d.snapshot('consumer',0)
        self.assertTrue(ui.update(100,state))
        self.assertTrue(ui.update(129,state))
        self.assertFalse(ui.update(130,state))
        backend.set_awake.assert_called_once_with(False)
        for now in (131,140,200):self.assertFalse(ui.update(now,state))
        self.assertEqual(backend.draw.call_count,2)
        self.assertTrue(ui.button_activity(201,True))
        backend.set_awake.assert_called_with(True)
        self.assertEqual(ui.page,2)
        self.assertTrue(ui.update(201,state))

    def test_maintenance_keeps_display_awake_until_mode_ends(self):
        backend=Mock(pending=False)
        ui=d.Dashboard(backend,idle_s=30)
        ui.visible(0)
        ui.maintenance=True
        self.assertTrue(ui.visible(100))
        backend.set_awake.assert_not_called()
        ui.maintenance=False
        self.assertTrue(ui.visible(120))
        self.assertFalse(ui.visible(130.1))
        backend.set_awake.assert_called_once_with(False)

    def test_wake_hold_is_consumed_until_all_buttons_released_stably(self):
        ui=d.Dashboard(Mock(),idle_s=30)
        ui.visible(0);self.assertFalse(ui.visible(30))
        for now in (31,31.1,34,40):self.assertTrue(ui.button_activity(now,True))
        self.assertTrue(ui.button_activity(40.01,False))
        self.assertTrue(ui.button_activity(40.02,True)) # release bounce
        self.assertTrue(ui.button_activity(40.03,False))
        self.assertTrue(ui.button_activity(40.1,False))
        self.assertFalse(ui.button_activity(40.2,True))
        self.assertTrue(ui.visible(69))
        self.assertFalse(ui.visible(70.2))

    def test_incoming_sleep_wakes_and_stays_visible(self):
        backend=Mock();ui=d.Dashboard(backend,idle_s=30)
        ui.visible(0);ui.visible(30)
        ui.set_overlay(d.sleep_overlay(remaining=3))
        self.assertTrue(ui.visible(40))
        backend.set_awake.assert_called_with(True)
        self.assertTrue(ui.visible(100))
        ui.set_overlay(None)
        self.assertTrue(ui.visible(129))
        self.assertFalse(ui.visible(130))

    def test_idle_gate_precedes_snapshot_and_sensor_work(self):
        from test_sleep import load_app
        from audio_features import AudioFeatures
        app=load_app();ui=d.Dashboard(Mock(),idle_s=30)
        ui.visible(0);battery=Mock();rate=Mock()
        with patch.object(app,'DISPLAY',ui),patch('dashboard.snapshot') as snap:
            app.update_dashboard(31,AudioFeatures(),SimpleNamespace(effect=0),battery,None,rate,spare=1)
        battery.update.assert_not_called();rate.update.assert_not_called();snap.assert_not_called()

    def test_config_separates_tft_and_wing_brightness_and_validates_timeout(self):
        c=Config()
        self.assertEqual(c.display_brightness,.5)
        self.assertEqual(c.brightness,.15)
        self.assertEqual(c.display_idle_s,30)
        for invalid in (0,-1,float('inf'),float('nan')):
            with self.assertRaises(ValueError):Config(display_idle_s=invalid)

    def test_backlight_failure_disables_only_dashboard(self):
        backend=Mock();backend.set_awake.side_effect=RuntimeError('backlight')
        ui=d.Dashboard(backend)
        ui.visible(0)
        self.assertFalse(ui.visible(30))
        self.assertTrue(ui.failed)
        backend.close.assert_called_once()

    def test_real_button_routing_consumes_wake_hold_then_allows_commands(self):
        from test_sleep import load_app
        from effects import TFTControls, SleepTransition
        import radio_protocol as p
        app=load_app();ui=d.Dashboard(Mock(pending=False))
        buttons=app.TFTButtons.__new__(app.TFTButtons)
        buttons.inputs=[SimpleNamespace(value=v) for v in (True,False,False)]
        buttons.logic=TFTControls('follower',.04,3)
        animation=Mock();radio=Mock();sleep=SleepTransition()
        def poll(now,levels=(True,False,False)):
            for pin,value in zip(buttons.inputs,levels):pin.value=value
            buttons.poll(animation,now,sleep,radio=radio)
        with patch.object(app,'DISPLAY',ui),patch.object(app,'CONFIG',Config(radio_role='consumer')):
            ui.visible(0);poll(0);poll(.1)
            ui.visible(30)
            for now in (31,31.1,34.2,35):poll(now,(True,False,True))
            poll(35.1);poll(35.2);poll(35.3)
            radio.request_control.assert_not_called()
            self.assertEqual(ui.page,0)
            self.assertEqual(buttons.logic.countdown,0)
            poll(36,(False,False,False));poll(36.1,(False,False,False))
            poll(36.2);poll(36.3)
            self.assertEqual(ui.page,1)
            poll(37,(True,True,False));poll(37.1,(True,True,False))
            poll(37.2);poll(37.3)
            radio.request_control.assert_called_once_with(p.NEXT_EFFECT,37.3)
            animation.set_effect.assert_not_called()

    def test_native_backlight_restores_configured_level_and_discards_stale_frame(self):
        backend=d.TFTBackend.__new__(d.TFTBackend)
        backend.display=Mock();backend.brightness=.5;backend.pending=True
        backend.set_awake(False)
        self.assertEqual(backend.display.brightness,0)
        backend.set_awake(True)
        self.assertEqual(backend.display.brightness,.5)
        self.assertFalse(backend.pending)


class BannerTests(unittest.TestCase):
    def test_short_ack_banner_is_rendered_while_status_frame_is_pending(self):
        backend=d.TFTBackend.__new__(d.TFTBackend)
        backend.front=object();backend.back=object();backend.row=135
        backend.pending=False;backend.page=None;backend.overlay=None
        backend._prepare=Mock();backend.blit=Mock();backend.display=Mock()
        ui=d.Dashboard(backend);ui.page=1
        for step in range(65):
            now=step*.032
            ui.set_banner('CHANGING EFFECT' if step==2 else '',now)
            ui.update(now,d.snapshot('consumer',0,banner=ui.banner))
        self.assertIn('Broadcasting...',[
            call.args[0]['banner'] for call in backend._prepare.call_args_list])

    def test_command_feedback_keeps_normal_page_visible(self):
        self.assertIsNone(d.sleep_overlay(status='CHANGING EFFECT'))
        for page in range(4):
            state=d.snapshot('consumer',1,banner='Broadcasting...')
            content=d.page_content(state,page)
            self.assertEqual(content['banner'],'Broadcasting...')
            self.assertEqual(content['page'],'%d/4'%(page+1))
            self.assertNotIn('sleep_title',content)
            self.assertNotIn('header',content)
            if page==1:self.assertEqual(content['k0'],'Battery')
            if page==2:self.assertEqual(content['effect'],'15%')

    def test_banner_lingers_after_ack_but_errors_are_not_hidden(self):
        ui=d.Dashboard(Mock())
        ui.set_banner('CHANGING EFFECT',1)
        self.assertEqual(ui.banner,'Broadcasting...')
        ui.set_banner('',1.05)
        self.assertEqual(ui.banner,'Broadcasting...')
        ui.set_banner('NO PRODUCER',1.1)
        self.assertEqual(ui.banner,'NO PRODUCER')
        ui.set_banner('',3)
        self.assertEqual(ui.banner,'')


class SleepAnimationTests(unittest.TestCase):
    def test_usb_countdown_uses_orange_fields_and_two_pixel_border(self):
        overlay=d.maintenance_overlay(3.1)
        self.assertEqual(overlay,('maintenance','HOLD FOR USB','4','Release to cancel'))
        state=d.snapshot('consumer',0,overlay=overlay)
        for page in range(4):
            content=d.page_content(state,page)
            self.assertEqual(content['maintenance_title'],'HOLD FOR USB')
            self.assertEqual(content['maintenance_number'],'4')
            self.assertNotIn('sleep_title',content)
        backend=d.TFTBackend.__new__(d.TFTBackend)
        backend.back=Mock();backend.fill_region=Mock();backend._text=Mock()
        backend._sleep_dog=Mock()
        backend._prepare(state,0)
        self.assertEqual([call.args[:5] for call in backend.fill_region.call_args_list[-4:]],[
            (backend.back,0,0,240,2),(backend.back,0,133,240,135),
            (backend.back,0,0,2,135),(backend.back,238,0,240,135)])
        backend._sleep_dog.assert_not_called()
        ready=d.maintenance_overlay(0,ready=True)
        self.assertEqual(d.page_content(d.snapshot('consumer',0,overlay=ready),0)['maintenance_title'],
                         'USB READY')

    def test_running_maintenance_border_persists_on_every_page(self):
        border=((0,0,240,2),(0,133,240,135),(0,0,2,135),(238,0,240,135))
        backend=d.TFTBackend.__new__(d.TFTBackend)
        backend.back=Mock();backend.fill_region=Mock();backend._text=Mock()
        backend._sleep_dog=Mock()
        for page in range(4):
            backend.fill_region.reset_mock()
            backend._prepare(d.snapshot('consumer',0,maintenance=True),page)
            self.assertEqual([call.args[1:6] for call in backend.fill_region.call_args_list[-4:]],
                             [(*rect,14) for rect in border])
        backend.fill_region.reset_mock()
        backend._prepare(d.snapshot('consumer',0,maintenance=False),3)
        self.assertFalse(any(call.args[-1]==14 for call in backend.fill_region.call_args_list))

    def test_maintenance_countdown_computer_stays_above_cancel_instruction(self):
        backend=d.TFTBackend.__new__(d.TFTBackend)
        backend.back=Mock();backend.fill_region=Mock();backend._text=Mock()
        backend._sleep_dog=Mock()
        for overlay in (d.maintenance_overlay(3.1),d.maintenance_overlay(0,ready=True)):
            backend.fill_region.reset_mock()
            backend._prepare(d.snapshot('consumer',0,overlay=overlay),0)
            art=[call.args for call in backend.fill_region.call_args_list
                 if call.args[-1] in (3,5,9,12)]
            self.assertTrue(any(call[-1]==5 for call in art), 'cyan face missing')
            self.assertTrue(any(call[-1]==3 for call in art), 'amber case missing')
            for _,x1,y1,x2,y2,_ in art:
                self.assertTrue(33<=x1<x2<=118)
                self.assertTrue(37<=y1<y2<=105)
        backend._sleep_dog.assert_not_called()
        backend.fill_region.reset_mock()
        backend._prepare(d.snapshot('consumer',0),0)
        self.assertFalse(any(call.args[-1]==5 for call in backend.fill_region.call_args_list))
        backend.fill_region.reset_mock()
        backend._prepare(d.snapshot('consumer',0,overlay=d.sleep_overlay(remaining=2)),0)
        backend._sleep_dog.assert_called_once()
        self.assertFalse(any(call.args[-1]==5 for call in backend.fill_region.call_args_list))

    def test_animated_frames_do_not_restart_incomplete_transfers(self):
        backend=d.TFTBackend.__new__(d.TFTBackend)
        backend.front=object();backend.back=object();backend.row=135
        backend.pending=False;backend.page=None;backend.overlay=None
        backend._prepare=Mock();backend.blit=Mock();backend.display=Mock()
        for frame in range(13):
            state=d.snapshot('consumer',0,overlay=d.sleep_overlay(remaining=3-frame*.1),animation_frame=frame%4)
            backend.draw(state,0)
        self.assertFalse(backend.pending)
        backend._prepare.assert_called_once()
        self.assertEqual(backend.display.refresh.call_count,12)

    def test_dog_has_breathing_and_snoring_frames(self):
        backend=d.TFTBackend.__new__(d.TFTBackend)
        backend.back=Mock();backend.dog=object();backend.blit=Mock()
        backend.fill_region=Mock();backend._text=Mock()
        for frame in range(4):backend._sleep_dog(frame)
        self.assertGreater(len({call.args[3] for call in backend.blit.call_args_list}),1)
        self.assertTrue(any(call.args[0]=='Z' for call in backend._text.call_args_list))
        for call in backend._text.call_args_list:
            _,x,y,_,scale,_=call.args
            self.assertTrue(0<=x<240-6*scale and 0<=y<135-14*scale)
