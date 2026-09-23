"""Versioned, bounded feature packets. No audio, network imports or credentials."""

import math
import struct

from audio_features import AudioFeatures, clamp
from effects import EFFECT_NAMES, SleepTransition

FIELDS = ("volume", "drone", "harmonics", "timbrePosition", "growl", "vocal",
          "roughness", "centroid", "attack", "decay")
FORMAT = "<4sBHIHffHHHHBBB10BB8B"
SIZE = struct.calcsize(FORMAT)
# Optional control extension; normal audio frames remain unchanged v3.
# magic, version, group, producer session, shared sequence, elapsed ms, fade ms.
SLEEP_FORMAT = "<4sBHIHHH"
SLEEP_SIZE = struct.calcsize(SLEEP_FORMAT)


class Transmitter:
    def __init__(self, config, session):
        self.c = config
        self.session = session
        self.sequence = self.attack_id = self.yell_id = 0
        self.attack_time = self.yell_time = -100.0
        self.attack_strength = self.yell_strength = 0.0

    def observe(self, features, now):
        # Called EVERY audio frame, including frames between radio sends.
        if features.attackEvent:
            self.attack_id = (self.attack_id + 1) & 65535
            self.attack_time = now
            self.attack_strength = features.attack
        if features.yellEvent:
            self.yell_id = (self.yell_id + 1) & 65535
            self.yell_time = now
            self.yell_strength = max(features.vocal, 0.7)

    def encode(self, features, animation, now):
        self.sequence = (self.sequence + 1) & 65535
        attack_age = min(65535, max(0, int((now - self.attack_time) * 1000)))
        yell_age = min(65535, max(0, int((now - self.yell_time) * 1000)))
        return struct.pack(FORMAT, b"DGRD", 3, self.c.radio_group, self.session,
                           self.sequence, animation.time, animation.phase,
                           self.attack_id, self.yell_id, attack_age, yell_age,
                           int(clamp(self.attack_strength) * 255), int(clamp(self.yell_strength) * 255),
                           int(features.active), *(int(clamp(getattr(features, name)) * 255) for name in FIELDS),
                           animation.effect, *(int(clamp(v) * 255) for v in features.spectrum))

    def encode_sleep(self, transition, now):
        self.sequence = (self.sequence + 1) & 65535
        duration = int(transition.duration * 1000)
        elapsed = min(duration, int(transition.elapsed(now) * 1000))
        return struct.pack(SLEEP_FORMAT, b"DGRS", 1, self.c.radio_group,
                           self.session, self.sequence, elapsed, duration)


