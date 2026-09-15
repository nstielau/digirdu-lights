.DEFAULT_GOAL := help
PYTHON ?= python3
VENV := .venv
PY := $(VENV)/bin/python
PORT ?=
CIRCUITPYTHON_VERSION := 10.3.1
BOARD ?= unexpectedmaker_feathers2
DEPLOY_BOARD = $(if $(filter file,$(origin BOARD)),auto,$(BOARD))
FIRMWARE_EXT := $(if $(filter unexpectedmaker_feathers2,$(BOARD)),uf2,bin)
FIRMWARE := .artifacts/firmware/adafruit-circuitpython-$(BOARD)-en_US-$(CIRCUITPYTHON_VERSION).$(FIRMWARE_EXT)
FIRMWARE_URL := https://downloads.circuitpython.org/bin/$(BOARD)/en_US/adafruit-circuitpython-$(BOARD)-en_US-$(CIRCUITPYTHON_VERSION).$(FIRMWARE_EXT)
MOUNT ?=
LEGACY_RAINBOW ?=
NODE_CONFIG ?=
BOARD_ARGS = --board '$(BOARD)' --port '$(PORT)' $(if $(MOUNT),--mount '$(MOUNT)')
ROM_FIRMWARE := .artifacts/firmware/adafruit-circuitpython-$(BOARD)-en_US-$(CIRCUITPYTHON_VERSION).bin

.PHONY: help setup ports firmware flash flash-rom deploy console check test-mic benchmark
help:
	@echo 'make setup    Install host tools into .venv'
	@echo 'make ports    List USB serial devices'
	@echo 'make flash    Install CircuitPython (FeatherS2: requires FTHRS2BOOT drive)'
	@echo 'make flash-rom Back up all flash, erase, install .bin in BOOT+RESET recovery mode'
	@echo 'make deploy   Upload app, preserve node profile, verify readback and startup'
	@echo '              NODE_CONFIG=examples/node_producer.py or examples/node_follower.py sets role'
	@echo '              Detects supported boards; BOARD=... enforces a specific model'
	@echo 'make console  Serial terminal (Ctrl-] exits; Ctrl-C stops; Ctrl-D restarts)'
	@echo 'make check    Check Python syntax and whitespace without hardware'
	@echo 'make test-mic Capture 10 seconds of microphone levels, then resume the app'
	@echo 'make benchmark Measure live FFT/render timing for 5 seconds, then resume the app'
	@echo 'Default board: unexpectedmaker_feathers2; old board: BOARD=adafruit_feather_esp32_v2'
	@echo 'Optional: PORT=/dev/cu.usbserial-... overrides automatic port selection'

setup: $(VENV)/.ready
$(VENV)/.ready: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -r requirements.txt
	touch $@

ports: setup
	$(PY) tools/board.py ports

firmware: $(FIRMWARE)
$(FIRMWARE):
	mkdir -p .artifacts/firmware
	curl -fL --retry 3 --connect-timeout 15 '$(FIRMWARE_URL)' -o '$@.tmp'
	mv '$@.tmp' '$@'

flash: setup firmware
	$(PY) tools/board.py flash $(BOARD_ARGS) --firmware '$(FIRMWARE)'

flash-rom: setup
	mkdir -p .artifacts/firmware
	curl -fL --retry 3 --connect-timeout 15 'https://downloads.circuitpython.org/bin/$(BOARD)/en_US/adafruit-circuitpython-$(BOARD)-en_US-$(CIRCUITPYTHON_VERSION).bin' -o '$(ROM_FIRMWARE).tmp'
	mv '$(ROM_FIRMWARE).tmp' '$(ROM_FIRMWARE)'
	$(PY) tools/board.py flash-rom $(BOARD_ARGS) --firmware '$(ROM_FIRMWARE)'

deploy: setup check
	$(PY) tools/board.py deploy --board '$(DEPLOY_BOARD)' --port '$(PORT)' $(if $(MOUNT),--mount '$(MOUNT)') $(if $(NODE_CONFIG),--node-config '$(NODE_CONFIG)') $(if $(filter 1,$(LEGACY_RAINBOW)),--legacy-rainbow)

console: setup
	$(PY) tools/board.py console $(BOARD_ARGS)

test-mic: setup
	$(PY) tools/board.py test-mic $(BOARD_ARGS)

benchmark: setup
	$(PY) tools/board.py benchmark $(BOARD_ARGS)

$(VENV)/.dev-ready: $(VENV)/.ready requirements-dev.txt
	$(PY) -m pip install -r requirements-dev.txt
	touch $@

check: $(VENV)/.dev-ready
	$(PY) -m py_compile code.py config.py node_config.py audio_spectrum.py audio_features.py animation.py effects.py radio_protocol.py wireless.py sound_reactive.py examples/esp32_rainbow.py examples/node_follower.py examples/node_producer.py tools/board.py
	$(PY) -m unittest discover -s tests
	git diff --check
