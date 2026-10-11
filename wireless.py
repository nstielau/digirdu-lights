"""CircuitPython ESP-NOW transport for one mic leader and wireless LED nodes."""

import os

import espnow
import wifi

from radio_protocol import Transmitter, Receiver
from telemetry import TelemetryRecorder


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
        self.sleep_turn = True
        self.pending = False
        self.completed = 0
        self.completed_success = self.radio.send_success
        self.pending_sequence = None
        self.read_count = 0
        self.telemetry = TelemetryRecorder(
            "producer" if config.radio_role == "leader" else "consumer",
            os.urandom(8).hex())
        if config.radio_role == "leader":
            self.peer = espnow.Peer(mac=b"\xff" * 6, channel=config.radio_channel)
            self.radio.peers.append(self.peer)
            self.transmitter = Transmitter(config, int.from_bytes(os.urandom(4), "little"))
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
            self.telemetry.skipped()
            return
        if self.pending_sequence is not None:
            self.telemetry.completed(self.transmitter.session, self.pending_sequence,
                                     self.radio.send_success != self.completed_success)
            self.pending_sequence = None
        self.pending = False
        self.completed = completed
        self.completed_success = self.radio.send_success
        # Alternate repeated sleep commands and features. Feature frames allow
        # a consumer joining during the fade to establish the producer session.
        if sleep is not None and sleep.started is not None and self.sleep_turn:
            message = self.transmitter.encode_sleep(sleep, now)
        else:
            message = self.transmitter.encode(features, animation, now)
        if sleep is not None and sleep.started is not None:
            self.sleep_turn = not self.sleep_turn
        sequence = self.transmitter.sequence
        self.telemetry.attempted(self.transmitter.session, sequence, message[:4] == b"DGRS")
        try:
            self.radio.send(message, self.peer)
            self.pending = True
            self.pending_sequence = sequence
            self.sent += 1
        except (OSError, RuntimeError) as error:
            self.telemetry.completed(self.transmitter.session, sequence, False)
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
            accepted = self.receiver.accept(packet.mac, packet.msg, now)
            if accepted:
                self.telemetry.received(self.receiver.session, self.receiver.sequence,
                                        getattr(packet, "rssi", None), packet.msg[:4] == b"DGRS")
            else:
                self.telemetry.rejected()
            received = accepted or received
        failures = getattr(self.radio, "read_failure", None)
        if type(failures) is int:
            self.telemetry.native_failures(failures)
        if received:
            animation.time = self.receiver.scene_time
            animation.phase = self.receiver.phase
            animation.set_effect(self.receiver.effect)
        return self.receiver.features

    def observe_link(self, lost):
        self.telemetry.link_lost(lost)

    def deinit(self):
        self.radio.deinit()
