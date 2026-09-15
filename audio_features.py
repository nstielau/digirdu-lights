"""Simultaneous didgeridoo feature envelopes and edge-triggered musical events.

These are tunable acoustic heuristics, not semantic voice recognition.
No feature excludes another: a drone can coexist with growl, vocal and attacks.
"""

import math


def clamp(value):
    return max(0.0, min(1.0, value))


def scale(value, limits):
    return clamp((value - limits[0]) / (limits[1] - limits[0]))


def smooth(previous, target, dt, attack, release):
    tau = attack if target > previous else release
    return target + (previous - target) * math.exp(-dt / tau)


class AudioFeatures:
    """Normalized continuous values; events are true for ONE analysis frame."""

    def __init__(self):
        self.volume = self.drone = self.harmonics = 0.0
        self.timbrePosition = self.growl = self.vocal = 0.0
        self.roughness = self.centroid = self.attack = 0.0
        self.attackEvent = self.yellEvent = False
        self.attackAge = self.yellAge = 0.0
        self.active = False
        self.decay = 0.0
        self.rms = self.noiseFloor = self.flux = self.flatness = 0.0
        self.modulation = self.fundamentalHz = 0.0
        self.bandEnergy = self.bandRatio = (0.0,) * 5
        self.clipped = False
        self.calibrating = True


