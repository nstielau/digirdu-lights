"""Compact RF evidence must survive wrap and remain bounded."""
import unittest

from telemetry import TelemetryRecorder


class RecorderTests(unittest.TestCase):
    def test_consumer_wrap_and_rssi(self):
        r = TelemetryRecorder("consumer", "0123456789abcdef", max_windows=3)
        r.received(7, 65535, -80, False)
        r.received(7, 0, -72, False)
        r.received(7, 1, -76, True)
        view = r.snapshot()
        self.assertEqual([w["base"] for w in view["windows"]], [65280, 65536])
        self.assertEqual(view["counts"]["features"], 2)
        self.assertEqual(view["counts"]["controls"], 1)
        self.assertEqual(view["rssi"], {"min": -80, "max": -72, "mean": -76})
        self.assertTrue(view["epoch_uncertain"])

    def test_producer_send_outcomes_and_skips(self):
        r = TelemetryRecorder("producer", "0123456789abcdef")
        r.attempted(9, 1, False)
        r.completed(9, 1, True)
        r.attempted(9, 2, False)
        r.completed(9, 2, False)
        r.attempted(9, 3, True)
        r.skipped()
        r.audio_overrun()
        r.audio_discontinuity()
        view = r.snapshot()
        w = view["windows"][0]
        self.assertEqual(bytes.fromhex(w["attempted"])[0] & 14, 14)
        self.assertEqual(bytes.fromhex(w["delivered"])[0] & 14, 2)
        self.assertEqual(bytes.fromhex(w["failed"])[0] & 14, 4)
        self.assertEqual(bytes.fromhex(w["controls"])[0] & 14, 8)
        self.assertEqual(view["counts"]["skipped"], 1)
        self.assertEqual(view["counts"]["audio_overruns"], 1)
        self.assertEqual(view["counts"]["audio_discontinuities"], 1)

    def test_bounded_windows_and_native_drop_delta(self):
        r = TelemetryRecorder("consumer", "0123456789abcdef", max_windows=2)
        for seq in (1, 257, 513):
            r.received(3, seq, None, False)
        r.native_failures(0xfffffffe)
        r.native_failures(1)
        r.rejected()
        r.link_lost(True)
        r.link_lost(True)
        r.link_lost(False)
        self.assertEqual(len(r.snapshot()["windows"]), 2)
        self.assertEqual(r.snapshot()["truncated_windows"], 1)
        self.assertEqual(r.snapshot()["counts"]["native_drops"], 3)
        self.assertEqual(r.snapshot()["counts"]["rejected"], 1)
        self.assertEqual(r.snapshot()["counts"]["link_losses"], 1)


if __name__ == "__main__":
    unittest.main()
