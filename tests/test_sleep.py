"""Long press, lossy sleep broadcast, and orderly device shutdown."""
import importlib.util
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

from animation import CulvertAnimation
from audio_features import AudioFeatures
from config import Config
from effects import ButtonGesture, SleepTransition, TFTControls
from radio_protocol import Transmitter, Receiver, SLEEP_FORMAT, SLEEP_SIZE
from test_wireless import wireless_class


class GestureTests(unittest.TestCase):
    def button(self):
        return ButtonGesture(.04, 3)

    def test_short_press_fires_on_release_only_after_debounce(self):
        b = self.button()
        for pressed, now in ((True,0),(False,.01),(True,.02),(True,.07),(True,.5),(False,.6),(True,.61),(False,.62)):
            self.assertEqual(b.update(pressed,now),0)
        self.assertEqual(b.update(False,.67),ButtonGesture.SHORT)
        self.assertEqual(b.update(False,1),0)

    def test_hold_fires_at_three_seconds_once_and_release_does_not_step(self):
        b=self.button()
        for now in (0,.05,2.99):self.assertEqual(b.update(True,now),0)
        self.assertEqual(b.update(True,3),ButtonGesture.HOLD)
        for now in (3.1,6,60):self.assertEqual(b.update(True,now),0)
        self.assertEqual(b.update(False,61),0)
        self.assertEqual(b.update(False,61.05),0)
        b.update(True,62);b.update(True,62.05);b.update(False,62.2)
        self.assertEqual(b.update(False,62.3),ButtonGesture.SHORT)

    def test_release_just_before_threshold_is_short_even_when_debounce_finishes_later(self):
        b=self.button();b.update(True,0);b.update(True,.05)
        self.assertEqual(b.update(False,2.99),0)
        self.assertEqual(b.update(False,3.05),ButtonGesture.SHORT)
        b=self.button();b.update(True,0);b.update(True,.05)
        self.assertEqual(b.update(False,3.01),0)
        self.assertEqual(b.update(False,3.06),ButtonGesture.HOLD)


class MaintenanceChordTests(unittest.TestCase):
    IDLE=(True,False,False)
    ALL=(False,True,True)

    def armed(self):
        controls=TFTControls('follower',.04,3)
        controls.update(self.IDLE,0)
        controls.update(self.IDLE,.05)
        return controls

    def test_all_three_count_down_then_request_maintenance_once(self):
        controls=self.armed()
        self.assertIsNone(controls.update(self.ALL,1))
        self.assertIsNone(controls.update(self.ALL,1.05))
        self.assertGreater(controls.maintenance_countdown,3.9)
        self.assertIsNone(controls.update(self.ALL,4.99))
        self.assertIsNone(controls.update(self.ALL,5.05))
        self.assertTrue(controls.maintenance_ready)
        self.assertIsNone(controls.update(self.ALL,6))
        self.assertIsNone(controls.update(self.IDLE,6.1))
        self.assertEqual(controls.update(self.IDLE,6.15),'maintenance')
        self.assertIsNone(controls.update(self.IDLE,6.2))
        self.assertEqual(controls.countdown,0)

    def test_release_cancels_and_suppresses_individual_short_press(self):
        controls=self.armed()
        controls.update(self.ALL,1)
        controls.update(self.ALL,1.05)
        self.assertIsNone(controls.update((True,True,True),2))
        self.assertIsNone(controls.update(self.IDLE,2.1))
        self.assertIsNone(controls.update(self.IDLE,2.2))
        self.assertEqual(controls.maintenance_countdown,0)
        controls.update((False,False,False),3)
        controls.update((False,False,False),3.05)
        controls.update(self.IDLE,3.2)
        self.assertEqual(controls.update(self.IDLE,3.25),'page')

    def test_trial_blocks_chord_and_single_button_sleep_unchanged(self):
        controls=self.armed()
        for now in (1,1.05,5.1):
            self.assertIsNone(controls.update(self.ALL,now,allow_maintenance=False))
        self.assertEqual(controls.maintenance_countdown,0)
        controls=self.armed()
        for now in (1,1.05,3.99):self.assertIsNone(controls.update((False,False,False),now))
        self.assertEqual(controls.update((False,False,False),4.05),'sleep')

    def test_tft_chord_is_local_and_requests_reset_without_radio_command(self):
        app=load_app()
        buttons=app.TFTButtons.__new__(app.TFTButtons)
        buttons.inputs=[SimpleNamespace(value=v) for v in self.IDLE]
        buttons.logic=TFTControls('follower',.04,3)
        radio=Mock();animation=Mock();sleep=SleepTransition()
        def poll(now,levels):
            for pin,value in zip(buttons.inputs,levels):pin.value=value
            buttons.poll(animation,now,sleep,radio=radio)
        with patch.object(app,'DISPLAY',None):
            for now in (0,.05):poll(now,self.IDLE)
            for now in (1,1.05,4.99,5.05,6):poll(now,self.ALL)
            poll(6.1,self.IDLE)
            with self.assertRaises(app.MaintenanceRequested):poll(6.15,self.IDLE)
        radio.request_control.assert_not_called()
        animation.set_effect.assert_not_called()
        self.assertIsNone(sleep.started)

    def test_local_reset_runs_after_app_unwinds(self):
        app=load_app()
        class Reset(BaseException):pass
        with patch.object(app,'run_follower',side_effect=app.MaintenanceRequested), \
             patch('hardware.reset_into_maintenance',side_effect=Reset) as reset:
            with self.assertRaises(Reset):app.main()
        reset.assert_called_once()

    def test_failed_maintenance_marker_resumes_app_without_ota_rollback(self):
        app=load_app()
        class Stop(BaseException):pass
        with patch.object(app,'run_follower',side_effect=[app.MaintenanceRequested(),Stop]) as run, \
             patch('hardware.reset_into_maintenance',side_effect=ValueError('NVM unavailable')) as reset:
            with self.assertRaises(Stop):app.main()
        self.assertEqual(run.call_count,2)
        reset.assert_called_once()

    def test_old_base_shows_update_needed_without_reset(self):
        app=load_app()
        buttons=app.TFTButtons.__new__(app.TFTButtons)
        buttons.inputs=[SimpleNamespace(value=v) for v in self.IDLE]
        buttons.logic=TFTControls('follower',.04,3)
        display=Mock(failed=False)
        display.button_activity.return_value=False
        with patch.object(app,'DISPLAY',display), \
             patch('hardware.reset_into_maintenance',None):
            for now,levels in ((0,self.IDLE),(.05,self.IDLE),(1,self.ALL),
                               (1.05,self.ALL),(5.05,self.ALL),(5.1,self.IDLE),
                               (5.15,self.IDLE)):
                for pin,value in zip(buttons.inputs,levels):pin.value=value
                buttons.poll(Mock(),now,SleepTransition(),radio=Mock())
        display.set_banner.assert_called_once_with('BASE UPDATE NEEDED',5.15)


