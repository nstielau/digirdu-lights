"""Installation tuning. Frequencies in Hz, times in seconds, levels in PCM units."""


class Config:
    # Confirmed hardware pins live only in code.py.
    sample_rate = 16000
    fft_size = 1024
    hop_size = 1024
    bands = ((45, 180), (180, 450), (450, 1000), (1000, 3500), (3500, 8000))
    # Eight diagnostic columns; independent of the five musical detector bands.
    spectrum_edges = (45, 90, 180, 350, 700, 1400, 2800, 5000, 8000)
    spectrum_attack_s = 0.05
    spectrum_release_s = 0.30
    spectrum_gain = 1.0
    spectrum_full_scale = 2.0  # Multiple of the slowly adapting RMS reference.
    spectrum_curve = 0.6  # Compress amplitude to make quieter harmonics visible.
    spectrum_rotation = 0  # Landscape 8 columns x 4 rows; optionally 180.
    timbre_band = (150, 1000)
    vocal_band = (700, 3500)
    roughness_band = (180, 3500)
    roughness_metric = "participation"  # Faster than logarithmic flatness on S2.
    noise_tonal_bins = 2.0  # A Hann-windowed sinusoid occupies about two effective bins.
    noise_expected_fill = 0.5  # Expected effective-bin fraction for noise power.
    gain = 1.0
    calibration_s = 2.0
    warmup_s = 0.2
    calibration_quantile = 0.2
    min_noise_rms = 2.0
    noise_rise_s = 120.0
    noise_fall_s = 4.0
    noise_learn_ratio = 1.8
    level_initial = 120.0
    level_rise_s = 12.0
    level_fall_s = 45.0
    adaptation_limit = 2.0  # Cap each observation before updating the reference.
    active_on_ratio = 2.8
    active_off_ratio = 1.6
    active_full_ratio = 5.0
    silence_hold_s = 0.45
    feature_attack_s = 0.09
    feature_release_s = 0.6
    drone_attack_s = 0.3
    drone_release_s = 1.8
    timbre_s = 0.22
    growl_attack_s = 0.16
    growl_release_s = 0.85
    vocal_attack_s = 0.08
    vocal_release_s = 0.5
    drone_snr = (2.0, 6.0)
    drone_concentration = (0.4, 0.85)
    pitch_change_fraction = 0.3
    harmonics_ratio = (0.03, 0.65)
    mid_ratio = (0.08, 0.55)
    flatness_range = (0.03, 0.4)
    spread_hz = (200.0, 1200.0)
    modulation_range = (0.015, 0.18)
    modulation_s = 0.16
    spectrum_reference_s = 0.6
    shape_flux_range = (0.02, 0.25)
    roughness_weights = (0.55, 0.25, 0.20)  # Flatness, modulation, shape flux.
    vocal_total_ratio = (0.10, 0.55)
    vocal_drone_ratio = (0.12, 1.5)
    vocal_reference_s = 15.0
    vocal_excess_range = (0.04, 0.25)
    yell_on = 0.58
    yell_off = 0.25
    yell_rise = 0.10
    yell_cooldown_s = 0.6
    attack_flux_range = (0.06, 0.4)
    attack_rise_range = (0.08, 0.6)
    attack_weights = (0.65, 0.35)  # Positive spectral flux and RMS rise.
    attack_on = 0.5
    attack_off = 0.18
    attack_cooldown_s = 0.18
    attack_release_s = 0.22
    echo_event_ratio = 0.6
    echo_memory_s = 0.8
    event_warmup_s = 0.15
    decay_s = 3.5
    flat_timeout_s = 2.0
    log_interval_s = 1.0

    # The 32-pixel wing previews a line spanning the culvert length.
    pixel_count = 32
    brightness = 0.15
    pixel_positions = None  # Optional per-physical-pixel (axial -1..1, turns 0..1).
    origin = 0.0
    base_hue = 0.52
    timbre_hue_span = 0.34
    base_speed = 0.12
    harmonic_speed = 0.45
    wave_cycles = 1.5
    growl_texture = 0.85
    # Visual expansion of observed playing ranges; detector outputs stay unchanged.
    visual_timbre_range = (0.12, 0.45)
    visual_growl_range = (0.04, 0.30)
    visual_vocal_range = (0.03, 0.40)
    drone_field_gain = 0.85
    volume_field_gain = 0.30
    decay_field_gain = 0.42
    wave_floor = 0.12
    vocal_ribbon_gain = 0.95
    attack_bloom_gain = 0.70
    attack_bloom_s = 0.13
    yell_bloom_gain = 0.85
    yell_bloom_s = 0.32
    pulse_gain = 1.35
    pulse_speed = 1.15  # Half-culvert lengths/second, intentionally theatrical.
    pulse_width = 0.18
    pulse_decay_s = 1.35
    max_pulses = 8
    trail_s = 0.28  # Short pixel trails preserve rhythm; audio decay stays 3.5 s.
    # Chroma: calibrated from active samples in didgeridoo-take1 (10th/90th
    # percentiles of the coarse band centroid). Replay reports new calibration.
    chroma_frequency_hz = (153.28, 350.55)
    chroma_hue_range = (0.0, 0.75)  # Red -> yellow -> green -> blue -> violet.
    chroma_color_s = 0.30
    chroma_attack_s = 0.06
    chroma_release_s = 0.80
    chroma_min_volume = 0.10  # Hold last hue below this level; still fade light.
    effect_index = 0
    effect_indicator_enabled = True
    effect_indicator_s = 1.5
    effect_indicator_rotation = 0  # Portrait; 180 turns the number upside down.
    effect_indicator_map = None  # Optional logical 4x8 -> physical 0..31 map.
    button_next_gpio = 0  # Built-in BOOT button, active low. None disables it.
    button_extra_next_gpio = 43  # FeatherS2 external next button to GND; None disables it.
    button_previous_gpio = None  # Optional external button to GND.
    button_debounce_s = 0.04

    # One microphone leader; each wireless follower has its own ESP32 + wing.
    radio_role = "follower"  # New nodes consume; producer role is saved per board.
    radio_channel = 1
    radio_group = 1
    leader_mac = "7c:df:a1:03:4c:2c"
    radio_interval_s = 0.064
    radio_timeout_s = 0.5
    radio_event_max_age_s = 0.5
    receiver_frame_s = 0.032

    def __init__(self, **overrides):
        for name, value in overrides.items():
            if not hasattr(self, name):
                raise ValueError("Unknown configuration: " + name)
            setattr(self, name, value)
        self.radio_role = {"producer": "leader", "consumer": "follower"}.get(self.radio_role, self.radio_role)
        self.validate()

    def validate(self):
        if self.sample_rate not in (16000, 22050):
            raise ValueError("sample_rate must be 16000 or 22050")
        if self.roughness_metric not in ("participation", "flatness"):
            raise ValueError("Invalid roughness_metric")
        if self.noise_expected_fill <= 0:
            raise ValueError("noise_expected_fill must be positive")
        if self.fft_size not in (512, 1024) or self.hop_size not in (self.fft_size // 2, self.fft_size):
            raise ValueError("Use a 512/1024 FFT with half- or full-window hops")
        if len(self.bands) != 5:
            raise ValueError("Expected five ordered frequency bands")
        last = 0
        for low, high in self.bands:
            if not last <= low < high <= self.sample_rate / 2:
                raise ValueError("Invalid frequency bands")
            last = high
        for low, high in (self.timbre_band, self.vocal_band, self.roughness_band):
            if not 0 < low < high <= self.sample_rate / 2:
                raise ValueError("Invalid analysis band")
        for name in dir(self):
            if name.endswith("_s") and getattr(self, name) <= 0:
                raise ValueError(name + " must be positive")
        if not 0 < self.brightness <= 1 or self.pixel_count < 2 or self.gain <= 0:
            raise ValueError("Invalid brightness, pixel_count, or gain")
        if (len(self.spectrum_edges) != 9
                or not 0 < self.spectrum_edges[0] < self.spectrum_edges[-1] <= self.sample_rate / 2
                or any(b - a < self.sample_rate / self.fft_size
                       for a, b in zip(self.spectrum_edges, self.spectrum_edges[1:]))):
            raise ValueError("Expected nine ascending spectrum edges, at least one FFT bin apart")
        if (self.spectrum_gain <= 0 or self.spectrum_full_scale <= 0
                or not 0 < self.spectrum_curve <= 1 or self.spectrum_rotation not in (0, 180)):
            raise ValueError("Invalid spectrum display tuning")
        if not 0 <= self.calibration_quantile <= 1:
            raise ValueError("Invalid calibration quantile")
        if not 0 < self.active_off_ratio < self.active_on_ratio < self.active_full_ratio:
            raise ValueError("Invalid activity thresholds")
        if not 0 <= self.yell_off < self.yell_on <= 1:
            raise ValueError("Invalid yell hysteresis")
        if not 0 <= self.attack_off < self.attack_on <= 1:
            raise ValueError("Invalid attack hysteresis")
        if self.max_pulses < 1 or self.pulse_width <= 0 or self.pulse_speed <= 0:
            raise ValueError("Invalid pulse configuration")
        for limits in (self.visual_timbre_range, self.visual_growl_range, self.visual_vocal_range):
            if len(limits) != 2 or not 0 <= limits[0] < limits[1] <= 1:
                raise ValueError("Invalid visual feature range")
        if (len(self.chroma_frequency_hz) != 2
                or not 0 < self.chroma_frequency_hz[0] < self.chroma_frequency_hz[1] <= self.sample_rate / 2
                or len(self.chroma_hue_range) != 2
                or not 0 <= self.chroma_hue_range[0] < self.chroma_hue_range[1] <= 1
                or not 0 <= self.chroma_min_volume <= 1):
            raise ValueError("Invalid Chroma frequency, hue or gate range")
        if not 0 <= self.wave_floor <= 1:
            raise ValueError("Invalid wave_floor")
        for value in (self.drone_field_gain, self.volume_field_gain, self.decay_field_gain,
                      self.vocal_ribbon_gain, self.attack_bloom_gain, self.yell_bloom_gain,
                      self.pulse_gain, self.growl_texture):
            if not 0 <= value <= 4:
                raise ValueError("Invalid visual gain")
        if self.pixel_positions is not None:
            if len(self.pixel_positions) != self.pixel_count:
                raise ValueError("One position per physical pixel is required")
            for x, angle in self.pixel_positions:
                if not -1 <= x <= 1 or not 0 <= angle <= 1:
                    raise ValueError("Invalid pixel position")
        if self.radio_role not in ("off", "leader", "follower"):
            raise ValueError("Invalid radio_role")
        if not 1 <= self.radio_channel <= 11 or not 0 <= self.radio_group <= 65535:
            raise ValueError("Invalid radio channel or group")
        if len(bytes.fromhex(self.leader_mac.replace(":", ""))) != 6:
            raise ValueError("leader_mac must be six bytes")
        from effects import EFFECT_NAMES
        if not 0 <= self.effect_index < len(EFFECT_NAMES):
            raise ValueError("Invalid effect_index")
        if self.effect_indicator_rotation not in (0, 180):
            raise ValueError("effect_indicator_rotation must be 0 or 180")
        if self.effect_indicator_map is not None:
            if (len(self.effect_indicator_map) != 32
                    or any(type(i) is not int for i in self.effect_indicator_map)
                    or sorted(self.effect_indicator_map) != list(range(32))):
                raise ValueError("effect_indicator_map must permute pixel indices 0..31")
        button_pins = (self.button_next_gpio, self.button_extra_next_gpio, self.button_previous_gpio)
        for pin in button_pins:
            if pin in (5, 6, 9, 38):
                raise ValueError("Button conflicts with microphone or wing GPIO")
        enabled_pins = [pin for pin in button_pins if pin is not None]
        if len(set(enabled_pins)) != len(enabled_pins):
            raise ValueError("Buttons must use different GPIOs")


from node_config import OVERRIDES

CONFIG = Config(**OVERRIDES)