class Receiver:
    def __init__(self, config):
        self.c = config
        self.leader = bytes.fromhex(config.leader_mac.replace(":", ""))
        self.features = AudioFeatures()
        self.features.calibrating = False
        self.session = self.sequence = None
        self.attack_id = self.yell_id = None
        self.last_receive = self.last_audio = -100.0
        self.audio_sequence = None
        self.scene_time = self.phase = 0.0
        self.effect = 0
        self.sleep = SleepTransition()
        self.sleep_commands = 0
        self.accepted = self.rejected = 0

    def accept(self, mac, message, now):
        if bytes(mac) == self.leader and len(message) == SLEEP_SIZE:
            return self._accept_sleep(message, now)
        if bytes(mac) != self.leader or len(message) != SIZE:
            self.rejected += 1
            return False
        values = struct.unpack(FORMAT, message)
        magic, version, group, session, sequence, scene_time, phase = values[:7]
        if (magic != b"DGRD" or version != 3 or group != self.c.radio_group
                or not math.isfinite(scene_time) or scene_time < 0
                or not math.isfinite(phase) or not 0 <= phase < 1 or values[13] > 1
                or values[24] >= len(EFFECT_NAMES)):
            self.rejected += 1
            return False
        new_session = session != self.session
        if not new_session and not 0 < ((sequence - self.sequence) & 65535) < 32768:
            self.rejected += 1
            return False
        attack_id, yell_id, attack_age, yell_age, attack_strength, yell_strength = values[7:13]
        f = self.features
        # OR latches preserve an event while draining several queued packets.
        if (not new_session and attack_id != self.attack_id
                and attack_age / 1000 <= self.c.radio_event_max_age_s):
            f.attackEvent = True
            f.attackAge = attack_age / 1000
        if (not new_session and yell_id != self.yell_id
                and yell_age / 1000 <= self.c.radio_event_max_age_s):
            f.yellEvent = True
            f.yellAge = yell_age / 1000
        self.session, self.sequence = session, sequence
        self.attack_id, self.yell_id = attack_id, yell_id
        for name, value in zip(FIELDS, values[14:24]):
            setattr(f, name, value / 255)
        if f.attackEvent:
            f.attack = attack_strength / 255
        if f.yellEvent:
            f.vocal = max(f.vocal, yell_strength / 255)
        f.active = bool(values[13])
        self.scene_time, self.phase = scene_time, phase
        self.effect = values[24]
        f.spectrum = tuple(value / 255 for value in values[25:33])
        self.last_receive = self.last_audio = now
        self.audio_sequence = sequence
        self.accepted += 1
        return True

    def _accept_sleep(self, message, now):
        magic, version, group, session, sequence, elapsed, duration = struct.unpack(SLEEP_FORMAT, message)
        # Require a previously accepted feature frame from this producer boot.
        # A reset consumer cannot be put to sleep by an orphan/stale command.
        if (magic != b"DGRS" or version != 1 or group != self.c.radio_group
                or self.session is None or session != self.session
                or not 0 < ((sequence - self.sequence) & 65535) < 32768
                or not 0 < duration <= 10000 or not 0 <= elapsed <= duration
                or now - self.last_receive > self.c.radio_timeout_s):
            self.rejected += 1
            return False
        self.sequence = sequence
        self.last_receive = now
        self.sleep.request(now, duration / 1000.0, elapsed / 1000.0)
        self.sleep_commands += 1
        self.accepted += 1
        return True

    def clear_events(self):
        self.features.attackEvent = self.features.yellEvent = False

    def fade_if_lost(self, now, dt):
        if now - self.last_receive <= self.c.radio_timeout_s:
            return False
        f = self.features
        f.active = False
        self.clear_events()
        f.spectrum = tuple(value * math.exp(-dt / self.c.decay_s) for value in f.spectrum)
        # Keep the last hue/centroid while the remaining light decays.
        for name in ("volume", "drone", "harmonics", "growl", "vocal", "roughness", "attack", "decay"):
            setattr(f, name, getattr(f, name) * math.exp(-dt / self.c.decay_s))
        return True


# Separate control extension: group, intended producer MAC/session, consumer
# boot session/sequence, last accepted AUDIO sequence. Never modifies v3 bytes.
PRESENCE_FORMAT = '<4sBH6sIIHH'
PRESENCE_SIZE = struct.calcsize(PRESENCE_FORMAT)


def encode_presence(group, producer, session, boot, sequence, audio_sequence):
    if len(producer) != 6:
        raise ValueError('Invalid producer MAC')
    return struct.pack(PRESENCE_FORMAT, b'DGRP', 1, group, producer, session,
                       boot, sequence, audio_sequence)


class PresenceRegistry:
    """Recent acknowledgments, not inventory or delivery/LED guarantees."""
    def __init__(self, mac, group, session, capacity=32, expiry=10.0, max_lag=160):
        self.mac, self.group, self.session = bytes(mac), group, session
        self.capacity, self.expiry, self.max_lag = capacity, expiry, max_lag
        self.entries = {}
        self.accepted = self.rejected = 0
        self.full = False

    def count(self, now):
        for mac in tuple(self.entries):
            if now - self.entries[mac][3] > self.expiry:
                del self.entries[mac]
        self.full = len(self.entries) >= self.capacity
        return len(self.entries)

    def accept(self, sender, message, now, latest_sequence):
        if len(sender) != 6 or len(message) != PRESENCE_SIZE:
            self.rejected += 1
            return False
        magic, version, group, intended, session, boot, seq, audio = struct.unpack(PRESENCE_FORMAT, message)
        sender = bytes(sender)
        if (magic != b'DGRP' or version != 1 or group != self.group
                or intended != self.mac or session != self.session or sender == self.mac
                or sender == b'\xff' * 6 or sender == bytes(6)
                or ((latest_sequence - audio) & 65535) > self.max_lag):
            self.rejected += 1
            return False
        self.count(now)
        old = self.entries.get(sender)
        retired = ()
        if old:
            old_boot, old_seq, _, _, retired = old
            if (boot in retired or boot == old_boot and not 0 < ((seq - old_seq) & 65535) < 32768):
                self.rejected += 1
                return False
            if boot != old_boot:
                retired = (retired + (old_boot,))[-2:]
        elif len(self.entries) >= self.capacity:
            oldest = min(self.entries, key=lambda mac: self.entries[mac][3])
            del self.entries[oldest]
        self.entries[sender] = (boot, seq, audio, now, retired)
        self.accepted += 1
        self.full = len(self.entries) >= self.capacity
        return True