class SleepProtocolTests(unittest.TestCase):
    def setUp(self):
        self.c=Config();self.a=CulvertAnimation(self.c);self.f=AudioFeatures()
        self.tx=Transmitter(self.c,123);self.rx=Receiver(self.c)
        self.sleep=SleepTransition();self.sleep.request(10,3)

    def feature(self,now):
        return self.rx.accept(self.rx.leader,self.tx.encode(self.f,self.a,now),now)

    def command(self,now):
        return self.tx.encode_sleep(self.sleep,now)

    def test_lost_start_catches_up_and_duplicates_never_restart_fade(self):
        self.feature(10)
        self.command(10.1)  # Lost.
        self.feature(11)
        packet=self.command(11.1)
        self.assertEqual(len(packet),SLEEP_SIZE)
        self.assertTrue(self.rx.accept(self.rx.leader,packet,11.1))
        self.assertAlmostEqual(self.rx.sleep.started,10,delta=.002)
        self.assertFalse(self.rx.accept(self.rx.leader,packet,11.2))
        self.feature(12)
        self.assertTrue(self.rx.accept(self.rx.leader,self.command(12.1),12.1))
        self.assertAlmostEqual(self.rx.sleep.started,10,delta=.002)
        self.assertTrue(self.rx.sleep.done(13.01))
        # Packet loss after the command does not cancel the irreversible fade.
        self.rx.fade_if_lost(20,.1)
        self.assertTrue(self.rx.sleep.done(20))

    def test_fresh_feature_required_and_malformed_commands_cannot_sleep(self):
        self.assertFalse(self.rx.accept(self.rx.leader,self.command(10),10))
        self.feature(10)
        self.assertFalse(self.rx.accept(b'badmac',self.command(10.1),10.1))
        packet=self.command(10.2)
        fields=list(struct.unpack(SLEEP_FORMAT,packet))
        for index,bad in ((0,b'NOPE'),(1,2),(2,999),(3,456),(5,4000),(6,0),(6,10001)):
            changed=fields[:];changed[index]=bad
            self.assertFalse(self.rx.accept(self.rx.leader,struct.pack(SLEEP_FORMAT,*changed),10.2))
        self.assertFalse(self.rx.accept(self.rx.leader,packet[:-1],10.2))
        self.assertFalse(self.rx.accept(self.rx.leader,packet,11))  # Stale feature session.
        self.assertIsNone(self.rx.sleep.started)

    def test_sequence_wrap_and_reset_require_current_session(self):
        self.tx.sequence=65534;self.feature(10)
        self.assertTrue(self.rx.accept(self.rx.leader,self.command(10.1),10.1))
        self.assertEqual(self.rx.sequence,0)
        self.assertTrue(self.feature(10.2))
        new=Receiver(self.c)
        self.assertFalse(new.accept(new.leader,self.command(10.3),10.3))

    def test_red_fade_and_black_are_independent_of_audio_and_capped(self):
        s=self.sleep
        self.assertEqual(s.pixels(10,self.c),bytes((0,38,0))*32)
        self.assertEqual(s.pixels(11.5,self.c),bytes((0,19,0))*32)
        self.assertFalse(s.done(12.99));self.assertTrue(s.done(13))
        self.assertEqual(s.pixels(13,self.c),bytes(96))
        self.assertFalse(s.request(12,3));self.assertEqual(s.started,10)

    def test_alternating_control_and_features_preserves_single_outstanding_send(self):
        cls=wireless_class();link=cls.__new__(cls)
        link.c=self.c;link.radio=Mock(send_success=0,send_failure=0)
        link.transmitter=self.tx;link.peer=object();link.next_send=0
        link.pending=False;link.completed=0;link.sleep_turn=True
        link.skipped=link.sent=link.errors=0
        link.publish(self.f,self.a,10,self.sleep)
        link.publish(self.f,self.a,10.1,self.sleep)  # Send still pending.
        self.assertEqual(link.skipped,1)
        link.radio.send_success=1
        link.publish(self.f,self.a,10.2,self.sleep)
        link.radio.send_success=2
        link.publish(self.f,self.a,10.3,self.sleep)
        self.assertEqual([call.args[0][:4] for call in link.radio.send.call_args_list],
                         [b'DGRS',b'DGRD',b'DGRS'])


