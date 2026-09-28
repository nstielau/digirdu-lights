import sys
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch, mock_open

import hardware as h


class EchoAnimationTests(unittest.TestCase):
    def test_wave_reflects_then_bursts_and_glows(self):
        self.assertTrue(hasattr(h,'echo_frame'),'EchoGlow animation missing')
        outgoing=[h.echo_frame(t) for t in (0,.2,.4,.6)]
        self.assertTrue(all(f[0]=='wave' for f in outgoing))
        self.assertEqual([f[1] for f in outgoing],sorted(f[1] for f in outgoing))
        reflected=[h.echo_frame(t) for t in (.75,.9,1.05)]
        self.assertTrue(all(f[0]=='echo' for f in reflected))
        self.assertGreater(reflected[0][1],reflected[-1][1])
        self.assertEqual(h.echo_frame(1.5)[0],'burst')
        self.assertEqual(h.echo_frame(2.5)[0],'glow')
        self.assertEqual(h.echo_frame(100)[0],'glow')

    def test_every_primitive_stays_in_animation_region(self):
        self.assertTrue(hasattr(h,'EchoArt'),'EchoGlow renderer missing')
        class Bitmap:
            width=216;height=60
            def fill(self,value):pass
        bitmap=Bitmap();calls=[]
        def fill(b,x1,y1,x2,y2,color):
            self.assertIs(b,bitmap)
            self.assertTrue(0<=x1<x2<=216,(x1,x2))
            self.assertTrue(0<=y1<y2<=60,(y1,y2))
            calls.append((x1,y1,x2,y2,color))
        art=h.EchoArt.__new__(h.EchoArt);art.bitmap=bitmap;art.fill_region=fill
        for i in range(100):art.draw(i*.037)
        self.assertTrue(calls)
        self.assertLess(len(calls),5000,'unbounded particle work')


