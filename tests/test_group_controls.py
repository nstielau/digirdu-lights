import unittest
import radio_protocol as p
from config import Config
from animation import CulvertAnimation
from audio_features import AudioFeatures

class ControlProtocolTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(hasattr(p,'ControlClient'),'control protocol missing')
        self.c=Config();self.rx=p.Receiver(self.c)
        self.tx=p.Transmitter(self.c,99)
        self.rx.accept(self.rx.leader,self.tx.encode(AudioFeatures(),CulvertAnimation(self.c),1),1)
        self.client=p.ControlClient(self.c,b'client',44)
        self.registry=p.ControlRegistry(self.rx.leader,self.c.radio_group,99,capacity=2,max_lag=64)

    def request(self,command=1,now=1):
        self.assertTrue(self.client.request(command,self.rx,now))
        return self.client.packet(now,self.rx)

    def test_retry_is_same_id_and_duplicate_applies_once(self):
        msg=self.request()
        first=self.registry.accept(b'client',msg,1,1)
        self.assertEqual(first,(1,44,1,True))
        retry=self.client.packet(1.3,self.rx)
        self.assertEqual(msg,retry)
        self.assertEqual(self.registry.accept(b'client',retry,1.3,1),(1,44,1,False))
        ack=p.encode_control_ack(self.c.radio_group,99,b'client',44,1,0)
        self.assertFalse(self.client.accept(b'wrong!',ack,self.rx,1.4))
        self.assertTrue(self.client.accept(self.rx.leader,ack,self.rx,1.4))
        self.assertIsNone(self.client.packet(1.6,self.rx))

    def test_freshness_timeout_wrong_targets_and_session(self):
        msg=self.request()
        for index in (0,4,5,7,13):
            bad=bytearray(msg);bad[index]^=1
            self.assertIsNone(self.registry.accept(b'client',bad,1,1))
        self.assertIsNone(self.registry.accept(b'bad',msg,1,1))
        self.assertIsNone(self.registry.accept(b'client',msg,1,100))
        self.assertIsNone(self.client.packet(4,self.rx))
        self.assertEqual(self.client.message,'NO RESPONSE')
        self.assertFalse(self.client.request(2,self.rx,4))
        self.assertEqual(self.client.message,'NO PRODUCER')

    def test_pending_bound_session_change_and_denial(self):
        msg=self.request(2)
        self.assertFalse(self.client.request(1,self.rx,1.1))
        ack=p.encode_control_ack(self.c.radio_group,99,b'client',44,1,1)
        self.assertTrue(self.client.accept(self.rx.leader,ack,self.rx,1.2))
        self.assertEqual(self.client.message,'SLEEP BLOCKED')
        self.rx.last_audio=2
        self.assertTrue(self.client.request(1,self.rx,2))
        self.rx.session=100
        self.assertIsNone(self.client.packet(2.3,self.rx))
        self.assertEqual(self.client.message,'PRODUCER RESET')

    def test_capacity_duplicates_expire_and_sequence_wrap(self):
        for i in range(2):
            msg=p.encode_control(self.c.radio_group,self.rx.leader,99,44,65535,1,1)
            self.assertIsNotNone(self.registry.accept(bytes([i+2])*6,msg,i,1))
        self.assertEqual(len(self.registry.entries),2)
        self.assertIsNone(self.registry.accept(bytes([4])*6,msg,2,1))
        sender=bytes([3])*6
        msg=p.encode_control(self.c.radio_group,self.rx.leader,99,44,0,1,2)
        self.assertEqual(self.registry.accept(sender,msg,3,1),(2,44,0,True))
        self.assertIsNone(self.registry.accept(sender,msg,20,100))

class GroupTransportTests(unittest.TestCase):
    def test_retried_consumer_request_changes_producer_once_and_ack_retries(self):
        from test_wireless import wireless_class
        from unittest.mock import Mock
        from types import SimpleNamespace
        from effects import SleepTransition
        c=Config();link=wireless_class().__new__(wireless_class())
        link.c=c;link.read_count=0;link.transmitter=p.Transmitter(c,99)
        link.controls=p.ControlRegistry(b'leader',c.radio_group,99)
        link.presence=Mock();link.ack=None;link.boot_session=99
        msg=p.encode_control(c.radio_group,b'leader',99,44,1,0,p.NEXT_EFFECT)
        link.radio=Mock(read_success=2)
        link.radio.read.return_value=SimpleNamespace(mac=b'client',msg=msg)
        animation=CulvertAnimation(c);sleep=SleepTransition()
        link.receive_presence(1,animation,sleep)
        self.assertEqual(animation.effect,1)
        self.assertEqual(link.ack[:4],b'DGRA')
        msg=p.encode_control(c.radio_group,b'leader',99,44,2,0,p.GROUP_SLEEP)
        link.radio.read_success=3;link.radio.read.return_value.msg=msg
        link.receive_presence(2,animation,sleep,allow_sleep=False)
        self.assertIsNone(sleep.started)
        link.radio.read_success=4
        link.receive_presence(2.1,animation,sleep,allow_sleep=True)
        self.assertIsNone(sleep.started) # Same denied request remains denied.
        msg=p.encode_control(c.radio_group,b'leader',99,44,3,0,p.GROUP_SLEEP)
        link.radio.read_success=5;link.radio.read.return_value.msg=msg
        link.receive_presence(3,animation,sleep)
        self.assertEqual(sleep.started,3)

