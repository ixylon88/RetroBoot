"""Compatibility entry point for FAT16-only media preparation."""
from prepare_fat_format import TICKET_CLUSTER, TICKET_LBA, ticketed_floppy as _ticketed_floppy


def ticketed_floppy(floppy, plan, backup, slot, heads, spt):
    if not 1 <= slot <= 4 or plan['primary'][slot - 1].get('fat', {}).get('bits') != 16:
        raise ValueError('Unsupported FAT16 metadata range')
    return _ticketed_floppy(floppy, plan, backup, slot, heads, spt)