class BootScreenTests(unittest.TestCase):
    def test_stale_screen_cleanup_preserves_replacement_fault_screen(self):
        text=h.TextScreen.__new__(h.TextScreen)
        text.group=object();replacement=object()
        text.display=SimpleNamespace(root_group=replacement,brightness=.5)
        text.close()
        self.assertIs(text.display.root_group,replacement)
        self.assertEqual(text.display.brightness,.5)
        text.display.root_group=text.group
        text.close()
        self.assertIsNone(text.display.root_group)
        self.assertEqual(text.display.brightness,0)

    def screen(self,clock):
        screen=Mock()
        screen.display.root_group=screen.group
        patches=(patch.dict(sys.modules,{'board':SimpleNamespace(board_id=h.S3)}),
                 patch.object(h,'TextScreen',return_value=screen),
                 patch.object(h,'EchoArt',return_value=Mock()),
                 patch('time.monotonic',side_effect=lambda:clock[0]))
        for p in patches:p.start();self.addCleanup(p.stop)
        return screen,h.BootScreen()

    def test_brand_version_status_and_bounded_ticks(self):
        self.assertTrue(hasattr(h,'EchoArt'),'EchoGlow renderer missing')
        clock=[0];text,screen=self.screen(clock)
        text.text.assert_any_call('title','EchoGlow')
        screen.version('1.2.3');text.text.assert_any_call('version','v1.2.3')
        screen.phase('Checking updates')
        text.text.assert_any_call('phase','Checking updates')
        count=text.refresh.call_count
        clock[0]=.01;screen.tick();self.assertEqual(text.refresh.call_count,count)
        clock[0]=.11;screen.tick();self.assertEqual(text.refresh.call_count,count+1)
        text.refresh.side_effect=RuntimeError('display missing')
        clock[0]=1;screen.tick()
        self.assertIsNone(screen.screen)

    def test_maintenance_mode_keeps_an_amber_badge_on_the_splash(self):
        clock=[0];text,screen=self.screen(clock)
        screen.maintenance()
        text.text.assert_any_call('mode','USB MAINT')
        text.text.assert_any_call('phase','CIRCUITPY READY')
        self.assertTrue(screen.art.maintenance)

    def test_no_display_has_no_graphics_allocation(self):
        with patch.dict(sys.modules,{'board':SimpleNamespace(board_id=h.S2)}), \
             patch.object(h,'TextScreen') as screen:
            ui=h.BootScreen()
            self.assertTrue(hasattr(ui,'tick'),'boot tick missing')
            ui.version('1.2.3');ui.tick();ui.phase('Starting');ui.close()
            screen.assert_not_called()

    def test_shared_screen_survives_indicator_cleanup_until_handoff(self):
        from ota_bootstrap import OTAIndicator
        self.assertTrue(hasattr(h,'start_boot'),'boot lifecycle missing')
        text=Mock()
        modules={'board':SimpleNamespace(board_id=h.S3,D6=object()),
                 'digitalio':SimpleNamespace(DigitalInOut=Mock()),
                 'neopixel_write':SimpleNamespace(neopixel_write=Mock())}
        with patch.dict(sys.modules,modules),patch.object(h,'BootScreen',return_value=text):
            h.start_boot()
            indicator=OTAIndicator()
            self.assertIs(indicator.screen,text)
            indicator.update()
            text.tick.assert_called()
            indicator.close();text.close.assert_not_called()
            h.close_boot();text.close.assert_called_once()

    def test_recovery_boot_displays_recovery_version_and_hands_off(self):
        import ota_bootstrap as ota
        self.assertTrue(hasattr(h,'start_boot'),'boot lifecycle missing')
        class Running(BaseException):pass
        app=Mock();app.CONFIG.radio_role='follower';app.main.side_effect=Running
        screen=Mock()
        modules={'board':SimpleNamespace(),
                 'storage':SimpleNamespace(getmount=lambda _:SimpleNamespace(readonly=True)),
                 'microcontroller':SimpleNamespace(),
                 'watchdog':SimpleNamespace(WatchDogMode=SimpleNamespace(RESET=1))}
        with patch.dict(sys.modules,modules), \
             patch.object(h,'start_boot',return_value=screen),patch.object(h,'close_boot') as close, \
             patch.object(ota,'open',mock_open(read_data='APP_VERSION="1.2.3"')), \
             patch.object(ota,'load_app',return_value=(app,'1.2.3')), \
             patch.dict(os.environ,{'OTA_ENABLED':'1'}):
            with self.assertRaises(Running):ota.main()
            screen.maintenance.assert_called_once()
            screen.version.assert_called_with('1.2.3')
            screen.phase.assert_any_call('Listening for producer')
            close.assert_called()

    def test_slot_identity_is_read_from_selected_directory(self):
        import ota_bootstrap as ota
        reader=mock_open(read_data='APP_VERSION="2.3.4"')
        with patch.object(ota,'open',reader):
            self.assertEqual(ota.selected_version('/ota/slot1'),'2.3.4')
        reader.assert_called_once_with('/ota/slot1/app_version.py')

    def test_animation_catches_up_gradually_after_a_blocking_call(self):
        self.assertTrue(hasattr(h,'EchoArt'),'EchoGlow renderer missing')
        clock=[0];text,screen=self.screen(clock)
        clock[0]=8;screen.tick()
        # A network/import pause must not skip reflection/explosion entirely.
        self.assertLessEqual(screen.art.draw.call_args.args[0],.2)

    def test_finishes_all_stages_at_twenty_fps_before_handoff(self):
        clock=[0];text,screen=self.screen(clock)
        self.assertTrue(hasattr(screen,'finish'),'animation completion missing')
        with patch('time.sleep',side_effect=lambda delay:clock.__setitem__(0,clock[0]+delay)):
            screen.finish()
        frames=[call.args[0] for call in screen.art.draw.call_args_list]
        self.assertGreaterEqual(frames[-1],2.35)
        self.assertLess(clock[0],3)
        for stage in ('wave','echo','burst','glow'):
            self.assertIn(stage,[h.echo_frame(t)[0] for t in frames])
        self.assertGreaterEqual(len(frames),45)
        self.assertLessEqual(len(frames),52)
        count=len(frames)
        screen.finish()
        self.assertEqual(len(screen.art.draw.call_args_list),count)

    def test_finishing_does_not_wait_for_headless_replaced_or_failed_display(self):
        clock=[0];text,screen=self.screen(clock)
        self.assertTrue(hasattr(screen,'finish'),'animation completion missing')
        text.display.root_group=object()
        with patch('time.sleep') as sleep:
            screen.finish();sleep.assert_not_called()
        text.display.root_group=text.group
        text.refresh.side_effect=RuntimeError('display failed')
        with patch('time.sleep',side_effect=lambda delay:clock.__setitem__(0,clock[0]+delay)):
            screen.finish()
        self.assertIsNone(screen.screen)
        self.assertLess(clock[0],.1)
        with patch('time.sleep') as sleep:
            screen.finish();sleep.assert_not_called()

    def test_finishing_has_a_deadline_if_progress_stalls(self):
        clock=[0];text,screen=self.screen(clock)
        self.assertTrue(hasattr(screen,'finish'),'animation completion missing')
        screen.tick=Mock() # simulates a callback that never advances animation
        with patch('time.sleep',side_effect=lambda delay:clock.__setitem__(0,clock[0]+delay)):
            screen.finish()
        self.assertLessEqual(clock[0],3.02)

    def test_finish_handoff_releases_boot_only_after_last_frame(self):
        self.assertTrue(hasattr(h,'finish_boot'),'animation handoff missing')
        screen=Mock();events=[]
        screen.finish.side_effect=lambda:events.append('finish')
        screen.close.side_effect=lambda:events.append('close')
        with patch.object(h,'_boot_screen',screen):
            h.finish_boot()
            self.assertEqual(events,['finish','close'])
            self.assertIsNone(h._boot_screen)

    def test_disabling_dashboard_releases_boot_graphics(self):
        from test_sleep import load_app
        app=load_app()
        with patch.object(app,'CONFIG',SimpleNamespace(display_enabled=False)), \
             patch.object(h,'close_boot') as close:
            app.start_dashboard()
            close.assert_called_once()
