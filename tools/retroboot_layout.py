"""Validate a planned CHS layout. Read JSON and print a report; never open a disk.

This is a host-side arithmetic check, not a partition-table parser or formatter.
The phase-1 reference fixture supplies sizes and roles, never the implementation.
"""

import argparse
import json
import sys
from pathlib import Path

SECTOR_SIZE = 512
UINT32_MAX = (1 << 32) - 1
FAT_TYPES = {0x06: 16, 0x16: 16, 0x0E: 16, 0x1E: 16,
             0x0B: 32, 0x1B: 32, 0x0C: 32, 0x1C: 32}


class LayoutError(ValueError):
    """Invalid or unsupported plan, reported without a Python traceback."""


def require(condition, message):
    if not condition:
        raise LayoutError(message)


def integer(value, field, minimum=1, maximum=UINT32_MAX):
    require(type(value) is int and minimum <= value <= maximum,
            f"{field}: integer in {minimum}..{maximum} required")
    return value


def text(value, field):
    require(isinstance(value, str) and bool(value.strip()),
            f"{field}: nonempty text required")
    require(all(char.isprintable() for char in value),
            f"{field}: control characters are not allowed")
    return value


def fields(value, required, optional, context):
    require(isinstance(value, dict), f"{context}: object required")
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    require(not missing, f"{context}: missing fields {sorted(missing)}")
    require(not extra, f"{context}: unknown fields {sorted(extra)}")


def chs(lba, geometry):
    """Return C/H/S and the three bytes used in an MBR entry; no saturation."""
    integer(lba, "LBA", 0)
    cylinders, heads, spt = geometry
    require(lba < cylinders * heads * spt, f"LBA {lba}: outside CHS reach")
    cylinder, remainder = divmod(lba, heads * spt)
    head, sector = divmod(remainder, spt)
    sector += 1
    return {"cylinder": cylinder, "head": head, "sector": sector,
            "encoded_hex": bytes((head, sector | ((cylinder >> 2) & 0xC0),
                                  cylinder & 0xFF)).hex()}


def fat_geometry(total_sectors, bits, sectors_per_cluster, sectors_per_fat=None):
    """Check a planned FAT size or calculate the smallest sufficient size.

    Binary search avoids the two-value oscillation of fixed-point iteration.
    The two FATs and rounded FAT16 root directory reduce the data area.
    """
    integer(total_sectors, "FAT total_sectors")
    integer(bits, "FAT bits", 16, 32)
    require(bits in (16, 32), "FAT: only FAT16/FAT32 are supported")
    integer(sectors_per_cluster, "sectors_per_cluster", 1, 64)
    require(sectors_per_cluster & (sectors_per_cluster - 1) == 0,
            "sectors_per_cluster: power of two required (maximum 32 KiB)")
    reserved = 1 if bits == 16 else 32
    root_entries = 512 if bits == 16 else 0
    root_sectors = (root_entries * 32 + SECTOR_SIZE - 1) // SECTOR_SIZE
    available = total_sectors - reserved - root_sectors
    require(available >= 2 + sectors_per_cluster, "FAT: volume too small")
    entry_bytes = bits // 8
    low, high = 1, available // 2
    while low < high:
        middle = (low + high) // 2
        clusters = (available - 2 * middle) // sectors_per_cluster
        if middle * SECTOR_SIZE // entry_bytes >= clusters + 2:
            high = middle
        else:
            low = middle + 1
    minimum = low
    if sectors_per_fat is None:
        sectors_per_fat = minimum
    else:
        integer(sectors_per_fat, "sectors_per_fat")
        require(sectors_per_fat >= minimum, "FAT: table too small for data-cluster entries")
    data_sectors = available - 2 * sectors_per_fat
    clusters = data_sectors // sectors_per_cluster
    # The FAT type is determined by cluster count, not by a label in the BPB.
    if bits == 16:
        require(4085 <= clusters < 65525, "FAT16: cluster count outside 4085..65524")
        require(sectors_per_fat <= 65535, "FAT16: FAT size does not fit BPB")
    else:
        require(65525 <= clusters < 0x0FFFFFF0 - 1,
                "FAT32: cluster count outside the data-cluster range")
    return {"bits": bits, "sectors_per_cluster": sectors_per_cluster,
            "reserved_sectors": reserved, "fat_copies": 2,
            "root_entries": root_entries, "root_directory_sectors": root_sectors,
            "sectors_per_fat": sectors_per_fat, "minimum_sectors_per_fat": minimum,
            "data_clusters": clusters,
            "fat_capacity_entries": sectors_per_fat * SECTOR_SIZE // entry_bytes,
            "unused_data_sectors": data_sectors % sectors_per_cluster}


