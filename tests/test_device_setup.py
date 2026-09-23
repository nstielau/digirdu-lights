import importlib.util
import unittest

class SetupTests(unittest.TestCase):
    def assessment(self):
        self.assertIsNotNone(importlib.util.find_spec('device_setup'),'guided setup missing')
        from device_setup import MicAssessment
        return MicAssessment(0)

    def test_flat_noise_clipping_variation_and_bounded_duration(self):
        a=self.assessment()
        for t in (1,5,10):a.observe(0,0,0,1024,t)
        self.assertEqual(a.result(10),'FLAT INPUT')
        a=self.assessment()
        for t in (1,5,10):a.observe(50,80,160,1024,t)
        self.assertEqual(a.result(10),'NO LEVEL CHANGE')
        a=self.assessment();a.observe(50,80,160,1000,1)
        self.assertEqual(a.result(10),'CAPTURE FAILED')
        a=self.assessment();a.observe(50,80,160,1024,1);a.observe(5000,32767,65535,1024,5)
        self.assertEqual(a.result(10),'CLIPPING')
        a=self.assessment();a.observe(10,20,40,1024,1);a.observe(100,200,400,1024,5)
        self.assertEqual(a.result(9),'TESTING');self.assertEqual(a.result(10),'CONFIRM RESPONSE')
        self.assertFalse(a.confirmed)
        self.assertTrue(a.confirm(10));self.assertTrue(a.confirmed)
        flat=self.assessment();self.assertFalse(flat.confirm(10))
