PYTHON ?= python3
PROFILE := profiles/rb-8g-chs255.json

.PHONY: all check layout report

all: check

check:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) tools/retroboot_layout.py $(PROFILE)

layout:
	$(PYTHON) tools/retroboot_layout.py $(PROFILE)

report:
	@$(PYTHON) tools/retroboot_layout.py $(PROFILE) --json
