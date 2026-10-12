"""Application release identity; independent of the USB-managed base."""
APP_VERSION = "1.0.9"
APP_API_VERSION = 1
# Release targets and ESP-NOW capabilities belong to the app, not the USB base.
APP_BOARDS = ("unexpectedmaker_feathers2", "adafruit_feather_esp32_v2")
APP_ROLES = ("producer", "consumer")
PROTOCOL_SEND = 3
PROTOCOL_RECEIVE = (3,)
