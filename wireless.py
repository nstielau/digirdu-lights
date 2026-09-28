"""CircuitPython ESP-NOW transport for one mic leader and wireless LED nodes."""

import os
import time

import espnow
import wifi

from radio_protocol import (Transmitter, Receiver, PresenceRegistry, encode_presence,
                            ControlClient, ControlRegistry, encode_control_ack,
                            NEXT_EFFECT, GROUP_SLEEP, BRIGHTER, DIMMER)
from effects import EFFECT_NAMES


class Wireless:
    def __init__(self, config):
        self.c = config
        # No AP association or router. Monitor sets the common radio channel;
        # it is immediately released before ESP-NOW registers its callbacks.
        wifi.radio.enabled = True
        wifi.radio.start_station()
        wifi.radio.power_management = wifi.PowerManagement.NONE
        monitor = wifi.Monitor(channel=config.radio_channel)
        monitor.deinit()
        self.local_mac = bytes(wifi.radio.mac_address)
        self.radio = espnow.ESPNow(buffer_size=2048)
        self.peer = espnow.Peer(mac=b"\xff" * 6, channel=config.radio_channel)
        self.radio.peers.append(self.peer)
        self.boot_session = int.from_bytes(os.urandom(4), "little")
        self.presence_sequence = 0
        self.next_presence = time.monotonic() + self._jitter() * config.presence_interval_s
        self.presence = None
        self.transmitter = None
        self.receiver = None
        self.next_send = 0.0
        self.sent = self.errors = self.skipped = 0
        self.sleep_turn = True
        self.pending = False
        self.completed = 0
        self.read_count = 0
        self.control = None
        self.controls = None
        self.ack = None
        self.ack_turn = True
        self.next_brightness = time.monotonic() + config.brightness_interval_s
        if config.radio_role == "leader":
            self.transmitter = Transmitter(config, self.boot_session)
            self.presence = PresenceRegistry(wifi.radio.mac_address, config.radio_group,
                                             self.boot_session, config.presence_capacity,
                                             config.presence_expiry_s,
                                             int(config.presence_expiry_s / config.radio_interval_s) + 4)
            self.controls = ControlRegistry(wifi.radio.mac_address,config.radio_group,
                                            self.boot_session,capacity=config.presence_capacity,
                                            max_lag=int(3/config.radio_interval_s)+4)
        else:
            self.receiver = Receiver(config)
            self.control = ControlClient(config,wifi.radio.mac_address,self.boot_session)
        print("RADIO role=%s mac=%s channel=%d group=%d" %
              (config.radio_role, self.local_mac.hex(), config.radio_channel, config.radio_group))

    def publish(self, features, animation, now, sleep=None):
        self.transmitter.observe(features, now)
        if now < self.next_send:
            return
        self.next_send = now + self.c.radio_interval_s
        completed = self.radio.send_success + self.radio.send_failure
        # Permit only one outstanding send, avoiding the native API's 2-second
        # wait when its transmit queue is full. Never queue stale feature frames.
        if self.pending and completed == self.completed:
            self.skipped += 1
            return
        self.pending = False
        self.completed = completed
        sleeping=sleep is not None and sleep.started is not None
        # Every control slot is followed by audio; sleeping retains DGRS/audio.
        brightness_due=(not sleeping and getattr(self,'ack_turn',True)
                        and now>=getattr(self,'next_brightness',now+1))
        sending_ack=(not sleeping and not brightness_due
                     and getattr(self,'ack',None) is not None and self.ack_turn)
        if sleeping and self.sleep_turn:
            message=self.transmitter.encode_sleep(sleep,now)
        elif sending_ack:
            message=self.ack
        elif brightness_due:
            message=self.transmitter.encode_brightness(animation)
            self.next_brightness=now+self.c.brightness_interval_s
        else:
            message=self.transmitter.encode(features,animation,now)
        if sleeping:self.sleep_turn=not self.sleep_turn
        self.ack_turn=not (sending_ack or brightness_due)
        try:
            self.radio.send(message, self.peer)
            if sending_ack:self.ack=None
            self.pending = True
            self.sent += 1
        except (OSError, RuntimeError) as error:
            self.errors += 1
            self.next_send = now + 1.0
            print("RADIO send error:", error)

    def receive(self, now, animation):
        # Bounded draining keeps LED rendering responsive under heavy traffic.
        received = False
        for _ in range(8):
            # CircuitPython 10.3.1 exposes partially copied ESP-NOW packets
            # through read()/len(). read_success advances only after the RX
            # callback has appended the complete header, MAC and payload.
            if self.read_count == self.radio.read_success:
                break
            packet = self.radio.read()
            if packet is None:
                break
            self.read_count = (self.read_count + 1) & 0xffffffff
            if packet.msg[:4]==b'DGRA':
                if self.control:self.control.accept(packet.mac,packet.msg,self.receiver,now)
            elif packet.msg[:4]==b'DGRB':
                if self.receiver.accept(packet.mac,packet.msg,now):
                    animation.set_brightness(self.receiver.brightness,self.receiver.brightness_max)
            else:
                received = self.receiver.accept(packet.mac, packet.msg, now) or received
        if received:
            animation.time = self.receiver.scene_time
            animation.phase = self.receiver.phase
            animation.set_effect(self.receiver.effect)
        return self.receiver.features

    def _jitter(self):
        return int.from_bytes(os.urandom(2), 'little') / 65535.0

    def request_control(self, command, now):
        return self.control.request(command,self.receiver,now) if self.control else False

    def heartbeat(self, now):
        rx = self.receiver
        control=getattr(self,'control',None)
        packet=control.packet(now,rx) if control else None
        if packet is None:
            if (rx.session is None or rx.audio_sequence is None
                    or now-rx.last_audio>self.c.radio_timeout_s
                    or rx.sleep.started is not None or now<self.next_presence):return
            self.next_presence=now+self.c.presence_interval_s+(self._jitter()*2-1)*self.c.presence_jitter_s
            self.presence_sequence=(self.presence_sequence+1)&65535
            packet=encode_presence(self.c.radio_group,rx.leader,rx.session,
                                   self.boot_session,self.presence_sequence,rx.audio_sequence)
        completed=self.radio.send_success+self.radio.send_failure
        if self.pending and completed==self.completed:
            self.skipped+=1
            return
        self.completed=completed
        self.pending=False
        try:
            self.radio.send(packet,self.peer)
            self.pending=True
            self.sent+=1
        except (OSError,RuntimeError):
            self.errors+=1

    def receive_presence(self, now, animation=None, sleep=None, allow_sleep=True):
        for _ in range(8):
            if self.read_count == self.radio.read_success:
                break
            packet = self.radio.read()
            if packet is None:
                break
            self.read_count = (self.read_count + 1) & 0xffffffff
            if packet.msg[:4]==b'DGRC' and animation is not None and sleep is not None:
                request=self.controls.accept(packet.mac,packet.msg,now,self.transmitter.sequence)
                if request is None:continue
                command,boot,seq,fresh=request
                sender=bytes(packet.mac)
                if fresh:
                    denied=sleep.started is not None or (command==GROUP_SLEEP and not allow_sleep)
                    self.controls.results[sender]=int(denied)
                    if not denied:
                        if command==NEXT_EFFECT:
                            animation.set_effect((animation.effect+1)%len(EFFECT_NAMES))
                            print('GROUP effect=%d requested by %s'%(animation.effect,sender.hex()))
                        elif command in (BRIGHTER,DIMMER):
                            animation.adjust_brightness(self.c.brightness_step*(1 if command==BRIGHTER else -1))
                            self.next_brightness=now
                            print('GROUP brightness=%d%%'%round(self.c.brightness*100))
                        else:
                            sleep.request(now,self.c.sleep_fade_s)
                            print('GROUP sleep requested by',sender.hex())
                self.ack=encode_control_ack(self.c.radio_group,self.boot_session,sender,
                                            boot,seq,self.controls.results[sender])
            else:
                self.presence.accept(packet.mac,packet.msg,now,self.transmitter.sequence)

    def deinit(self):
        self.radio.deinit()