class Analyzer:
    def __init__(self, config):
        self.c = config
        self.features = AudioFeatures()
        self.elapsed = 0.0
        self.calibration = []
        self.noise = config.min_noise_rms
        self.band_noise = [self.noise * self.noise / 5] * 5
        self.level_reference = config.level_initial
        self.rms_previous = 0.0
        self.mid_reference = 0.0
        self.modulation = 0.0
        self.vocal_reference = 0.0
        self.vocal_previous = 0.0
        self.pitch_previous = 0.0
        self.pitch_stability = 0.0
        self.quiet_time = 0.0
        self.attack_armed = self.yell_armed = True
        self.last_attack = self.last_yell = -100.0
        self.attack_memory = self.yell_memory = 0.0
        self.suppress_until = 0.0

    def discontinuity(self):
        """Don't interpret dropped audio or a processing pause as a new attack."""
        self.suppress_until = self.elapsed + self.c.event_warmup_s
        self.rms_previous = 0.0
        self.vocal_previous = 0.0
        self.features.attackEvent = self.features.yellEvent = False

    def _calibrate(self, raw, dt):
        c, f = self.c, self.features
        if self.elapsed > c.warmup_s:
            self.calibration.append((raw["rms"], raw["bands"]))
        if self.elapsed < c.calibration_s or not self.calibration:
            return
        index = int((len(self.calibration) - 1) * c.calibration_quantile)
        levels = sorted(row[0] for row in self.calibration)
        self.noise = max(c.min_noise_rms, levels[index])
        for band in range(5):
            values = sorted(row[1][band] for row in self.calibration)
            self.band_noise[band] = max(c.min_noise_rms ** 2 / 5, values[index])
        self.level_reference = max(c.level_initial, self.noise * c.active_full_ratio)
        self.calibration = []
        f.calibrating = False
        self.discontinuity()

    def update(self, raw, dt):
        if dt <= 0 or not math.isfinite(dt):
            raise ValueError("Positive finite frame time required")
        c, f = self.c, self.features
        self.elapsed += dt
        f.attackEvent = f.yellEvent = False
        f.rms = rms = raw["rms"]
        f.bandEnergy = raw["bands"]
        f.clipped = raw["clipped"]
        if f.calibrating:
            self._calibrate(raw, dt)
            f.noiseFloor = self.noise
            return f

        # A loud foreground frame never raises the background estimate.
        # Falling background can recover even after a poor startup calibration.
        if rms < self.noise * c.noise_learn_ratio:
            target = max(c.min_noise_rms, rms)
            self.noise = smooth(self.noise, target, dt, c.noise_rise_s, c.noise_fall_s)
            for i in range(5):
                target = max(c.min_noise_rms ** 2 / 5, raw["bands"][i])
                target = min(target, self.band_noise[i] * c.adaptation_limit)
                self.band_noise[i] = smooth(self.band_noise[i], target, dt,
                                            c.noise_rise_s, c.noise_fall_s)
        f.noiseFloor = self.noise
        snr = rms / self.noise
        gate = scale(snr, (c.active_off_ratio, c.active_full_ratio))
        if snr >= c.active_on_ratio:
            f.active = True
            self.quiet_time = 0.0
        elif snr < c.active_off_ratio:
            self.quiet_time += dt
            if self.quiet_time >= c.silence_hold_s:
                f.active = False
        else:
            self.quiet_time = 0.0

        # Slowly track typical playing level, with bounded influence per frame.
        if snr >= c.active_on_ratio:
            target = max(self.level_reference / c.adaptation_limit,
                         min(rms, self.level_reference * c.adaptation_limit))
            self.level_reference = smooth(self.level_reference, target, dt,
                                          c.level_rise_s, c.level_fall_s)
        volume = gate * clamp(math.log(1 + max(0, rms - self.noise) / self.noise) /
                              math.log(1 + self.level_reference * 2 / self.noise))

        # Subtract a conservative per-band background before forming ratios.
        energy = [max(0.0, raw["bands"][i] - self.band_noise[i]) for i in range(5)]
        total = max(sum(energy), self.noise * self.noise, 1e-12)
        ratios = tuple(e / total for e in energy)
        f.bandRatio = ratios
        mid_ratio = ratios[1] + ratios[2]
        mid_change = abs(mid_ratio - self.mid_reference)
        self.mid_reference = smooth(self.mid_reference, mid_ratio, dt,
                                    c.spectrum_reference_s, c.spectrum_reference_s)
        self.modulation = smooth(self.modulation, mid_change, dt,
                                 c.modulation_s, c.modulation_s)
        modulation = scale(self.modulation, c.modulation_range)
        flatness = scale(raw["flatness"], c.flatness_range)
        shape = scale(raw["shape_flux"], c.shape_flux_range)
        spreading = scale(raw["spread_hz"], c.spread_hz)
        weights = c.roughness_weights
        roughness = gate * clamp(weights[0] * flatness + weights[1] * modulation + weights[2] * shape)
        growl = roughness * scale(mid_ratio, c.mid_ratio) * (0.6 + 0.4 * spreading)

        concentration = scale(raw["drone_concentration"], c.drone_concentration)
        pitch_change = abs(raw["drone_hz"] - self.pitch_previous) / max(raw["drone_hz"], 1)
        stable = 1.0 - clamp(pitch_change / c.pitch_change_fraction)
        self.pitch_previous = raw["drone_hz"]
        self.pitch_stability = smooth(self.pitch_stability, stable, dt, c.drone_attack_s, c.drone_release_s)
        drone_snr = math.sqrt(raw["bands"][0] / max(self.band_noise[0], 1e-12))
        drone = gate * scale(drone_snr, c.drone_snr) * concentration * (0.6 + 0.4 * self.pitch_stability)
        harmonics = gate * scale(mid_ratio, c.harmonics_ratio)
        timbre = (0.65 * scale(raw["timbre_hz"], c.timbre_band) +
                  0.35 * ratios[2] / max(mid_ratio, 1e-12))

        # Both a total-energy share AND a drone-relative share are required.
        # Thus merely multiplying a drone's waveform cannot turn it into a yell.
        vocal_share = clamp(raw["vocal_energy"] / max(raw["total"], self.noise ** 2))
        vocal_to_drone = raw["vocal_energy"] / max(raw["bands"][0], self.noise ** 2)
        vocal_base = gate * math.sqrt(scale(vocal_share, c.vocal_total_ratio) *
                                      scale(vocal_to_drone, c.vocal_drone_ratio))
        excess = scale(vocal_share - self.vocal_reference, c.vocal_excess_range)
        vocal = vocal_base * (0.75 + 0.25 * excess)
        # Only non-vocal playing may redefine the long-term vocal reference.
        if gate > 0 and vocal_base < c.yell_off:
            self.vocal_reference = smooth(self.vocal_reference, vocal_share, dt,
                                          c.vocal_reference_s, c.vocal_reference_s)

        rise = max(0.0, (rms - self.rms_previous) / max(rms, self.noise))
        flux = scale(raw["flux"], c.attack_flux_range)
        attack_score = gate * clamp(c.attack_weights[0] * flux +
                                    c.attack_weights[1] * scale(rise, c.attack_rise_range))
        vocal_rise = max(0.0, vocal_base - self.vocal_previous)
        self.rms_previous = rms
        self.vocal_previous = vocal_base
        self.attack_memory *= math.exp(-dt / c.echo_memory_s)
        self.yell_memory *= math.exp(-dt / c.echo_memory_s)
        if attack_score < c.attack_off:
            self.attack_armed = True
        if vocal_base < c.yell_off:
            self.yell_armed = True
        eligible = self.elapsed >= self.suppress_until and snr >= c.active_on_ratio
        if (eligible and self.attack_armed and attack_score >= c.attack_on
                and self.elapsed - self.last_attack >= c.attack_cooldown_s
                and rms >= self.attack_memory * c.echo_event_ratio):
            f.attackEvent = True
            self.attack_armed = False
            self.last_attack = self.elapsed
            self.attack_memory = rms
        if (eligible and self.yell_armed and vocal_base >= c.yell_on
                and vocal_rise >= c.yell_rise
                and self.elapsed - self.last_yell >= c.yell_cooldown_s
                and rms >= self.yell_memory * c.echo_event_ratio):
            f.yellEvent = True
            self.yell_armed = False
            self.last_yell = self.elapsed
            self.yell_memory = rms

        f.volume = smooth(f.volume, volume, dt, c.feature_attack_s, c.feature_release_s)
        f.drone = smooth(f.drone, drone, dt, c.drone_attack_s, c.drone_release_s)
        f.harmonics = smooth(f.harmonics, harmonics, dt, c.feature_attack_s, c.feature_release_s)
        if gate > 0:
            f.timbrePosition = smooth(f.timbrePosition, timbre, dt, c.timbre_s, c.timbre_s)
            f.centroid = smooth(f.centroid, clamp(raw["centroid_hz"] / c.vocal_band[1]),
                                dt, c.timbre_s, c.timbre_s)
        f.growl = smooth(f.growl, growl, dt, c.growl_attack_s, c.growl_release_s)
        f.vocal = smooth(f.vocal, vocal, dt, c.vocal_attack_s, c.vocal_release_s)
        f.roughness = smooth(f.roughness, roughness, dt, c.growl_attack_s, c.growl_release_s)
        f.attack = max(attack_score if f.attackEvent else 0.0,
                       f.attack * math.exp(-dt / c.attack_release_s))
        f.decay = max(volume, f.decay * math.exp(-dt / c.decay_s))
        f.flux = clamp(raw["flux"])
        f.flatness = clamp(raw["flatness"])
        f.modulation = gate * modulation
        f.fundamentalHz = raw["drone_hz"] if drone > 0.2 else 0.0
        return f
