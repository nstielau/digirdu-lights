"""Offline animation replay uses generated feature logs, never private takes."""
import json
import math
from pathlib import Path
import tempfile
import unittest

from animation import CulvertAnimation
from audio_features import AudioFeatures
from config import Config
from effects import spectrum_frequency
from radio_protocol import Transmitter, Receiver
from tools.replay import read_records, feature_frames, calibration, render_replay


class ChromaTests(unittest.TestCase):
    def test_frequency_relative_power_and_silent_spectrum(self):
        centers = tuple(math.sqrt(a*b) for a,b in zip(Config.spectrum_edges, Config.spectrum_edges[1:]))
        self.assertEqual(spectrum_frequency((0,)*8, centers, .6), 0)
        levels = (.2,.4,.1,.1,0,0,0,0)
        hz = spectrum_frequency(levels, centers, .6)
        self.assertAlmostEqual(hz, spectrum_frequency(tuple(v*.5 for v in levels), centers, .6))
        self.assertAlmostEqual(spectrum_frequency((0,0,1,0,0,0,0,0), centers, .6), centers[2])

    def test_color_brightness_independence_and_blending(self):
        c = Config(effect_index=4)
        a = CulvertAnimation(c)
        f = AudioFeatures()
        f.volume = .5
        f.spectrum = (0,1,0,0,0,0,0,0)
        low = a.render(f, 10)
        self.assertEqual(max(low), int(.5*.15*255))
        f.spectrum = (0,0,0,1,0,0,0,0)
        a.render(f, .05)
        self.assertGreater(a.chroma_position, 0)
        self.assertLess(a.chroma_position, 1)
        high = a.render(f, 10)
        self.assertNotEqual(low, high)
        self.assertEqual(max(low), max(high))
        position = a.chroma_position
        f.volume = 1
        brighter = a.render(f, 10)
        self.assertAlmostEqual(a.chroma_position, position, places=6)
        self.assertEqual(max(brighter), 38)
        f.volume = 0
        f.spectrum = (1,0,0,0,0,0,0,0)
        fade = a.render(f, .1)
        self.assertTrue(any(fade))
        self.assertLess(max(fade), max(brighter))
        self.assertAlmostEqual(a.chroma_position, position, places=6)
        self.assertEqual(a.render(f, 20), bytes(96))

    def test_chroma_radio_round_trip_and_indicator(self):
        c = Config(effect_index=4)
        a = CulvertAnimation(c)
        f = AudioFeatures()
        f.volume = .7
        f.spectrum = (.2,.5,.4,.1,0,0,0,0)
        packet = Transmitter(c, 1).encode(f,a,0)
        self.assertEqual(len(packet), 51)
        receiver = Receiver(c)
        self.assertTrue(receiver.accept(receiver.leader, packet, 0))
        self.assertEqual(receiver.effect, 4)
        other = CulvertAnimation(Config())
        other.set_effect(receiver.effect)
        self.assertTrue(any(other.render(receiver.features,.032)))
        # After the HUD, both use the same centroid with only byte quantization error.
        for _ in range(100):
            x=a.render(f,.064)
            y=other.render(receiver.features,.064)
        self.assertLessEqual(max(abs(i-j) for i,j in zip(x,y)), 1)

    def test_invalid_tuning(self):
        for kw in ({'chroma_frequency_hz':(350,150)}, {'chroma_hue_range':(1,0)},
                   {'chroma_color_s':0}, {'chroma_min_volume':2}):
            with self.assertRaises(ValueError):
                Config(**kw)


class ReplayTests(unittest.TestCase):
    def fixture(self):
        return [
            {'elapsed_s':0, 'section':'drone', 'line':'AUDIO vol=0.7 drone=1 active=True'},
            {'elapsed_s':.001, 'section':'drone', 'line':'SPECTRUM levels=(0,1,0,0,0,0,0,0)'},
            {'elapsed_s':.11, 'section':'drone', 'line':'ATTACK strength=0.8'},
            {'elapsed_s':.16, 'section':'drone', 'line':'YELL vocal=0.9'},
            {'elapsed_s':1, 'section':'drone', 'line':'AUDIO vol=0.7 drone=1 active=True'},
            {'elapsed_s':1.001, 'section':'drone', 'line':'SPECTRUM levels=(0,0,1,0,0,0,0,0)'}]

    def read_fixture(self, rows):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'take.jsonl'
            p.write_text('\n'.join(json.dumps(row) for row in rows))
            return read_records(p)

    def test_event_once_age_and_held_levels_then_explicit_tail(self):
        records = self.read_fixture(self.fixture())
        attacks, yells = [], []
        for now, section, f in feature_frames(records, Config(),20,1):
            if f.attackEvent:
                attacks.append((now,f.attackAge,f.attack))
            if f.yellEvent:
                yells.append((now,f.yellAge,f.vocal))
            if .3 < now < .9:
                self.assertEqual(f.volume,.7)
                self.assertEqual(f.vocal,0)
            if now > 1.001:
                self.assertIn('synthetic',section)
                self.assertEqual(f.volume,0)
        self.assertEqual(len(attacks),1)
        self.assertEqual(len(yells),1)
        self.assertAlmostEqual(attacks[0][1],.04)
        self.assertAlmostEqual(yells[0][1],.04)
        self.assertEqual(yells[0][2],.9)
        self.assertEqual(attacks[0][2],.8)

    def test_percentiles_and_renderer_output_deterministic(self):
        records=self.read_fixture(self.fixture())
        report=calibration(records,Config())
        self.assertEqual(report['active_spectrum_samples'],2)
        self.assertLess(report['frequency_p10_p90_hz'][0],report['frequency_p10_p90_hz'][1])
        result=render_replay(records,Config(),10,0)
        self.assertEqual(result,render_replay(records,Config(),10,0))
        self.assertEqual(len(result['names']),5)
        import base64
        self.assertTrue(all(len(base64.b64decode(f))==5*96 for f in result['frames']))

    def test_bad_timestamps_or_spectrum_fail_clearly(self):
        rows=self.fixture()
        rows[-1]['elapsed_s']=-1
        with self.assertRaises(ValueError):
            self.read_fixture(rows)
        rows=self.fixture()
        rows[1]['line']='SPECTRUM levels=(0,1)'
        with self.assertRaises(ValueError):
            self.read_fixture(rows)