class GroupButtonTests(unittest.TestCase):
    def test_consumer_routes_buttons_to_radio_without_local_change_or_sleep(self):
        from test_sleep import load_app
        from unittest.mock import Mock,patch
        from types import SimpleNamespace
        from effects import SleepTransition
        app=load_app();buttons=app.TFTButtons.__new__(app.TFTButtons)
        buttons.inputs=[];buttons.logic=Mock();radio=Mock();animation=Mock();sleep=SleepTransition()
        with patch.object(app,'CONFIG',SimpleNamespace(radio_role='follower',sleep_fade_s=3)):
            buttons.logic.update.return_value='next'
            buttons.poll(animation,1,sleep,radio=radio)
            radio.request_control.assert_called_with(p.NEXT_EFFECT,1)
            animation.set_effect.assert_not_called()
            buttons.logic.update.return_value='sleep'
            buttons.poll(animation,2,sleep,radio=radio)
            radio.request_control.assert_called_with(p.GROUP_SLEEP,2)
            self.assertIsNone(sleep.started)
            radio.reset_mock();buttons.poll(animation,3,sleep,radio=radio,allow_sleep=False)
            radio.request_control.assert_not_called()

class SleepScreenTests(unittest.TestCase):
    def test_sleep_overlay_owns_full_screen_and_release_restores_page(self):
        import dashboard as d
        from unittest.mock import Mock
        self.assertTrue(hasattr(d,'sleep_overlay'),'full-screen sleep missing')
        hold=d.sleep_overlay(holding=2.7)
        self.assertEqual(hold,('HOLD TO SLEEP','3','Release to cancel'))
        fade=d.sleep_overlay(remaining=1.7)
        self.assertEqual(fade,('SLEEPING','2','Group shutdown'))
        state=d.snapshot('consumer',0,overlay=hold)
        for page in (0,1):
            content=d.page_content(state,page)
            self.assertEqual(set(content),{'sleep_title','sleep_number','sleep_detail'})
        ui=d.Dashboard(Mock(pending=False));ui.page=1;ui.next_refresh=100
        ui.set_overlay(hold);self.assertEqual(ui.next_refresh,0)
        ui.set_overlay(None);self.assertEqual(ui.page,1)
        self.assertIsNone(d.sleep_overlay(holding=0))

class ControlTransportBoundsTests(unittest.TestCase):
    def test_acknowledgments_leave_audio_slots_and_native_send_is_bounded(self):
        from test_wireless import wireless_class
        from unittest.mock import Mock
        c=Config();link=wireless_class().__new__(wireless_class())
        link.c=c;link.radio=Mock(send_success=0,send_failure=0)
        link.peer=object();link.transmitter=p.Transmitter(c,99)
        link.next_send=0;link.pending=False;link.completed=0;link.sleep_turn=True
        link.sent=link.errors=link.skipped=0;link.ack_turn=True
        link.ack=b'DGRA';a=CulvertAnimation(c);f=AudioFeatures()
        link.publish(f,a,1)
        link.ack=b'DGRA';link.publish(f,a,1.1)
        self.assertEqual(link.radio.send.call_count,1)
        link.radio.send_success=1;link.publish(f,a,1.2)
        link.radio.send_success=2;link.publish(f,a,1.3)
        self.assertEqual([x.args[0][:4] for x in link.radio.send.call_args_list],
                         [b'DGRA',b'DGRD',b'DGRA'])

    def test_lost_sleep_start_reaches_both_consumers_through_producer(self):
        from effects import SleepTransition
        c=Config();tx=p.Transmitter(c,99);a=CulvertAnimation(c);f=AudioFeatures()
        consumers=[p.Receiver(c),p.Receiver(c)]
        initial=tx.encode(f,a,1)
        for rx in consumers:self.assertTrue(rx.accept(rx.leader,initial,1))
        client=p.ControlClient(c,b'client',44)
        client.request(p.GROUP_SLEEP,consumers[0],1)
        registry=p.ControlRegistry(consumers[0].leader,c.radio_group,99)
        command=registry.accept(b'client',client.packet(1,consumers[0]),1,tx.sequence)
        self.assertEqual(command[0],p.GROUP_SLEEP)
        sleep=SleepTransition();sleep.request(1,3)
        tx.encode_sleep(sleep,1.1) # lost command
        audio=tx.encode(f,a,1.3)
        for rx in consumers:rx.accept(rx.leader,audio,1.3)
        packet=tx.encode_sleep(sleep,1.4)
        for rx in consumers:
            self.assertTrue(rx.accept(rx.leader,packet,1.4))
            self.assertAlmostEqual(rx.sleep.started,1,delta=.002)
            self.assertTrue(rx.sleep.done(4.01))

class SleepRenderProgressTests(unittest.TestCase):
    def test_countdown_completes_under_tight_budget_without_restarting_each_digit(self):
        import dashboard as d
        from unittest.mock import Mock,patch
        backend=d.TFTBackend.__new__(d.TFTBackend)
        backend.front=object();backend.back=object();backend.pending=False
        backend.page=None;backend.row=135;backend.overlay=None
        backend._prepare=Mock();backend.blit=Mock();backend.display=Mock()
        ui=d.Dashboard(backend);completed=0
        for step in range(90):
            now=step*.032
            overlay=d.sleep_overlay(holding=3-now)
            ui.set_overlay(overlay)
            ui.cost=.013
            with patch('time.monotonic',side_effect=[now,now+.013]):
                ui.update(now,d.snapshot('consumer',0,overlay=overlay),spare=.012)
            if backend.row==135:completed+=1
        self.assertGreater(completed,0)
        self.assertGreaterEqual(max(call.kwargs['y2'] for call in backend.blit.call_args_list),135)
        ui.set_overlay(d.sleep_overlay(remaining=3))
        self.assertFalse(ui.update(4,d.snapshot('consumer',0),spare=0))
