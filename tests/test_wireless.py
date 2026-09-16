"""ESP-NOW callback completion must precede native receive-buffer reads."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


def wireless_class():
    spec = importlib.util.spec_from_file_location('wireless_test_device', Path(__file__).parents[1] / 'wireless.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'espnow': SimpleNamespace(), 'wifi': SimpleNamespace()}):
        spec.loader.exec_module(module)
    return module.Wireless


class ReceiveCompletionTests(unittest.TestCase):
    def setUp(self):
        cls = wireless_class()
        self.link = cls.__new__(cls)
        self.link.read_count = 0
        self.link.radio = Mock(read_success=0)
        self.link.receiver = Mock(scene_time=2.0, phase=0.25, effect=1)
        self.link.receiver.accept.return_value = True
        self.animation = Mock()

    def test_partial_callback_does_not_read_even_with_buffer_bytes(self):
        self.link.radio.read.side_effect = ValueError('Invalid buffer')
        self.link.receive(1.0, self.animation)
        self.link.radio.read.assert_not_called()
        self.animation.set_effect.assert_not_called()
        self.link.radio.read.side_effect = None
        self.link.radio.read.return_value = SimpleNamespace(mac=b'123456', msg=b'complete')
        self.link.radio.read_success = 1
        self.link.receive(2.0, self.animation)
        self.link.radio.read.assert_called_once()
        self.assertEqual(self.link.read_count, 1)
        self.animation.set_effect.assert_called_once_with(1)

    def test_rejected_packets_are_consumed_and_draining_is_bounded(self):
        self.link.radio.read_success = 12
        self.link.radio.read.return_value = SimpleNamespace(mac=b'wrong!', msg=b'bad')
        self.link.receiver.accept.return_value = False
        self.link.receive(1.0, self.animation)
        self.assertEqual(self.link.read_count, 8)
        self.assertEqual(self.link.radio.read.call_count, 8)
        self.link.receive(2.0, self.animation)
        self.assertEqual(self.link.read_count, 12)
        self.assertEqual(self.link.radio.read.call_count, 12)
        self.animation.set_effect.assert_not_called()

    def test_completed_packet_counter_wraps(self):
        self.link.read_count = 0xffffffff
        self.link.radio.read_success = 0
        self.link.radio.read.return_value = SimpleNamespace(mac=b'123456', msg=b'complete')
        self.link.receive(1.0, self.animation)
        self.assertEqual(self.link.read_count, 0)
        self.link.radio.read.assert_called_once()