def load_app():
    spec=importlib.util.spec_from_file_location('sleep_test_app',Path(__file__).parents[1]/'lights_app.py')
    app=importlib.util.module_from_spec(spec)
    modules={'board':SimpleNamespace(board_id='adafruit_feather_esp32_v2',D32=32),
             'digitalio':MagicMock(),'neopixel_write':SimpleNamespace(neopixel_write=Mock())}
    with patch.dict(sys.modules,modules):spec.loader.exec_module(app)
    return app


class ShutdownTests(unittest.TestCase):
    def test_no_wake_alarms_watchdog_off_and_no_ota_failure_exception(self):
        app=load_app()
        class DeepSleep(BaseException):pass
        alarm=Mock();alarm.exit_and_deep_sleep_until_alarms.side_effect=DeepSleep
        mcu=SimpleNamespace(watchdog=SimpleNamespace(mode='reset'))
        supervisor=SimpleNamespace(runtime=SimpleNamespace(autoreload=True))
        wifi=SimpleNamespace(radio=SimpleNamespace(enabled=True))
        with patch.dict(sys.modules,{'alarm':alarm,'microcontroller':mcu,'supervisor':supervisor,'wifi':wifi}), \
             patch.object(app,'run_follower',side_effect=app.SleepRequested):
            with self.assertRaises(DeepSleep):app.main()
        self.assertIsNone(mcu.watchdog.mode);self.assertFalse(wifi.radio.enabled)
        self.assertFalse(supervisor.runtime.autoreload)
        pin=app.digitalio.DigitalInOut.return_value
        app.digitalio.DigitalInOut.assert_called_once_with(app.PIXEL_PIN)
        pin.switch_to_output.assert_called_once_with(value=False)
        app.neopixel_write.assert_called_once_with(pin,bytes(96))
        self.assertFalse(pin.value)
        pin.deinit.assert_not_called()  # DeepSleepRequest must not release the hold.
        alarm.exit_and_deep_sleep_until_alarms.assert_called_once_with(preserve_dios=(pin,))
        self.assertFalse(issubclass(app.SleepRequested,Exception))

    def test_follower_blacks_out_and_deinitializes_radio_before_sleep(self):
        app=load_app();rx=Receiver(Config());rx.sleep.request(0,3)
        link=Mock(receiver=rx);link.receive.return_value=AudioFeatures()
        health=Mock(trial=False)
        with patch.dict(sys.modules,{'wireless':SimpleNamespace(Wireless=lambda _:link)}), \
             patch.object(app.time,'monotonic',return_value=4):
            with self.assertRaises(app.SleepRequested):app.run_follower(health)
        self.assertEqual(app.neopixel_write.call_args.args[1],bytes(96))
        link.deinit.assert_called_once();health.assert_called_once()

    def test_trial_does_not_sleep_or_trigger_rollback(self):
        app=load_app();rx=Receiver(Config());rx.sleep.request(0,3)
        link=Mock(receiver=rx);link.receive.return_value=AudioFeatures()
        class TrialConfirmed(Exception):pass
        health=Mock(trial=True,side_effect=TrialConfirmed)
        with patch.dict(sys.modules,{'wireless':SimpleNamespace(Wireless=lambda _:link)}), \
             patch.object(app.time,'monotonic',return_value=4):
            with self.assertRaises(TrialConfirmed):app.run_follower(health)
        self.assertIsNone(rx.sleep.started)
        link.deinit.assert_called_once()

    def test_buttons_do_not_change_effect_on_hold_and_trial_stays_awake(self):
        app=load_app()
        for allow in (True,False):
            buttons=app.EffectButtons.__new__(app.EffectButtons)
            pin=SimpleNamespace(value=False)
            buttons.inputs=[(pin,ButtonGesture(.04,3),1)]
            animation=CulvertAnimation(Config());sleep=SleepTransition()
            for now in (0,.05,3,4):buttons.poll(animation,now,sleep,allow_sleep=allow)
            self.assertEqual(animation.effect,0)
            self.assertEqual(sleep.started is not None,allow)
            pin.value=True
            buttons.poll(animation,4.1,sleep,allow_sleep=allow)
            buttons.poll(animation,4.2,sleep,allow_sleep=allow)
            self.assertEqual(animation.effect,0)

    def test_config_rejects_unrepresentable_sleep_times(self):
        for overrides in ({'sleep_fade_s':0},{'sleep_fade_s':11},
                          {'button_sleep_hold_s':.001},{'sleep_fade_s':float('nan')}):
            with self.assertRaises(ValueError):Config(**overrides)

    def test_s3_release_precedes_alarm_and_preserves_power_outputs(self):
        app=load_app()
        self.assertTrue(hasattr(app,'wait_for_wake_release'),'S3 release-before-wake missing')
        calls=[]
        class DeepSleep(BaseException):pass
        alarm=Mock();alarm.exit_and_deep_sleep_until_alarms.side_effect=DeepSleep
        held=(object(),object(),object())
        mcu=SimpleNamespace(watchdog=SimpleNamespace(mode='reset'))
        with patch.object(app,'PROFILE',{'display':True}), \
             patch.object(app,'board',SimpleNamespace(D0=0,D1=1,D2=2)), \
             patch.object(app,'wait_for_wake_release',side_effect=lambda:calls.append('release')), \
             patch('hardware.sleep_power',side_effect=lambda:calls.append('power') or held,create=True), \
             patch.dict(sys.modules,{'alarm':alarm,'microcontroller':mcu,'supervisor':SimpleNamespace(runtime=Mock()),
                                    'wifi':SimpleNamespace(radio=Mock())}):
            with self.assertRaises(DeepSleep):app.enter_deep_sleep()
        self.assertEqual(calls,['release','power'])
        self.assertEqual(alarm.pin.PinAlarm.call_args_list,[
            unittest.mock.call(pin=0,value=False,pull=True),
            unittest.mock.call(pin=1,value=True,pull=True),
            unittest.mock.call(pin=2,value=True,pull=True),
        ])
        preserved=alarm.exit_and_deep_sleep_until_alarms.call_args.kwargs['preserve_dios']
        self.assertEqual(preserved[1:],held)