def disjoint(spans, context):
    """Check half-open intervals, allowing adjacency but no containment."""
    ordered = sorted(spans)
    for previous, current in zip(ordered, ordered[1:]):
        require(previous[1] <= current[0],
                f"{context}: overlap between {previous[2]} and {current[2]}")


def validate_plan(plan):
    fields(plan, ("format_version", "name", "sector_size", "disk_bytes",
                  "geometry", "primary", "logical"), (), "plan")
    integer(plan["format_version"], "format_version", 1, 1)
    name = text(plan["name"], "name")
    integer(plan["sector_size"], "sector_size", SECTOR_SIZE, SECTOR_SIZE)
    disk_bytes = integer(plan["disk_bytes"], "disk_bytes", SECTOR_SIZE,
                         (UINT32_MAX + 1) * SECTOR_SIZE)
    require(disk_bytes % SECTOR_SIZE == 0, "disk_bytes: incomplete sector")
    disk_sectors = disk_bytes // SECTOR_SIZE
    g = plan["geometry"]
    fields(g, ("cylinders", "heads", "sectors_per_track"), (), "geometry")
    geometry = (integer(g["cylinders"], "cylinders", 1, 1024),
                integer(g["heads"], "heads", 1, 255),
                integer(g["sectors_per_track"], "sectors_per_track", 1, 63))
    require(disk_sectors <= geometry[0] * geometry[1] * geometry[2],
            "disk: outside CHS reach; this tool only validates CHS profiles")
    primary, logical = plan["primary"], plan["logical"]
    require(isinstance(primary, list) and 1 <= len(primary) <= 4,
            "primary: one to four MBR entries required")
    require(isinstance(logical, list) and bool(logical),
            "logical: at least the RetroBoot volume is required")

    seen_ids, volumes, extended, ebrs = set(), [], [], []
    primary_spans, logical_spans = [], []
    for category, entries in (("primary", primary), ("logical", logical)):
        for index, entry in enumerate(entries):
            context = f"{category}[{index}]"
            required = ["id", "role", "type", "start_lba", "sectors"]
            if category == "logical":
                required.append("ebr_lba")
            fields(entry, required, ("fat",), context)
            identity = text(entry["id"], f"{context}.id")
            require(identity not in seen_ids, f"duplicate id: {identity}")
            seen_ids.add(identity)
            role = text(entry["role"], f"{identity}.role")
            allowed = ("system", "extended") if category == "primary" else ("shared", "retroboot")
            require(role in allowed, f"{identity}: unsupported {category} role {role}")
            ptype = integer(entry["type"], f"{identity}.type", 1, 255)
            start = integer(entry["start_lba"], f"{identity}.start_lba")
            count = integer(entry["sectors"], f"{identity}.sectors")
            end = start + count  # Exclusive; use unbounded host arithmetic before checking.
            require(end <= UINT32_MAX + 1, f"{identity}: 32-bit LBA overflow")
            require(end <= disk_sectors, f"{identity}: outside disk")
            report = {"id": identity, "role": role, "kind": category,
                      "type_hex": f"{ptype:02X}", "start_lba": start,
                      "sectors": count, "end_lba": end - 1,
                      "start_chs": chs(start, geometry), "end_chs": chs(end - 1, geometry)}
            span = (start, end, identity)
            if category == "primary":
                report["slot"] = index + 1  # Preserve MBR order, never sort by OS or address.
                primary_spans.append(span)
            else:
                ebr = integer(entry["ebr_lba"], f"{identity}.ebr_lba")
                require(ebr < start, f"{identity}: EBR must precede its data volume")
                logical_spans.extend((span, (ebr, ebr + 1, f"EBR({identity})")))
                report["ebr_lba"] = ebr
                report["data_relative_lba"] = start - ebr
                ebrs.append(report)
            if role == "extended":
                require(ptype == 0x05, f"{identity}: CHS container requires type 05h")
                require("fat" not in entry, f"{identity}: extended container has no FAT")
                extended.append(span)
            else:
                require(ptype in FAT_TYPES, f"{identity}: unsupported partition type {ptype:02X}h")
                require("fat" in entry, f"{identity}: FAT parameters required")
                fat = entry["fat"]
                fields(fat, ("bits", "sectors_per_cluster"), ("sectors_per_fat",), f"{identity}.fat")
                require(type(fat["bits"]) is int and fat["bits"] == FAT_TYPES[ptype],
                        f"{identity}: partition type and FAT width disagree")
                if "sectors_per_fat" in fat:
                    integer(fat["sectors_per_fat"], f"{identity}.sectors_per_fat")
                report["fat"] = fat_geometry(count, **fat)
                if role == "retroboot":
                    require(ptype == 0x16, "RetroBoot must be hidden FAT16 (16h)")
            volumes.append(report)

    require(len(extended) == 1, "exactly one extended container required")
    require(sum(v["role"] == "retroboot" for v in volumes) == 1,
            "exactly one logical RetroBoot volume required")
    disjoint(primary_spans, "primary partitions")
    disjoint(logical_spans, "logical volumes/EBRs")
    ext_start, ext_end, _ = extended[0]
    for start, end, identity in logical_spans:
        require(ext_start <= start < end <= ext_end,
                f"{identity}: outside extended container")
    require(ebrs[0]["ebr_lba"] == ext_start, "first EBR must start at the extended base")
    for index, entry in enumerate(ebrs):
        next_ebr = ebrs[index + 1]["ebr_lba"] if index + 1 < len(ebrs) else None
        require(next_ebr is None or entry["ebr_lba"] < next_ebr,
                "EBR plan must be in strictly increasing chain order")
        entry["next_ebr_relative_lba"] = None if next_ebr is None else next_ebr - ext_start

    return {"report_version": 1, "name": name, "status": "arithmetic-check-only",
            "sector_size": SECTOR_SIZE, "disk_bytes": disk_bytes,
            "disk_sectors": disk_sectors, "geometry": dict(g),
            "chs_capacity_sectors": geometry[0] * geometry[1] * geometry[2],
            "trailing_free_sectors": disk_sectors - max(s[1] for s in primary_spans),
            "volumes": volumes}


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_plan(path):
    if not path.is_file():
        raise LayoutError(f"{path}: regular JSON file required")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)


def render_text(report):
    lines = [f"{report['name']}: arithmetic checks passed",
             f"Disk: {report['disk_bytes']} bytes / {report['disk_sectors']} sectors",
             "ID              start LBA      end LBA     sectors   FAT   SPF  clusters"]
    for v in report["volumes"]:
        fat = v.get("fat")
        summary = (f"{fat['bits']:>5} {fat['sectors_per_fat']:>5} {fat['data_clusters']:>9}"
                   if fat else "    -     -         -")
        lines.append(f"{v['id']:<12} {v['start_lba']:>12} {v['end_lba']:>12} {v['sectors']:>11} {summary}")
    lines.append("No image created; no BIOS, boot or OS compatibility verified.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, help="JSON layout plan (read only)")
    parser.add_argument("--json", action="store_true", help="deterministic JSON report on stdout")
    args = parser.parse_args(argv)
    try:
        report = validate_plan(load_plan(args.plan))
    except (OSError, UnicodeError, ValueError) as error:
        print(f"RetroBoot layout: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
          if args.json else render_text(report))
    return 0


if __name__ == "__main__":
    # Keep redirected reports byte-identical across host locales and platforms.
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stderr.reconfigure(encoding="utf-8", newline="\n")
    sys.exit(main())
