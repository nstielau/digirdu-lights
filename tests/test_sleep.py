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
from effects import ButtonGesture, SleepTransition
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