class TFTInputBiasTests(unittest.TestCase):
    def test_buttons_bias_idle_levels_opposite_pressed_polarity(self):
        app=load_app()
        pins=[Mock(),Mock(),Mock()]
        app.board=SimpleNamespace(D0=0,D1=1,D2=2)
        app.digitalio.DigitalInOut.side_effect=pins
        buttons=app.TFTButtons()
        for pin,pull in zip(pins,(app.digitalio.Pull.UP,app.digitalio.Pull.DOWN,app.digitalio.Pull.DOWN)):
            pin.switch_to_input.assert_called_once_with(pull=pull)
        buttons.deinit()

    def test_release_wait_requires_all_buttons_to_be_stably_released(self):
        app=load_app();app.board=SimpleNamespace(D0=0,D1=1,D2=2)

        class Input:
            def __init__(self, values):
                self.values=iter(values)
                self.pulls=[]
            @property
            def value(self):
                return next(self.values)
            def __enter__(self):
                return self
            def __exit__(self,*args):
                return False
            def switch_to_input(self,**kwargs):
                self.pulls.append(kwargs['pull'])
            def deinit(self):
                pass

        pins=[Input((False,True,True,True)),Input((True,False,False,False)),Input((True,False,False,False))]
        app.digitalio.DigitalInOut.side_effect=pins
        with patch('hardware.TextScreen'), \
             patch.object(app.time,'monotonic',side_effect=[0,.01,.1,.2]):
            app.wait_for_wake_release()
        self.assertEqual([pin.pulls for pin in pins],[[app.digitalio.Pull.UP],
                                                       [app.digitalio.Pull.DOWN],
                                                       [app.digitalio.Pull.DOWN]])
