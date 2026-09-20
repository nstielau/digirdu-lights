import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from battery import read_battery, BatteryMonitor
from animation import CulvertAnimation
from audio_features import AudioFeatures
from config import Config
from effects import battery_pixels, EFFECT_NAMES
from radio_protocol import Transmitter, Receiver


class BatteryTests(unittest.TestCase):
    def test_adc_divider_and_cleanup_with_wifi_independent_adc1(self):
        adc = Mock(value=40000, reference_voltage=3.3)
        context = Mock()
        context.__enter__ = Mock(return_value=adc)
        context.__exit__ = Mock(return_value=False)
        factory = Mock(return_value=context)
        pin = object()
        modules = {'board': SimpleNamespace(board_id='adafruit_feather_esp32_v2', VOLTAGE_MONITOR=pin),
                   'analogio': SimpleNamespace(AnalogIn=factory)}
        with patch.dict(sys.modules, modules):
            result = read_battery()
        self.assertEqual(result, {'voltage': round(40000 * 3.3 / 65535 * 2, 3), 'status': 'measured'})
        factory.assert_called_once_with(pin)
        context.__exit__.assert_called_once()

    def test_feathers2_never_claims_an_adc_or_mic_pin(self):
        factory = Mock(side_effect=AssertionError('must not touch hardware'))
        with patch.dict(sys.modules, {'board': SimpleNamespace(board_id='unexpectedmaker_feathers2'),
                                     'analogio': SimpleNamespace(AnalogIn=factory)}):
            self.assertEqual(read_battery(), {'voltage': None, 'status': 'unsupported'})
        factory.assert_not_called()

    def test_failed_read_replaces_previous_voltage_and_polling_is_bounded(self):
        monitor = BatteryMonitor(2)
        with patch('battery.read_battery', side_effect=[{'voltage': 3.9, 'status': 'measured'},
                                                       {'voltage': None, 'status': 'read_error'}]) as read:
            self.assertEqual(monitor.update(0)['voltage'], 3.9)
            self.assertEqual(monitor.update(1.9)['voltage'], 3.9)
            self.assertIsNone(monitor.update(2)['voltage'])
            self.assertEqual(read.call_count, 2)

    def test_out_of_range_and_hardware_errors_are_not_zero_volts(self):
        for raw in (0, 65535, float('nan')):
            context=Mock();context.__enter__=Mock(return_value=SimpleNamespace(value=raw,reference_voltage=3.3))
            context.__exit__=Mock(return_value=False)
            with patch.dict(sys.modules, {'board':SimpleNamespace(board_id='adafruit_feather_esp32_v2',VOLTAGE_MONITOR=35),
                                         'analogio':SimpleNamespace(AnalogIn=lambda _:context)}):
                self.assertEqual(read_battery(), {'voltage': None, 'status': 'out_of_range'})
        with patch.dict(sys.modules, {'board':SimpleNamespace(board_id='adafruit_feather_esp32_v2',VOLTAGE_MONITOR=35),
                                     'analogio':SimpleNamespace(AnalogIn=Mock(side_effect=RuntimeError('busy')))}):
            self.assertEqual(read_battery(), {'voltage':None,'status':'read_error'})

    def test_last_effect_is_local_and_visible_in_silence_after_radio_loss(self):
        self.assertEqual(EFFECT_NAMES[-1], 'Battery')
        c=Config(effect_index=5);a=CulvertAnimation(c);b=CulvertAnimation(c)
        a.battery_voltage=3.3;b.battery_voltage=4.2
        f=AudioFeatures()
        self.assertNotEqual(a.render(f,.1),b.render(f,.1))
        # Source voltage is not part of the feature packet; destination owns it.
        tx=Transmitter(c,1);rx=Receiver(c)
        self.assertTrue(rx.accept(bytes.fromhex(c.leader_mac.replace(':','')),tx.encode(f,a,0),0))
        b.set_effect(rx.effect)
        rx.fade_if_lost(10,1)
        self.assertEqual(b.battery_voltage,4.2)
        self.assertTrue(any(b.render(rx.features,.1)))
        b.set_effect(0);self.assertEqual(b.effect,0)

    def test_persistent_gauge_unknown_rotation_and_brightness(self):
        c=Config()
        empty=battery_pixels(3.3,c);full=battery_pixels(4.2,c);unknown=battery_pixels(None,c)
        count=lambda p:sum(any(p[i:i+3]) for i in range(0,len(p),3))
        self.assertEqual(count(full)-count(empty),10)
        self.assertNotEqual(unknown,empty)
        animation=CulvertAnimation(Config(effect_index=5))
        animation.battery_voltage=3.9
        expected=battery_pixels(3.9,c)
        # The gauge persists beyond the former scrolling interval.
        for _ in range(120):
            self.assertEqual(animation.render(AudioFeatures(),.5),expected)
        self.assertLessEqual(max(expected),7)
        from effects import FEATHERWING_PORTRAIT as mapping
        rotated=battery_pixels(4.2,Config(effect_indicator_rotation=180))
        for i in range(32):self.assertEqual(full[mapping[i]*3:mapping[i]*3+3],rotated[mapping[31-i]*3:mapping[31-i]*3+3])
        self.assertEqual(battery_pixels(4.2,Config(pixel_count=64)),full*2)
        self.assertEqual(battery_pixels(4.2,Config(pixel_count=2)),bytes(6))

    def test_report_uses_fresh_local_snapshot(self):
        from ota_bootstrap import report_body
        cfg={'id':'test','board':'adafruit_feather_esp32_v2','role':'consumer'}
        store=SimpleNamespace(state={'outcome':'current','floor':11,'error':''})
        reading={'voltage':3.85,'status':'measured'}
        with patch('ota_bootstrap.read_battery',return_value=reading) as read:
            self.assertEqual(report_body(store,cfg,'1.0.7','session',1)['battery'],reading)
            read.assert_called_once()
