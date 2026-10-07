import unittest
from unittest.mock import Mock,patch
from config import Config
from animation import CulvertAnimation
from audio_features import AudioFeatures
import radio_protocol as p

class BrightnessTests(unittest.TestCase):
    def test_brightness_packet_recovers_after_loss_and_requires_live_producer(self):
        self.assertTrue(hasattr(p.Transmitter,'encode_brightness'),'brightness replication missing')
        c=Config();a=CulvertAnimation(c);tx=p.Transmitter(c,99);rx=p.Receiver(Config())
        a.set_brightness(.08)
        state=tx.encode_brightness(a)
        self.assertFalse(rx.accept(rx.leader,state,1))
        self.assertTrue(rx.accept(rx.leader,tx.encode(AudioFeatures(),a,1),1))
        tx.encode_brightness(a) # lost
        packet=tx.encode_brightness(a)
        self.assertTrue(rx.accept(rx.leader,packet,1.1))
        self.assertAlmostEqual(rx.brightness,.08)
        self.assertFalse(rx.accept(rx.leader,packet,1.2))
        self.assertFalse(rx.accept(b'wrong!',tx.encode_brightness(a),1.3))
        self.assertFalse(rx.accept(rx.leader,tx.encode_brightness(a),2))
        self.assertEqual(p.SIZE,51)

    def test_brightness_refreshes_spectrum_indicator_and_zero(self):
        self.assertTrue(hasattr(CulvertAnimation,'set_brightness'),'live brightness missing')
        c=Config();a=CulvertAnimation(c);f=AudioFeatures();f.spectrum=(1,)*8
        bright=bytes(a.render(f,.1))
        a.set_brightness(.05);dim=bytes(a.render(f,.1))
        self.assertLess(max(dim),max(bright))
        a.set_effect(1);old=max(a.indicator_pixels)
        a.set_brightness(.02);self.assertLess(max(a.indicator_pixels),old)
        a.set_brightness(0);self.assertEqual(max(a.render(f,.1)),0)
        a.adjust_brightness(-1);self.assertEqual(c.brightness,0)
        a.adjust_brightness(2);self.assertEqual(c.brightness,c.brightness_max)

    def test_brightness_page_labels_value_and_local_cycle(self):
        import dashboard as d
        ui=d.Dashboard(Mock());pages=[]
        for _ in range(4):ui.toggle();pages.append(ui.page)
        self.assertEqual(pages,[1,2,3,0])
        state=d.snapshot('consumer',0,brightness=.08,brightness_max=.15)
        content=d.page_content(state,2)
        self.assertEqual(content['b1'],'+')
        self.assertEqual(content['b2'],'-')
        self.assertEqual(content['effect'],'8%')
        self.assertEqual(content['header'],'BRIGHTNESS')

    def test_short_d2_on_brightness_requests_decrease_and_hold_still_sleeps(self):
        from test_sleep import load_app
        from effects import SleepTransition
        app=load_app();buttons=app.TFTButtons.__new__(app.TFTButtons)
        buttons.inputs=[];buttons.logic=Mock();radio=Mock();animation=Mock();sleep=SleepTransition()
        with patch.object(app,'DISPLAY',Mock(page=2)):
            buttons.logic.update.return_value='next'
            buttons.poll(animation,1,sleep,radio=radio)
            radio.request_control.assert_called_with(p.BRIGHTER,1)
            buttons.logic.update.return_value='decrease'
            buttons.poll(animation,2,sleep,radio=radio)
            radio.request_control.assert_called_with(p.DIMMER,2)
            buttons.logic.update.return_value='sleep'
            buttons.poll(animation,3,sleep,radio=radio)
            radio.request_control.assert_called_with(p.GROUP_SLEEP,3)
            animation.set_effect.assert_not_called()

    def test_periodic_brightness_survives_ack_traffic_and_preserves_audio(self):
        from test_wireless import wireless_class
        c=Config();link=wireless_class().__new__(wireless_class())
        link.c=c;link.radio=Mock(send_success=0,send_failure=0)
        link.peer=object();link.transmitter=p.Transmitter(c,99)
        link.next_send=0;link.pending=False;link.completed=0;link.sleep_turn=True
        link.sent=link.errors=link.skipped=0;link.ack_turn=True;link.next_brightness=0
        a=CulvertAnimation(c);f=AudioFeatures()
        for i in range(20):
            link.radio.send_success=i
            link.ack=b'DGRA'
            link.publish(f,a,i*.1)
        messages=[x.args[0][:4] for x in link.radio.send.call_args_list]
        self.assertGreaterEqual(messages.count(b'DGRB'),3)
        self.assertGreaterEqual(messages.count(b'DGRD'),9)
        self.assertIn(b'DGRA',messages)

    def test_new_session_rejects_old_state_then_updates_render_cache(self):
        from test_wireless import wireless_class
        from types import SimpleNamespace
        c=Config();rx=p.Receiver(c);a=CulvertAnimation(c)
        producer_config=Config();producer=CulvertAnimation(producer_config)
        old=p.Transmitter(producer_config,11);new=p.Transmitter(producer_config,22)
        f=AudioFeatures()
        rx.accept(rx.leader,old.encode(f,producer,1),1)
        producer.set_brightness(.10)
        old_packet=old.encode_brightness(producer)
        link=wireless_class().__new__(wireless_class())
        link.receiver=rx;link.read_count=0;link.radio=Mock(read_success=1)
        link.radio.read.return_value=SimpleNamespace(mac=rx.leader,msg=old_packet)
        link.receive(1.1,a);self.assertEqual(c.brightness,.10)
        rx.accept(rx.leader,new.encode(f,producer,1.2),1.2)
        self.assertFalse(rx.accept(rx.leader,old_packet,1.3))
        producer.set_brightness(.35)
        link.radio.read_success=2
        link.radio.read.return_value.msg=new.encode_brightness(producer)
        link.receive(1.4,a)
        self.assertEqual(c.brightness,.35)
        self.assertAlmostEqual(max(a.spectrum_colors[0]),.35*255)
