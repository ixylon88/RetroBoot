PYTHON ?= python3
PROFILE := profiles/rb-8g-chs255.json

.PHONY: all check layout report toolchain abi abi-check boot-test

all: check

check:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) tools/retroboot_layout.py $(PROFILE)

layout:
	$(PYTHON) tools/retroboot_layout.py $(PROFILE)

report:
	@$(PYTHON) tools/retroboot_layout.py $(PROFILE) --json

toolchain:
	$(PYTHON) tools/setup_toolchain.py

abi:
	$(PYTHON) tools/build_abi_probe.py

abi-check:
	$(PYTHON) tools/build_abi_probe.py --repeat

boot-test: abi-check
	$(PYTHON) tools/test_abi_probe.py
