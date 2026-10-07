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

class PresenceTransportTests(unittest.TestCase):
    def test_heartbeat_requires_recent_audio_and_send_completion(self):
        from config import Config
        from radio_protocol import Receiver
        cls=wireless_class()
        self.assertTrue(hasattr(cls,'heartbeat'), 'consumer heartbeat missing')
        link=cls.__new__(cls);link.c=Config();link.receiver=Receiver(link.c)
        link.radio=Mock(send_success=0,send_failure=0);link.peer=object()
        link.next_presence=0;link.boot_session=7;link.presence_sequence=0
        link.sent=link.skipped=link.errors=0;link.pending=False;link.completed=0
        link.heartbeat(1)
        link.radio.send.assert_not_called()
        link.receiver.session=55;link.receiver.sequence=10
        link.receiver.audio_sequence=10;link.receiver.last_audio=1
        link.heartbeat(1)
        self.assertEqual(link.radio.send.call_count,1)
        self.assertTrue(3.5<=link.next_presence<=4.5)
        link.receiver.last_audio=5;link.heartbeat(5)
        self.assertEqual(link.radio.send.call_count,1)
        link.radio.send_success=1;link.receiver.sleep.request(8,3)
        link.receiver.last_audio=8;link.heartbeat(8)
        self.assertEqual(link.radio.send.call_count,1)

    def test_producer_drain_is_gated_and_bounded(self):
        cls=wireless_class()
        self.assertTrue(hasattr(cls,'receive_presence'), 'producer receive missing')
        link=cls.__new__(cls);link.read_count=0;link.radio=Mock(read_success=0)
        link.presence=Mock();link.transmitter=Mock(sequence=10)
        link.receive_presence(1);link.radio.read.assert_not_called()
        link.radio.read_success=12;link.radio.read.return_value=SimpleNamespace(mac=b'abcdef',msg=b'hello')
        link.receive_presence(2)
        self.assertEqual(link.radio.read.call_count,8)
        self.assertEqual(link.presence.accept.call_count,8)

    def test_initial_heartbeat_delay_is_relative_to_boot_clock(self):
        from config import Config
        cls=wireless_class()
        native=Mock(send_success=0,send_failure=0,read_success=0,peers=[])
        wifi=SimpleNamespace(radio=Mock(mac_address=b'abcdef'),Monitor=Mock(),PowerManagement=SimpleNamespace(NONE=0))
        espnow=SimpleNamespace(Peer=Mock(),ESPNow=Mock(return_value=native))
        with patch.dict(cls.__init__.__globals__,{'wifi':wifi,'espnow':espnow}), \
             patch('time.monotonic',return_value=100),patch.object(cls,'_jitter',return_value=.5):
            link=cls(Config())
        self.assertAlmostEqual(link.next_presence,101.5)
