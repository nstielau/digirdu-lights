"""CircuitPython ESP-NOW transport for one mic leader and wireless LED nodes."""

import os
import time

import espnow
import wifi

from radio_protocol import Transmitter, Receiver, PresenceRegistry, encode_presence


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
        if config.radio_role == "leader":
            self.transmitter = Transmitter(config, self.boot_session)
            self.presence = PresenceRegistry(wifi.radio.mac_address, config.radio_group,
                                             self.boot_session, config.presence_capacity,
                                             config.presence_expiry_s,
                                             int(config.presence_expiry_s / config.radio_interval_s) + 4)
        else:
            self.receiver = Receiver(config)
        print("RADIO role=%s mac=%s channel=%d group=%d" %
              (config.radio_role, bytes(wifi.radio.mac_address).hex(), config.radio_channel, config.radio_group))

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
        # Alternate repeated sleep commands and features. Feature frames allow
        # a consumer joining during the fade to establish the producer session.
        if sleep is not None and sleep.started is not None and self.sleep_turn:
            message = self.transmitter.encode_sleep(sleep, now)
        else:
            message = self.transmitter.encode(features, animation, now)
        if sleep is not None and sleep.started is not None:
            self.sleep_turn = not self.sleep_turn
        try:
            self.radio.send(message, self.peer)
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
            received = self.receiver.accept(packet.mac, packet.msg, now) or received
        if received:
            animation.time = self.receiver.scene_time
            animation.phase = self.receiver.phase
            animation.set_effect(self.receiver.effect)
        return self.receiver.features

    def _jitter(self):
        return int.from_bytes(os.urandom(2), 'little') / 65535.0

    def heartbeat(self, now):
        rx = self.receiver
        if (rx.session is None or rx.audio_sequence is None
                or now - rx.last_audio > self.c.radio_timeout_s
                or rx.sleep.started is not None or now < self.next_presence):
            return
        self.next_presence = now + self.c.presence_interval_s + (self._jitter() * 2 - 1) * self.c.presence_jitter_s
        completed = self.radio.send_success + self.radio.send_failure
        if self.pending and completed == self.completed:
            self.skipped += 1
            return
        self.completed = completed
        self.pending = False
        self.presence_sequence = (self.presence_sequence + 1) & 65535
        packet = encode_presence(self.c.radio_group, rx.leader, rx.session,
                                 self.boot_session, self.presence_sequence, rx.audio_sequence)
        try:
            self.radio.send(packet, self.peer)
            self.pending = True
            self.sent += 1
        except (OSError, RuntimeError):
            self.errors += 1

    def receive_presence(self, now):
        for _ in range(8):
            if self.read_count == self.radio.read_success:
                break
            packet = self.radio.read()
            if packet is None:
                break
            self.read_count = (self.read_count + 1) & 0xffffffff
            self.presence.accept(packet.mac, packet.msg, now, self.transmitter.sequence)

    def deinit(self):
        self.radio.deinit()
