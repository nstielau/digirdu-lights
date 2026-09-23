"""Board selection must fail before writing when hardware is unconfigured."""

import unittest
from unittest.mock import Mock, patch

from tools import board


class DeploymentSelectionTests(unittest.TestCase):
    def deploy(self, detected, expected="auto", legacy=False):
        repl = Mock()
        repl.execute.return_value = detected + "\n(name='circuitpython', version=(10, 3, 1))"
        with patch("builtins.print"), patch.object(board, "Repl", return_value=repl), \
                patch.object(board, "deploy_s2") as usb, \
                patch.object(board, "deploy_serial") as serial:
            try:
                board.deploy("test-port", expected, node_config="profile.py", legacy=legacy)
            except RuntimeError:
                usb.assert_not_called()
                serial.assert_not_called()
                repl.restart.assert_not_called()
                raise
            finally:
                repl.serial.close.assert_called_once()
        return repl, usb, serial

    def test_s2_uses_usb_and_explicit_profile(self):
        repl, usb, serial = self.deploy(board.S2_BOARD)
        usb.assert_called_once_with(repl, None, "profile.py")
        serial.assert_not_called()
        repl.restart.assert_called_once_with(board.S2_BOARD, legacy=False)

    def test_v2_uses_shared_serial_app(self):
        repl, usb, serial = self.deploy(board.ESP32_BOARD)
        usb.assert_not_called()
        serial.assert_called_once_with(repl, "profile.py", False)
        repl.restart.assert_called_once_with(board.ESP32_BOARD, legacy=False)

    def test_unknown_board_refused(self):
        with self.assertRaisesRegex(RuntimeError, "No verified wiring profile"):
            self.deploy("another_esp32")

    def test_explicit_model_mismatch_refused(self):
        with self.assertRaisesRegex(RuntimeError, "Wrong board"):
            self.deploy(board.S2_BOARD, expected=board.ESP32_BOARD)

    def test_legacy_requires_v2(self):
        with self.assertRaisesRegex(RuntimeError, "Legacy rainbow"):
            self.deploy(board.S2_BOARD, legacy=True)
        repl, _, serial = self.deploy(board.ESP32_BOARD, legacy=True)
        serial.assert_called_once_with(repl, "profile.py", True)
        repl.restart.assert_called_once_with(board.ESP32_BOARD, legacy=True)

    def test_reverse_tft_uses_native_usb(self):
        name = 'adafruit_feather_esp32s3_reverse_tft'
        repl, usb, serial = self.deploy(name)
        serial.assert_not_called()
        usb.assert_called_once_with(repl, None, 'profile.py', board_id=name)

class ConfigurationTests(unittest.TestCase):
    def test_native_configuration_verified_and_enrollment_locked(self):
        import json
        import tempfile
        from pathlib import Path
        self.assertTrue(hasattr(board,'configure_node'),'host identity setup missing')
        name='adafruit_feather_esp32s3_reverse_tft';uid='123456789abc'
        with tempfile.TemporaryDirectory() as directory:
            drive=Path(directory)
            (drive/'boot_out.txt').write_text('Board ID:'+name+'\nUID:'+uid)
            (drive/'node_config.py').write_text("OVERRIDES = {'brightness': 0.12}\n")
            repl=Mock()
            def execute(code, **kw):
                if 'board.board_id' in code:return repr((name,uid))
                if 'readonly' in code:return 'True'
                if 'OTA_DEVICE_TOKEN' in code:return repr((False,None))
                return ''
            repl.execute.side_effect=execute
            with patch.object(board,'Repl',return_value=repl):
                board.configure_node('port', 'consumer',1,'7c:df:a1:03:4c:2c', directory)
            data=json.loads((drive/'node_state.json').read_text())
            self.assertEqual(data['leader_mac'],'7c:df:a1:03:4c:2c')
            self.assertIn("'brightness': 0.12",(drive/'node_config.py').read_text())
            self.assertIn("'radio_role': 'consumer'",(drive/'node_config.py').read_text())
            repl.execute.side_effect=lambda code,**kw: repr((name,uid)) if 'board.board_id' in code else repr((True,'producer'))
            with patch.object(board,'Repl',return_value=repl):
                with self.assertRaisesRegex(ValueError,'enrolled'):
                    board.configure_node('port','consumer',1,'7c:df:a1:03:4c:2c',directory)

    def test_reverse_tft_uf2_refuses_old_bootloader_before_copy(self):
        import tempfile
        from pathlib import Path
        self.assertTrue(hasattr(board,'flash_native'),'native UF2 selection missing')
        with tempfile.TemporaryDirectory() as directory:
            drive=Path(directory)
            firmware=drive/'adafruit-circuitpython-adafruit_feather_esp32s3_reverse_tft-en_US-10.3.1.uf2'
            firmware.write_bytes(b'fixture')
            (drive/'INFO_UF2.TXT').write_text('TinyUF2 Bootloader 0.32.0\nModel: Adafruit Feather ESP32-S3 Reverse TFT\nBoard-ID: ESP32S3-Feather-revTFT')
            with self.assertRaisesRegex(RuntimeError,'0.33'):
                board.flash_native(firmware,directory,board.S3_BOARD)
            self.assertFalse((drive/'firmware.uf2').exists())

    def test_button_diagnostic_uses_s3_aliases_and_polarity(self):
        import sys
        from types import SimpleNamespace
        from config import Config
        clock=[0]
        def now():clock[0]+=.1;return clock[0]
        pins=[]
        def claim(number):
            pin=Mock(value=number!=0);pins.append((number,pin));return pin
        modules={'board':SimpleNamespace(board_id=board.S3_BOARD,D0=0,D1=1,D2=2),
                 'digitalio':SimpleNamespace(DigitalInOut=claim,Pull=SimpleNamespace(UP=1)),
                 'ota_bootstrap':SimpleNamespace(load_app=lambda:None),
                 'time':SimpleNamespace(monotonic=now,sleep=lambda _:None)}
        with patch.dict(sys.modules,modules),patch('builtins.print') as output:
            exec(board.BUTTON_TEST_SOURCE,{})
        self.assertEqual([number for number,pin in pins],[0,1,2])
        self.assertEqual(sum('accepted press=' in str(call.args) for call in output.call_args_list),3)
        for _,pin in pins:pin.deinit.assert_called_once()
