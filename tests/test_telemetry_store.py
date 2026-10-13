import json
from pathlib import Path
import tempfile
import unittest

from telemetry_store import TelemetryQueue, read_attempt, write_attempt


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = self.temp.name + '/telemetry'
        self.queue = TelemetryQueue(self.path, sync=lambda: None)
        self.sample = {"schema": 1, "role": "consumer", "boot_id": "0123456789abcdef",
                       "windows": [], "counts": {}, "truncated_windows": 0,
                       "epoch_uncertain": False, "rssi": None}

    def test_acknowledged_upload_only_deletes_matching_batch(self):
        batch = self.queue.enqueue('0123456789abcdef', self.sample)
        self.assertEqual(self.queue.flush(lambda b: {"accepted": "wrong"}), 0)
        self.assertEqual(len(self.queue.pending()), 1)
        self.assertEqual(self.queue.flush(lambda b: {"accepted": b['batch_id']}), 1)
        self.assertEqual(self.queue.pending(), [])
        self.assertEqual(batch['device_id'], '0123456789abcdef')

    def test_failed_upload_and_reopen_retry_keep_stable_id(self):
        batch = self.queue.enqueue('0123456789abcdef', self.sample)
        with self.assertRaises(OSError):
            self.queue.flush(lambda _: (_ for _ in ()).throw(OSError('offline')))
        reopened = TelemetryQueue(self.path, sync=lambda: None)
        self.assertEqual(reopened.pending()[0]['batch_id'], batch['batch_id'])
        self.assertEqual(reopened.flush(lambda b: {"accepted": b['batch_id']}), 1)

    def test_temporary_and_corrupt_files_do_not_block_queue(self):
        Path(self.path, 'orphan.tmp').write_text('{')
        Path(self.path, 'bad.json').write_text('{')
        self.assertEqual(self.queue.pending(), [])
        self.assertEqual(self.queue.flush(lambda _: None), 0)

    def test_queue_is_bounded_and_preserves_newest(self):
        ids = [self.queue.enqueue('0123456789abcdef', self.sample)['batch_id'] for _ in range(5)]
        self.assertEqual([b['batch_id'] for b in self.queue.pending()], ids[1:])

    def test_attempt_status_survives_reopen_and_does_not_enter_batch_queue(self):
        self.queue.enqueue('0123456789abcdef',self.sample)
        write_attempt('failed','Wi-Fi',1,root=self.path,sync=lambda:None)
        self.assertEqual(read_attempt(self.path),{'state':'failed','reason':'Wi-Fi','pending':1})
        self.assertEqual(len(TelemetryQueue(self.path,sync=lambda:None).pending()),1)
        write_attempt('uploaded','',0,root=self.path,sync=lambda:None)
        self.assertEqual(read_attempt(self.path),{'state':'uploaded','reason':'','pending':0})

    def test_attempt_status_rejects_corrupt_and_unbounded_content(self):
        self.assertIsNone(read_attempt(self.path))
        with self.assertRaises(ValueError):
            write_attempt('failed','x'*80,1,root=self.path,sync=lambda:None)
        Path(self.path,'status.json').write_text('{')
        self.assertIsNone(read_attempt(self.path))


if __name__ == '__main__':
    unittest.main()
