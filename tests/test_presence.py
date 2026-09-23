import unittest
import radio_protocol as protocol

class PresenceTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(hasattr(protocol, 'PresenceRegistry'), 'presence extension missing')
        self.mac = b'123456'; self.sender = b'abcdef'
        self.registry = protocol.PresenceRegistry(self.mac, 1, 99, capacity=2)

    def packet(self, sequence=1, boot=44, audio=100):
        return protocol.encode_presence(1, self.mac, 99, boot, sequence, audio)

    def test_validation_wrap_duplicate_and_session(self):
        r = self.registry
        self.assertTrue(r.accept(self.sender, self.packet(65535), 0, 101))
        self.assertFalse(r.accept(self.sender, self.packet(65535), 1, 101))
        self.assertTrue(r.accept(self.sender, self.packet(0), 2, 101))
        self.assertTrue(r.accept(self.sender, self.packet(0, 45), 3, 101))
        self.assertFalse(r.accept(self.sender, self.packet(1, 44), 4, 101))
        for packet in (self.packet()[:-1], b'bad',
                       protocol.encode_presence(2,self.mac,99,44,2,100),
                       protocol.encode_presence(1,b'654321',99,44,2,100),
                       protocol.encode_presence(1,self.mac,98,44,2,100),
                       self.packet(4,45,500), self.packet(4,45,65000)):
            self.assertFalse(r.accept(b'ghijkl', packet, 4, 101))
        self.assertFalse(r.accept(b'bad', self.packet(4,45), 4, 101))
        self.assertEqual(r.count(4),1)
        self.assertEqual(protocol.SIZE,51);self.assertEqual(protocol.SLEEP_SIZE,17)

    def test_expiry_capacity_lru_and_actual_sender(self):
        r=self.registry
        for i in range(3):self.assertTrue(r.accept(bytes([i+2])*6,self.packet(),i,101))
        self.assertEqual(len(r.entries),2);self.assertTrue(r.full)
        self.assertNotIn(bytes([2])*6,r.entries)
        self.assertEqual(r.count(11.5),1)
        self.assertEqual(r.count(12.1),0)
