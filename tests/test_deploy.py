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
