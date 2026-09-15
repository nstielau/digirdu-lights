"""CircuitPython ESP-NOW transport for one mic leader and wireless LED nodes."""

import os

import espnow
import wifi

from radio_protocol import Transmitter, Receiver


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
        self.peer = None
        self.transmitter = None
        self.receiver = None
        self.next_send = 0.0
        self.sent = self.errors = self.skipped = 0
        self.pending = False
        self.completed = 0
        if config.radio_role == "leader":
            self.peer = espnow.Peer(mac=b"\xff" * 6, channel=config.radio_channel)
            self.radio.peers.append(self.peer)
            self.transmitter = Transmitter(config, int.from_bytes(os.urandom(4), "little"))
        else:
            self.receiver = Receiver(config)
        print("RADIO role=%s mac=%s channel=%d group=%d" %
              (config.radio_role, bytes(wifi.radio.mac_address).hex(), config.radio_channel, config.radio_group))

    def publish(self, features, animation, now):
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
        message = self.transmitter.encode(features, animation, now)
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
            packet = self.radio.read()
            if packet is None:
                break
            received = self.receiver.accept(packet.mac, packet.msg, now) or received
        if received:
            animation.time = self.receiver.scene_time
            animation.phase = self.receiver.phase
            animation.set_effect(self.receiver.effect)
        return self.receiver.features

    def deinit(self):
        self.radio.deinit()
