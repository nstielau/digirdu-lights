import unittest
from effects import SleepTransition
import effects

class ControlsTests(unittest.TestCase):
    def controls(self, role='leader'):
        self.assertTrue(hasattr(effects,'TFTControls'),'TFT controls missing')
        c=effects.TFTControls(role,.04,3)
        c.update((True,False,False),0)
        c.update((True,False,False),.05)
        return c

    def test_polarities_pages_short_effect_and_long_sleep(self):
        c=self.controls()
        self.assertEqual(c.update((False,False,False),1),None)
        c.update((False,False,False),1.05);c.update((True,False,False),1.1)
        self.assertEqual(c.update((True,False,False),1.15),'page')
        c.update((True,True,False),2);c.update((True,True,False),2.05)
        c.update((True,False,False),2.1)
        self.assertEqual(c.update((True,False,False),2.15),'next')
        c.update((True,False,True),3);c.update((True,False,True),3.05)
        self.assertEqual(c.update((True,False,True),6),'sleep')
        self.assertIsNone(c.update((True,False,True),7))

    def test_consumer_cannot_change_group_and_wake_press_ignored(self):
        c=self.controls('follower')
        c.update((True,True,False),1);c.update((True,True,False),1.05)
        c.update((True,False,False),1.1)
        self.assertIsNone(c.update((True,False,False),1.2))
        c=effects.TFTControls('leader',.04,3)
        for t in (0,.05,3,6):self.assertIsNone(c.update((True,False,True),t))
        c.update((True,False,False),7);c.update((True,False,False),7.1)
        c.update((True,False,True),8);c.update((True,False,True),8.1)
        self.assertEqual(c.update((True,False,True),11),'sleep')
        c=self.controls();c.update((True,True,False),1);c.update((True,True,False),1.1)
        self.assertIsNone(c.update((True,True,False),4))
        c.update((True,False,False),5);self.assertIsNone(c.update((True,False,False),5.1))

    def test_release_must_be_stable(self):
        self.assertTrue(hasattr(effects,'ReleaseGate'),'release gate missing')
        g=effects.ReleaseGate(.04)
        for pressed,t in ((True,0),(False,1),(True,1.01),(False,2),(False,2.02)):
            self.assertFalse(g.update(pressed,t))
        self.assertTrue(g.update(False,2.05))
