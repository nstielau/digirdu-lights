import importlib.util
import unittest
from unittest.mock import Mock

class DashboardTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('dashboard'), 'dashboard missing')
        import dashboard
        return dashboard

    def test_units_health_and_left_labels(self):
        d=self.module()
        p=d.snapshot('leader',0,rms=3276.8,volume=.8,clipped=True)
        self.assertEqual(p['level_units'],'dBFS');self.assertAlmostEqual(p['level'],-20)
        self.assertEqual(p['state'],'CLIPPING');self.assertEqual(p['labels'],('PAGE','NEXT','SLEEP'))
        c=d.snapshot('follower',2,volume=.25,age=1)
        self.assertEqual(c['level_units'],'%');self.assertEqual(c['level'],25)
        self.assertEqual(c['state'],'LOST');self.assertEqual(c['labels'][1],'FOLLOW')
        self.assertEqual(d.snapshot('leader',0,calibrating=True)['state'],'CALIBRATING')
        self.assertEqual(d.snapshot('leader',0,fault=True)['state'],'MIC FAULT')
        self.assertEqual(d.snapshot('leader',0)['state'],'QUIET')

    def test_rate_wrap_reset_and_bounded_updates(self):
        d=self.module();r=d.Rate()
        self.assertEqual(r.update(4294967294,0),0)
        self.assertEqual(r.update(2,1),4)
        self.assertEqual(r.update(0,2),0)
        backend=Mock();ui=d.Dashboard(backend,interval=.2)
        state=d.snapshot('leader',0)
        self.assertTrue(ui.update(0,state,spare=.02))
        self.assertFalse(ui.update(.1,state,spare=.02))
        self.assertFalse(ui.update(.3,state,spare=0))
        self.assertTrue(ui.update(.4,state,spare=.02))
        backend.draw.side_effect=RuntimeError('display lost')
        self.assertFalse(ui.update(.7,state,spare=.02))
        self.assertFalse(ui.update(1,state,spare=.02))
        self.assertEqual(backend.draw.call_count,3)
