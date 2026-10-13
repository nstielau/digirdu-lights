import importlib.util
import os
import runpy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


class HardwareTests(unittest.TestCase):
    def test_maintenance_marker_is_one_use_and_does_not_change_ota_bytes(self):
        import hardware
        nvm=bytearray(b'DGO1\x01'+bytes(27))
        hardware.set_maintenance_request(nvm)
        self.assertEqual(nvm[:5],b'DGO1\x01')
        self.assertTrue(hardware.consume_maintenance_request(nvm))
        self.assertEqual(nvm[:5],b'DGO1\x01')
        self.assertFalse(hardware.consume_maintenance_request(nvm))

    def test_short_nvm_never_resets_or_claims_maintenance(self):
        import hardware
        nvm=bytearray(8)
        with self.assertRaises(ValueError):hardware.set_maintenance_request(nvm)
        self.assertFalse(hardware.consume_maintenance_request(nvm))

    def test_boot_consumes_chord_request_then_next_full_boot_is_normal(self):
        import hardware
        nvm=bytearray(32)
        hardware.set_maintenance_request(nvm)
        storage=Mock()
        frames=[]
        class Pin:
            value=True  # D0 is released.
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def switch_to_input(self,**kwargs):pass
            def switch_to_output(self,**kwargs):pass
        modules={'board':SimpleNamespace(board_id=hardware.S3,D0=0,D6=6),
                 'storage':storage,
                 'digitalio':SimpleNamespace(DigitalInOut=lambda pin:Pin(),Pull=SimpleNamespace(UP=1)),
                 'microcontroller':SimpleNamespace(nvm=nvm),
                 'neopixel_write':SimpleNamespace(neopixel_write=lambda pin,data:frames.append(bytes(data)))}
        script=str(Path(__file__).parents[1]/'boot.py')
        with patch.dict(os.environ,{'OTA_ENABLED':'1'}),patch.dict(sys.modules,modules), \
             patch('time.monotonic',side_effect=[0,3,0,3]),patch('time.sleep'):
            runpy.run_path(script)
            storage.remount.assert_called_with('/',readonly=True)
            self.assertEqual(frames[0][:3],bytes((3,8,0)))
            self.assertEqual(frames[0][3:],bytes(93))
            storage.reset_mock()
            frames.clear()
            runpy.run_path(script)
        storage.remount.assert_called_with('/',readonly=False)
        self.assertEqual(frames[0],bytes((0,0,12))*32)
        self.assertFalse(hardware.consume_maintenance_request(nvm))

    def test_legacy_buttons_select_orange_maintenance_without_chord(self):
        import hardware
        script=str(Path(__file__).parents[1]/'boot.py')
        for board_id,button,wing in ((hardware.S2,'IO0','IO38'),
                                     (hardware.V2,'BUTTON','D32')):
            with self.subTest(board_id=board_id):
                storage=Mock()
                frames=[]
                class Pin:
                    value=False  # BOOT/IO0 or HUZZAH32 V2 SW38, pressed after reset.
                    def __enter__(self):return self
                    def __exit__(self,*args):pass
                    def switch_to_input(self,**kwargs):pass
                    def switch_to_output(self,**kwargs):pass
                board=SimpleNamespace(board_id=board_id,**{button:0,wing:38})
                modules={'board':board,'storage':storage,
                         'digitalio':SimpleNamespace(DigitalInOut=lambda pin:Pin(),Pull=SimpleNamespace(UP=1)),
                         'neopixel_write':SimpleNamespace(neopixel_write=lambda pin,data:frames.append(bytes(data)))}
                with patch.dict(os.environ,{'OTA_ENABLED':'1'}),patch.dict(sys.modules,modules), \
                     patch('time.monotonic',side_effect=[0,0,3]),patch('time.sleep'):
                    runpy.run_path(script)
                storage.remount.assert_called_once_with('/',readonly=True)
                self.assertEqual(frames[0],bytes((0,0,12))*32)
                self.assertEqual(frames[1][:3],bytes((3,8,0)))
                self.assertEqual(frames[1][3:],bytes(93))
                self.assertEqual(frames[-1],bytes(96))

    def test_disabled_ota_clears_stale_chord_request(self):
        import hardware
        nvm=bytearray(32)
        hardware.set_maintenance_request(nvm)
        modules={'board':SimpleNamespace(board_id=hardware.S3),
                 'storage':Mock(),
                 'microcontroller':SimpleNamespace(nvm=nvm)}
        script=str(Path(__file__).parents[1]/'boot.py')
        with patch.dict(os.environ,{'OTA_ENABLED':'0'}),patch.dict(sys.modules,modules):
            runpy.run_path(script)
        self.assertFalse(hardware.consume_maintenance_request(nvm))

    def test_local_maintenance_reset_marks_nvm_and_stops_watchdog(self):
        import hardware
        class Reset(BaseException):pass
        nvm=bytearray(32)
        mcu=SimpleNamespace(nvm=nvm,watchdog=SimpleNamespace(mode='reset'),
                            reset=Mock(side_effect=Reset))
        with patch.dict(sys.modules,{'microcontroller':mcu}):
            with self.assertRaises(Reset):hardware.reset_into_maintenance()
        self.assertIsNone(mcu.watchdog.mode)
        self.assertEqual(nvm[:5],bytes(5))
        self.assertTrue(hardware.consume_maintenance_request(nvm))
        mcu.reset.assert_called_once()

    def test_failed_reset_clears_request(self):
        import hardware
        nvm=bytearray(32)
        mcu=SimpleNamespace(nvm=nvm,watchdog=SimpleNamespace(mode='reset'),
                            reset=Mock(side_effect=OSError('reset failed')))
        with patch.dict(sys.modules,{'microcontroller':mcu}):
            with self.assertRaises(OSError):hardware.reset_into_maintenance()
        self.assertFalse(hardware.consume_maintenance_request(nvm))

    def test_profiles_and_reserved_pins(self):
        self.assertIsNotNone(importlib.util.find_spec('hardware'), 'shared profiles missing')
        from hardware import profile, validate_pins
        s3 = profile('adafruit_feather_esp32s3_reverse_tft')
        self.assertEqual(s3['wing'], 'D6')
        self.assertEqual(s3['mic'], ('D5', 'D9', 'D6'))
        self.assertEqual(profile('unexpectedmaker_feathers2')['wing'], 'IO38')
        self.assertEqual(profile('adafruit_feather_esp32_v2')['wing'], 'D32')
        for pins in ((5, 6, 10), (5, 9, 9), (35, 9, 10), (0, 9, 10)):
            with self.assertRaises(ValueError): validate_pins(s3, pins)
        with self.assertRaises(ValueError): profile('unknown')

    def test_max17048_voltage_soc_and_unlock(self):
        import battery
        self.assertTrue(hasattr(battery, 'read_gauge'), 'fuel gauge reader missing')
        class Bus:
            unlocked = False
            def try_lock(self): return True
            def unlock(self): self.unlocked = True
            def writeto_then_readfrom(self, address, command, response):
                self_address = 0x36
                assert address == self_address
                value = {8: 0x0012, 2: 48000, 4: 75 * 256}[command[0]]
                response[:] = value.to_bytes(2, 'big')
        bus = Bus()
        with patch.dict(sys.modules, {'board': SimpleNamespace(I2C=lambda: bus)}):
            result = battery.read_gauge()
        self.assertEqual(result, {'status':'measured', 'voltage':3.75, 'percent':75.0})
        self.assertTrue(bus.unlocked)
        bus.try_lock = lambda: False
        with patch.dict(sys.modules, {'board':SimpleNamespace(I2C=lambda: bus)}):
            self.assertEqual(battery.read_gauge()['status'], 'read_error')
        bus.try_lock = lambda: True
        bus.writeto_then_readfrom = lambda a, c, r: r.__setitem__(slice(None), b'\xff\xff')
        with patch.dict(sys.modules, {'board':SimpleNamespace(I2C=lambda: bus)}):
            self.assertEqual(battery.read_gauge()['status'], 'unsupported')

    def test_s3_app_claims_verified_mic_and_wing_only(self):
        import importlib.util
        from pathlib import Path
        from config import Config
        from unittest.mock import MagicMock
        name='adafruit_feather_esp32s3_reverse_tft'
        board=SimpleNamespace(board_id=name,D6=6,D5=5,D9=9,D10=10)
        factory=MagicMock()
        spec=importlib.util.spec_from_file_location('s3_app_test',Path(__file__).parents[1]/'lights_app.py')
        app=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'board':board,'digitalio':MagicMock(),
                       'neopixel_write':SimpleNamespace(neopixel_write=MagicMock()),
                       'audioi2sin':SimpleNamespace(I2SIn=factory)}):
            spec.loader.exec_module(app)
            self.assertEqual(app.PIXEL_PIN,6)
            app.microphone()
        self.assertEqual(factory.call_args.args,(5,9,6))

    def test_capture_failure_is_visible_without_role_change(self):
        from test_sleep import load_app
        app=load_app()
        self.assertTrue(hasattr(app,'show_mic_fault'),'runtime microphone fault screen missing')
        screen=__import__('unittest.mock',fromlist=['Mock']).Mock()
        previous_role=app.CONFIG.radio_role
        with patch.object(app,'PROFILE',{'display':True}),patch('hardware.BootScreen',return_value=screen):
            app.show_mic_fault()
        screen.phase.assert_called_once_with('MIC FAULT - check wiring / reset')
        self.assertEqual(app.CONFIG.radio_role,previous_role)
