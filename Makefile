PYTHON ?= python3
RB_LANGUAGE ?= en
PROFILE := profiles/rb-8g-chs255.json

.PHONY: all check layout report toolchain abi abi-check boot-test hdd hdd-check hdd-test hdd-ui-test menu-test scan-test volume-test handoff-test config-test state-test visibility-test profile-test audit-test journal-test profile-recovery-test fat-plan-test fat16-format-test fat32-format-test dos-guest-test install-plan-test rescue rescue-check rescue-test iso-deps rescue-iso rescue-iso-test

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

hdd:
	$(PYTHON) tools/build_hdd.py --language $(RB_LANGUAGE)

hdd-check:
	$(PYTHON) tools/build_hdd.py --language $(RB_LANGUAGE) --repeat

hdd-test: hdd-check
	$(PYTHON) tools/test_hdd.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_menu.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_scan.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_volume.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_handoff.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_config.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_state.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_visibility.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_profile.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_prepared_dos.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_dos_countdown.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_prepared_install_state.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_dos_verification.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_profile_menu.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_profile_switch.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_mixed_profiles.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_profile_scope.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_audit.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_journal.py --language $(RB_LANGUAGE)

hdd-ui-test: hdd-check
	$(PYTHON) tools/test_menu.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_scan.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_volume.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_handoff.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_config.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_state.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_visibility.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_profile.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_prepared_dos.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_dos_countdown.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_prepared_install_state.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_dos_verification.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_profile_menu.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_profile_switch.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_mixed_profiles.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_profile_scope.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_audit.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_journal.py --language $(RB_LANGUAGE)

menu-test: hdd
	$(PYTHON) tools/test_menu.py --language $(RB_LANGUAGE)

scan-test: hdd
	$(PYTHON) tools/test_scan.py --language $(RB_LANGUAGE)

volume-test: hdd
	$(PYTHON) tools/test_volume.py --language $(RB_LANGUAGE)

handoff-test: hdd
	$(PYTHON) tools/test_handoff.py --language $(RB_LANGUAGE)

config-test: hdd
	$(PYTHON) tools/test_config.py --language $(RB_LANGUAGE)

state-test: hdd
	$(PYTHON) tools/test_state.py --language $(RB_LANGUAGE)

visibility-test: hdd
	$(PYTHON) tools/test_visibility.py --language $(RB_LANGUAGE)

profile-test: hdd
	$(PYTHON) tools/test_profile.py --language $(RB_LANGUAGE)

audit-test: hdd
	$(PYTHON) tools/test_audit.py --language $(RB_LANGUAGE)

journal-test: hdd
	$(PYTHON) tools/test_journal.py --language $(RB_LANGUAGE)

profile-recovery-test:
	$(PYTHON) tools/build_hdd.py --language de
	$(PYTHON) tools/build_rescue.py --language en
	$(PYTHON) tools/build_rescue.py --language de
	$(PYTHON) tools/test_later_profile_recovery.py

fat-plan-test:
	$(PYTHON) tools/build_rescue.py --language en
	$(PYTHON) tools/build_rescue.py --language de
	$(PYTHON) tools/test_fat_format_plan.py
	$(PYTHON) tools/test_fat_format_review.py

fat16-format-test: format_bits = 16
fat32-format-test: format_bits = 32
fat16-format-test fat32-format-test:
	$(PYTHON) tools/build_rescue.py --language en
	$(PYTHON) tools/build_rescue.py --language de
	$(PYTHON) tools/test_fat_format_write.py --bits $(format_bits) --host-tools

dos-guest-test:
	$(PYTHON) tools/build_rescue.py --language en
	$(PYTHON) tools/build_rescue.py --language de
	$(PYTHON) tools/build_dos_guest.py
	$(PYTHON) tools/test_dos_guest.py

install-plan-test:
	$(PYTHON) tools/build_rescue.py --language en
	$(PYTHON) tools/build_rescue.py --language de
	$(PYTHON) tools/test_install_plan.py

.PHONY: install-view-test
install-view-test:
	$(PYTHON) tools/build_rescue.py --language en
	$(PYTHON) tools/build_rescue.py --language de
	$(PYTHON) tools/test_install_view.py

rescue:
	$(PYTHON) tools/build_rescue.py --language $(RB_LANGUAGE)

rescue-check:
	$(PYTHON) tools/build_rescue.py --language $(RB_LANGUAGE) --repeat

rescue-test: rescue-check
	$(PYTHON) tools/test_rescue.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_rescue_match.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_rescue_plan.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_rescue_stream.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_mbr_restart.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_mbr_reservation.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_mbr_original.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_mbr_target.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_mbr_ata_history.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_mbr_recovery_disk.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_backup_disk.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_mbr_first_witness.py --language $(RB_LANGUAGE)
	$(PYTHON) tools/test_mbr_approval.py --language $(RB_LANGUAGE)

iso-deps:
	$(PYTHON) -m pip install --require-hashes -r tools/requirements-iso.txt

rescue-iso:
	$(PYTHON) tools/build_rescue_iso.py --language $(RB_LANGUAGE) --repeat

rescue-iso-test: rescue-iso
	$(PYTHON) tools/test_rescue_match.py --language $(RB_LANGUAGE) --cdrom
	$(PYTHON) tools/test_rescue_match.py --language $(RB_LANGUAGE) --cdrom --bare
	$(PYTHON) tools/test_rescue_plan.py --language $(RB_LANGUAGE) --cdrom
	$(PYTHON) tools/test_rescue_plan.py --language $(RB_LANGUAGE) --cdrom --bare
