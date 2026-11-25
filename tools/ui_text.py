"""Compile readable UTF-8 menu catalogs into exact CP437 C string literals."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ("en", "de")
ERROR_KEYS = tuple("ERROR_" + name for name in (
    "OK", "IO", "SIGNATURE", "IDENTITY", "FLAGS", "TYPE", "EMPTY",
    "OVERFLOW", "RANGE", "OVERLAP", "EXTENDED", "SLOTS", "LOOP", "LIMIT"))
VOLUME_KEYS = tuple("VOLUME_" + name for name in (
    "OK", "IO", "SIGNATURE", "JUMP", "SECTOR", "CLUSTER", "RESERVED", "FATS",
    "ROOT", "TOTAL", "HIDDEN", "LAYOUT", "TYPE", "FAT_SIZE", "FAT32", "RANGE",
    "UNSUPPORTED", "MEDIA"))
TIMER_KEYS = tuple("TIMER_" + name for name in (
    "HELP", "TITLE", "SAVED", "NEW", "TARGET", "RANGE", "KEYS", "CONFIRM", "BACK", "OK",
    "DISK", "RECORDS", "CHANGED", "FULL", "WRITE", "READBACK", "UNCHANGED"))
KEYS = (
    "SYSTEM_INFO", "PARTITIONS", "RECOVERY", "READ_ONLY", "BOOT_MENU",
    "DOS_GEOMETRY", "DOS_TIMER", "DOS_BLOCKED", "DOS_RECOVERY_REQUIRED", "DOS_BASELINE", "NO_PROFILES", "AUTO_OFF", "DRIVE", "DRIVE_HEX", "ROUTE", "ROUTE_EDD",
    "ROUTE_CHS", "REACHABLE", "DISK_ID", "BOOT_SNAPSHOT", "CHS_HEADS",
    "CHS_SECTORS", "EDD_GEOMETRY", "PARTITION_TITLE", "SCAN_FAILED", "SCAN_OK",
    "TABLE_HEADER", "LBA_HEX", "ENTRY", "WHOLE_SECTOR", "NO_CHANGES",
    "SCAN_HELP", "PAGE", "PAGING", "RECOVERY_MISSING", "RECOVERY_PAGES",
    "RECOVERY_READ_ONLY", "KEY_HELP", "FUNCTION_HELP",
    "VOLUME_TITLE", "VOLUME_SCOPE", "VOLUME_NONE", "VOLUME_ENTRY", "VOLUME_PTYPE",
    "VOLUME_LBA", "VOLUME_KIND", "VOLUME_BYTES", "VOLUME_TOTAL_LABEL",
    "VOLUME_CLUSTERS", "VOLUME_DATA", "VOLUME_HELP",
    "HANDOFF_HELP", "HANDOFF_FAILED", "HANDOFF_REASON",
    "HANDOFF_TARGET", "HANDOFF_CODE", "HANDOFF_RETRY",
    "CONFIG_TITLE",
    "CONFIG_DEGRADED",
    "CONFIG_SCOPE",
    "CONFIG_COPIES",
    "CONFIG_OK",
    "CONFIG_MISSING",
    "CONFIG_FORMAT",
    "CONFIG_CRC",
    "CONFIG_IDENTITY",
    "CONFIG_PROFILE",
    "CONFIG_CONFLICT",
    "CONFIG_ADMIN",
    "CONFIG_DIRECTORY",
    "CONFIG_FAT",
    "CONFIG_DETAIL",
    "CONFIG_GENERATION",
    "CONFIG_IDENTITY_LABEL",
    "CONFIG_EMPTY",
    "CONFIG_ENTRY",
    "CONFIG_EXTENT",
    "CONFIG_FLAGS",
    "CONFIG_HELP",
    "STATE_TITLE",
    "STATE_SCOPE",
    "STATE_CONFIG_COPIES",
    "STATE_COPIES",
    "STATE_MEDIA",
    "STATE_REASON",
    "STATE_INSTALL_ID",
    "STATE_CRC",
    "STATE_HELP",
    "STATE_MATCH",
    "STATE_CONFIG",
    "STATE_RECORD",
    "STATE_DEGRADED",
    "STATE_LEGACY",
    "STATE_IDENTITY",
    "STATE_EMPTY",
    "STATE_PENDING",
    "STATE_INSTALLATION",
    "STATE_TARGET",
    "STATE_NOT_READY",
    "STATE_APPROVAL",
    "STATE_SCAN",
    "STATE_LAYOUT",
    "STATE_VOLUME",
    "STATE_VBR",
    "PROFILE_TEST_HELP",
    "PROFILE_TEST_FAILED",
    "PROFILE_TEST_SELECTION",
    "PROFILE_TEST_PROOF",
    "PROFILE_TEST_CHANGE",
    "PROFILE_TEST_TARGET",
    "PROFILE_TEST_CODE",
    "PROFILE_TEST_REASON",
    "PROFILE_TEST_REVIEW",
    "AUDIT_HELP",
    "AUDIT_TITLE",
    "AUDIT_SCOPE",
    "AUDIT_OK",
    "AUDIT_SCAN",
    "AUDIT_ADMIN",
    "AUDIT_IO",
    "AUDIT_ROOT",
    "AUDIT_CHAIN",
    "AUDIT_SHARED",
    "AUDIT_COPIES",
    "AUDIT_HEADER",
    "AUDIT_ORPHAN",
    "AUDIT_CHANGED",
    "AUDIT_BOOTSTRAP",
    "AUDIT_CODES",
    "AUDIT_COLUMNS",
    "AUDIT_CLUSTERS",
    "AUDIT_ERROR_FILE",
    "AUDIT_REVIEW",
    "AUDIT_LIMIT",
    "JOURNAL_TITLE",
    "JOURNAL_SCOPE",
    "JOURNAL_ALLOCATION",
    "JOURNAL_CONFIG",
    "JOURNAL_STATE",
    "JOURNAL_IDENTITY",
    "JOURNAL_IO",
    "JOURNAL_CHANGED",
    "JOURNAL_INVALID",
    "JOURNAL_BASELINE",
    "JOURNAL_PREPARED_OLD",
    "JOURNAL_PREPARED_NEW",
    "JOURNAL_COMMITTED_NEW",
    "JOURNAL_DIVERGED",
    "JOURNAL_LOAD_CODES",
    "JOURNAL_COPY_CODES",
    "JOURNAL_SEQUENCE",
    "JOURNAL_PHASE",
    "JOURNAL_CRCS",
    "JOURNAL_HELP",
    "VIS_TITLE",
    "VIS_SCOPE",
    "VIS_CODES",
    "VIS_COLUMNS",
    "VIS_VISIBLE",
    "VIS_ACTIVE",
    "VIS_CHANGED",
    "VIS_HELP",
    "VIS_MATCH",
    "VIS_CHANGE",
    "VIS_BLOCKED",
    "VIS_ADMIN",
) + ERROR_KEYS + VOLUME_KEYS + TIMER_KEYS
# Most text begins at column 4 and must end before the frame at column 78.
WIDTHS = dict.fromkeys(KEYS, 74)
WIDTHS.update(TIMER_SAVED=26, TIMER_NEW=26, TIMER_TARGET=26, SYSTEM_INFO=67, PARTITIONS=67, RECOVERY=67, READ_ONLY=13,
              DRIVE=15, DRIVE_HEX=25, ROUTE=25, DISK_ID=25, CHS_HEADS=13,
              CHS_SECTORS=16, LBA_HEX=19, ENTRY=19, WHOLE_SECTOR=55,
              PAGE=6, PAGING=58, VOLUME_ENTRY=25, VOLUME_PTYPE=9, VOLUME_LBA=25,
              VOLUME_KIND=25, VOLUME_BYTES=25, VOLUME_TOTAL_LABEL=25,
              VOLUME_CLUSTERS=25, VOLUME_DATA=25, CONFIG_COPIES=25, CONFIG_DETAIL=25,
              CONFIG_GENERATION=25, CONFIG_IDENTITY_LABEL=25, CONFIG_ENTRY=25,
              CONFIG_EXTENT=25, CONFIG_FLAGS=27, STATE_CONFIG_COPIES=25, STATE_COPIES=25,
              STATE_MEDIA=25, STATE_REASON=25, STATE_INSTALL_ID=25, STATE_CRC=25,
              VIS_CODES=26, VIS_VISIBLE=26, VIS_ACTIVE=26, VIS_CHANGED=26,
              JOURNAL_LOAD_CODES=28, JOURNAL_COPY_CODES=28, JOURNAL_SEQUENCE=28, JOURNAL_PHASE=28, JOURNAL_CRCS=28,
              AUDIT_CODES=28, AUDIT_ERROR_FILE=28, AUDIT_CLUSTERS=34)


def output_name(kind, language):
    if language not in LANGUAGES or kind not in ("hdd", "hdd-repeat", "menu", "scan", "volume", "handoff", "config", "state", "visibility", "profile", "audit", "journal"):
        raise ValueError("Unknown build language or output kind")
    return kind if language == "en" else kind + "-" + language


def catalog_path(language):
    if language not in LANGUAGES:
        raise ValueError("Unsupported menu language")
    return ROOT / "ui" / (language + ".json")


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate UI text key: " + key)
        result[key] = value
    return result


def validate_catalog(strings):
    if not isinstance(strings, dict) or set(strings) != set(KEYS):
        raise ValueError("UI catalog must contain exactly the supported text keys")
    for key, value in strings.items():
        if not isinstance(value, str) or not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Empty text or control character in UI catalog: " + key)
        try:
            encoded = value.encode("cp437")
        except UnicodeEncodeError as error:
            raise ValueError("Text is not representable in CP437: " + key) from error
        if len(encoded) > WIDTHS[key]:
            raise ValueError("UI text exceeds its screen field: " + key)
    return strings


def load_catalog(language):
    return validate_catalog(json.loads(catalog_path(language).read_text(encoding="utf-8"),
                                       object_pairs_hook=unique_keys))


def c_literal(value):
    # Exactly three octal digits prevent the next source character from
    # becoming part of an escape. ASCII output avoids compiler locale rules.
    return '"' + "".join(f"\\{byte:03o}" for byte in value.encode("cp437")) + '"'


def render_header(strings, language):
    catalog_path(language)
    validate_catalog(strings)
    lines = ["/* Generated from ui/" + language + ".json; CP437 bytes. */",
             "#ifndef RB_UI_TEXT_H", "#define RB_UI_TEXT_H",
             '#define RB_UI_LANGUAGE "' + language + '"']
    lines.extend("#define RB_UI_" + key + " " + c_literal(strings[key]) for key in KEYS)
    return "\n".join(lines + ["#endif", ""])


def catalog_metadata(language):
    return {"language": language, "encoding": "cp437",
            "catalog_sha256": hashlib.sha256(catalog_path(language).read_bytes()).hexdigest()}


def checked_catalog(manifest, language):
    if manifest.get("ui") != catalog_metadata(language):
        raise ValueError("Built language/catalog differs from the requested UI tests")
    return load_catalog(language)
