import importlib.util
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class HardwareTests(unittest.TestCase):
    def test_profiles_and_reserved_pins(self):
        self.assertIsNotNone(importlib.util.find_spec('hardware'), 'shared profiles missing')
        from hardware import profile, validate_pins
        s3 = profile('adafruit_feather_esp32s3_reverse_tft')
        self.assertEqual(s3['wing'], 'D6')
        self.assertEqual(s3['mic'], ('D5', 'D9', 'D10'))
        self.assertEqual(profile('unexpectedmaker_feathers2')['wing'], 'IO38')
        self.assertEqual(profile('adafruit_feather_esp32_v2')['wing'], 'D32')
        for pins in ((5, 6, 10), (5, 9, 9), (35, 9, 10), (0, 9, 10)):
            with self.assertRaises(ValueError): validate_pins(s3, pins)
        with self.assertRaises(ValueError): profile('unknown')

    def test_max17048_voltage_soc_and_unlock(self):
        import battery
        self.assertTrue(hasattr(battery, 'read_gauge'), 'fuel gauge reader missing')
        class Bus:
            unlocked = False
            def try_lock(self): return True
            def unlock(self): self.unlocked = True
            def writeto_then_readfrom(self, address, command, response):
                self_address = 0x36
                assert address == self_address
                value = {8: 0x0012, 2: 48000, 4: 75 * 256}[command[0]]
                response[:] = value.to_bytes(2, 'big')
        bus = Bus()
        with patch.dict(sys.modules, {'board': SimpleNamespace(I2C=lambda: bus)}):
            result = battery.read_gauge()
        self.assertEqual(result, {'status':'measured', 'voltage':3.75, 'percent':75.0})
        self.assertTrue(bus.unlocked)
        bus.try_lock = lambda: False
        with patch.dict(sys.modules, {'board':SimpleNamespace(I2C=lambda: bus)}):
            self.assertEqual(battery.read_gauge()['status'], 'read_error')
        bus.try_lock = lambda: True
        bus.writeto_then_readfrom = lambda a, c, r: r.__setitem__(slice(None), b'\xff\xff')
        with patch.dict(sys.modules, {'board':SimpleNamespace(I2C=lambda: bus)}):
            self.assertEqual(battery.read_gauge()['status'], 'unsupported')
