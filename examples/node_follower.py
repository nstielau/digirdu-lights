"""Deploy with NODE_CONFIG=examples/node_follower.py to a FeatherS2 or ESP32 V2 receiver.

This example wing spans -0.6..-0.4 of the culvert's half-length coordinate.
Change positions for each node, or use identical positions to mirror the preview.
No microphone is initialized on a follower.
"""

OVERRIDES = {
    "radio_role": "consumer",
    "leader_mac": "7c:df:a1:03:4c:2c",
    "radio_group": 1,
    "radio_channel": 1,
    "pixel_count": 32,
    "pixel_positions": tuple((-0.6 + 0.2 * i / 31, 0.0) for i in range(32)),
}
