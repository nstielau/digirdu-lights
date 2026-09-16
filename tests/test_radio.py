"""Wireless protocol replay, loss, event retention and graceful failover tests."""

import struct
import unittest

from config import Config
from audio_features import AudioFeatures
from animation import CulvertAnimation
from radio_protocol import Transmitter, Receiver, FORMAT, SIZE


class RadioTests(unittest.TestCase):
    def setUp(self):
        self.c = Config()
        self.tx = Transmitter(self.c, 123)
        self.rx = Receiver(self.c)
        self.mac = self.rx.leader
        self.f = AudioFeatures()
        self.a = CulvertAnimation(self.c)

    def packet(self, now):
        self.tx.observe(self.f, now)
        return self.tx.encode(self.f, self.a, now)

    def test_round_trip_bounds_and_source_filter(self):
        self.f.drone = 0.8
        self.f.timbrePosition = 0.4
        p = self.packet(0)
        self.assertEqual(len(p), SIZE)
        self.assertLessEqual(SIZE, 250)
        self.assertFalse(self.rx.accept(b'\xff' * 6, p, 0))
        self.assertTrue(self.rx.accept(self.mac, p, 0))
        self.assertAlmostEqual(self.rx.features.drone, 0.8, delta=1/255)
        self.assertAlmostEqual(self.rx.features.timbrePosition, 0.4, delta=1/255)

    def test_duplicates_reordering_sequence_wrap_and_reboot(self):
        self.tx.sequence = 65533
        p1, p2, p3 = self.packet(0), self.packet(.1), self.packet(.2)
        self.assertTrue(self.rx.accept(self.mac, p2, .1))
        self.assertFalse(self.rx.accept(self.mac, p1, .2))
        self.assertFalse(self.rx.accept(self.mac, p2, .2))
        self.assertTrue(self.rx.accept(self.mac, p3, .3))
        self.tx = Transmitter(self.c, 456)
        self.assertTrue(self.rx.accept(self.mac, self.packet(.4), .4))

    def test_event_between_sends_survives_loss_and_is_not_repeated(self):
        self.rx.accept(self.mac, self.packet(0), 0)
        self.f.attackEvent = True
        self.f.attack = .9
        self.tx.observe(self.f, .032)
        self.f.attackEvent = False
        self.packet(.064)  # This packet is lost.
        p = self.packet(.128)
        self.assertTrue(self.rx.accept(self.mac, p, .128))
        self.assertTrue(self.rx.features.attackEvent)
        self.assertAlmostEqual(self.rx.features.attackAge, .096, delta=.001)
        self.rx.clear_events()
        self.rx.accept(self.mac, self.packet(.192), .192)
        self.assertFalse(self.rx.features.attackEvent)

    def test_stale_events_and_startup_do_not_fire(self):
        self.f.yellEvent = True
        self.f.vocal = .8
        self.assertTrue(self.rx.accept(self.mac, self.packet(0), 0))
        self.assertFalse(self.rx.features.yellEvent)
        self.f.yellEvent = False
        self.tx.yell_id += 1
        self.rx.accept(self.mac, self.packet(5), 5)
        self.assertFalse(self.rx.features.yellEvent)

    def test_malformed_packets_and_nan_rejected(self):
        p = self.packet(0)
        for bad in (b'', p[:-1], b'BAD!' + p[4:]):
            self.assertFalse(self.rx.accept(self.mac, bad, 0))
        values = list(struct.unpack(FORMAT, p))
        for index, bad in ((2, 55), (5, float('nan')), (6, float('inf')), (13, 3), (24, 255)):
            altered = values[:]
            altered[index] = bad
            self.assertFalse(self.rx.accept(self.mac, struct.pack(FORMAT, *altered), 0))

    def test_connection_loss_fades_and_reconnects(self):
        self.f.drone = self.f.volume = self.f.decay = 1
        self.f.active = True
        self.rx.accept(self.mac, self.packet(0), 0)
        self.assertFalse(self.rx.fade_if_lost(.2, .032))
        self.assertTrue(self.rx.fade_if_lost(1, .032))
        self.assertFalse(self.rx.features.active)
        self.assertGreater(self.rx.features.drone, .9)
        for _ in range(1000):
            self.rx.fade_if_lost(2, .032)
        self.assertLess(self.rx.features.drone, .001)
        self.rx.accept(self.mac, self.packet(35), 35)
        self.assertEqual(self.rx.features.drone, 1)

    def test_effect_is_repeated_state_and_new_consumers_join(self):
        self.rx.accept(self.mac, self.packet(0), 0)
        self.a.set_effect(2)
        self.packet(.1)  # Effect-change packet is lost.
        packet = self.packet(.2)
        self.rx.accept(self.mac, packet, .2)
        self.assertEqual(self.rx.effect, 2)
        another = Receiver(self.c)
        self.assertTrue(another.accept(self.mac, packet, .2))
        self.assertEqual(another.effect, 2)

    def test_effect_indicator_mirrors_after_loss_without_restarting(self):
        # Different culvert coordinates must not alter the local number display.
        consumer = CulvertAnimation(Config(pixel_positions=tuple((.5, 0) for _ in range(32))))
        self.rx.accept(self.mac, self.packet(0), 0)
        self.a.set_effect(2)
        self.packet(.1)  # First effect-change update is lost.
        self.rx.accept(self.mac, self.packet(.2), .2)
        consumer.set_effect(self.rx.effect)
        self.assertEqual(self.a.render(self.f, .064), consumer.render(self.rx.features, .064))
        for n in range(30):
            self.rx.accept(self.mac, self.packet(.3+n*.064), .3+n*.064)
            consumer.set_effect(self.rx.effect)
            consumer.render(self.rx.features, .064)
        self.assertEqual(consumer.indicator_remaining, 0)


if __name__ == "__main__":
    unittest.main()
