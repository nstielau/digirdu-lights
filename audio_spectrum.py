"""Hann FFT measurements; native ulab on device, NumPy only for host tests."""

import math
import sys

if sys.implementation.name == "circuitpython":
    from ulab import numpy as np
    from ulab import utils
else:
    import numpy as np
    utils = None


class Spectrum:
    """Reusable FFT with full or half-window hops of signed 16-bit PCM."""

    def __init__(self, config):
        self.config = config
        n = config.fft_size
        self.frame = np.zeros(n)
        self.window = np.array([0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1))
                                for i in range(n)])
        self.scale = 2.0 / (n * float(np.sum(self.window * self.window)))
        self.previous = np.zeros(n // 2 + 1)
        self.previous_shape = np.zeros(n // 2 + 1)
        self.previous_sum = 0.0
        self.frequencies = np.array([i * config.sample_rate / n for i in range(n // 2 + 1)])
        self.frequency_squared = self.frequencies * self.frequencies
        self.ranges = [self.bin_range(b) for b in config.bands]
        self.total_range = self.bin_range((config.bands[0][0], config.sample_rate / 2))
        self.timbre_range = self.bin_range(config.timbre_band)
        self.vocal_range = self.bin_range(config.vocal_band)
        self.rough_range = self.bin_range(config.roughness_band)
        self.ready = False
        self.filled = 0

    def bin_range(self, band):
        step = self.config.sample_rate / self.config.fft_size
        return (max(1, int(math.ceil(band[0] / step))),
                min(self.config.fft_size // 2 + 1, int(math.ceil(band[1] / step))))

    def reset_history(self):
        """Discard overlap/flux history after a capture discontinuity."""
        self.ready = False
        self.filled = 0
        self.frame[:] = 0
        self.previous[:] = 0
        self.previous_shape[:] = 0
        self.previous_sum = 0.0

    def push(self, samples):
        c = self.config
        if len(samples) != c.hop_size:
            raise ValueError("Expected one complete PCM hop")
        h = c.hop_size
        if h < c.fft_size:
            self.frame[:-h] = self.frame[h:]
        if utils is not None:
            self.frame[-h:] = utils.from_int16_buffer(samples)
        else:
            self.frame[-h:] = np.asarray(samples, dtype=float)
        self.filled = min(c.fft_size, self.filled + h)
        if self.filled < c.fft_size:
            return None
        low, high = float(np.min(self.frame)), float(np.max(self.frame))
        span = high - low
        clipped = max(high, -low) >= 32760
        windowed = self.frame - np.mean(self.frame)
        windowed *= self.window
        if utils is not None:
            real, imaginary = np.fft.fft(windowed)
        else:
            transformed = np.fft.fft(windowed)
            real, imaginary = transformed.real, transformed.imag
        half = c.fft_size // 2 + 1
        real, imaginary = real[:half], imaginary[:half]
        power = real * real
        power += imaginary * imaginary
        # Compute magnitudes only for the non-redundant half of the spectrum.
        mag = np.sqrt(power)
        power *= self.scale * c.gain * c.gain
        power[0] *= 0.5
        power[-1] *= 0.5  # Nyquist has no negative-frequency partner.
        # Parseval: RMS of the DC-removed, Hann-weighted frame. Reusing FFT
        # power avoids a second full time-domain square/reduction on this CPU.
        rms = math.sqrt(float(np.sum(power)))
        energies = tuple(float(np.sum(power[a:b])) for a, b in self.ranges)
        a, b = self.total_range
        total = float(np.sum(power[a:b]))
        eps = max(total * 1e-12, 1e-20)
        centroid = float(np.dot(power[a:b], self.frequencies[a:b])) / max(total, eps)
        old_sum = self.previous_sum
        new_sum = float(np.sum(mag[a:b]))
        current_shape = mag * (1.0 / max(new_sum, 1e-10))
        if self.ready and new_sum > 1e-10:
            flux = float(np.sum(np.maximum(mag[a:b] - self.previous[a:b], 0))) / max(new_sum, old_sum, 1e-10)
            delta = current_shape[a:b] - self.previous_shape[a:b]
            shape_flux = float(np.sum(np.maximum(delta, -delta))) / 2
        else:
            flux = shape_flux = 0.0
        self.previous = mag
        self.previous_shape = current_shape
        self.previous_sum = new_sum
        self.ready = True
        a, b = self.timbre_range
        timbre_energy = float(np.sum(power[a:b]))
        timbre_hz = float(np.dot(power[a:b], self.frequencies[a:b])) / max(timbre_energy, eps)
        a, b = self.vocal_range
        vocal_energy = float(np.sum(power[a:b]))
        a, b = self.rough_range
        rough = power[a:b]
        rough_sum = float(np.sum(rough))
        if rough_sum > eps:
            if c.roughness_metric == "flatness":
                rough_mean = rough_sum / (b - a)
                flatness = math.exp(float(np.mean(np.log(rough / rough_mean + 1e-12))))
            else:
                # Participation ratio: how many bins carry substantial energy?
                # Remove a sinusoid's Hann footprint, then normalize to noise.
                effective_bins = rough_sum * rough_sum / max(float(np.dot(rough, rough)), eps)
                flatness = max(0.0, min(1.0, (effective_bins - c.noise_tonal_bins) /
                                        ((b - a) * c.noise_expected_fill)))
            center = float(np.dot(rough, self.frequencies[a:b])) / rough_sum
            second_moment = float(np.dot(rough, self.frequency_squared[a:b])) / rough_sum
            spread = math.sqrt(max(0.0, second_moment - center * center))
        else:
            flatness = spread = 0.0
        a, b = self.ranges[0]
        peak_bin = a + int(np.argmax(power[a:b]))
        concentration = float(np.sum(power[max(a, peak_bin - 1):min(b, peak_bin + 2)])) / max(energies[0], eps)
        return {"rms": rms, "span": span, "clipped": clipped,
                "bands": energies, "total": total, "centroid_hz": centroid,
                "timbre_hz": timbre_hz, "vocal_energy": vocal_energy,
                "flux": flux, "shape_flux": shape_flux, "flatness": flatness,
                "spread_hz": spread, "drone_hz": float(self.frequencies[peak_bin]),
                "drone_concentration": concentration}
