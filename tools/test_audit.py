"""Exercise F10 through real BIOS reads, keys, VGA and unchanged owned media."""
import argparse
import json
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

try:
    from .build_hdd import ROOT, prepare_output, sha256
    from .test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
    from .test_menu import Qmp, check_screen, screen_rows, wait_marker
    from .ui_text import LANGUAGES, checked_catalog, output_name
except ImportError:
    from build_hdd import ROOT, prepare_output, sha256
    from test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
    from test_menu import Qmp, check_screen, screen_rows, wait_marker
    from ui_text import LANGUAGES, checked_catalog, output_name

REASONS = ('OK', 'SCAN', 'ADMIN', 'IO', 'ROOT', 'CHAIN', 'SHARED', 'COPIES',
           'HEADER', 'ORPHAN', 'CHANGED', 'BOOTSTRAP')
NAMES = ('RBBOOT.SYS', 'RBSTG2.BIN', 'RBCFG.A', 'RBCFG.B', 'RBSTATE.A', 'RBSTATE.B', 'RBTXN.A', 'RBTXN.B')


def file_values(image):
    """Decode display values from the eight fixed fixture entries, not a validator."""
    with image.open('rb') as stream:
        stream.seek(379 * 512); root = stream.read(1024)
    values = []
    for index in (0, 20, 21, 22, 23, 24, 25, 26):
        cluster, size = struct.unpack_from('<HI', root, index * 32 + 26)
        values.append((size, (size + 2047) // 2048, 411 + (cluster - 2) * 4))
    return values


def expected_reads(spec, stage_bytes, attempt):
    """Fixed fixture read oracle; native audit status is never an input."""
    reads = [0, 63, 126, 379, 380]
    status = spec.get('status', 0)
    if status in (4, 11): return reads
    if status == 8: return reads + [127, 253]
    stage_count = (stage_bytes + 2047) // 2048
    stage = [20 + i * 10 if i % 2 == 0 else 200 + i * 100 for i in range(stage_count)]
    chains = [[2], stage, [2800], [2900], [3000], [3100], [3200], [3300]]
    if status == 6: chains = chains[:spec['file'] - 1]
    elif status == 5: chains = chains[:spec['file']]
    cached = None
    for chain in chains:
        for cluster in chain:
            index = cluster // 256
            if index != cached: reads += [127 + index, 253 + index]
            cached = index
    if status in (5, 6): return reads
    limit = 16 if status == 9 or spec.get('lba') == 268 else 126
    reads += [lba for i in range(limit) for lba in (127 + i, 253 + i)]
    if 'fault_lba' in spec:
        # The final second-copy sector is unused by the boot path and chains.
        retries = 1 if spec['fault_once'] and attempt == 0 else 0 if spec['fault_once'] else 2
        reads += [378] * retries
    return reads


def check_reads(actual, expected):
    allowed = {0, 63, 126, *range(127, 411)}
    if any(lba not in allowed for lba in actual): raise ValueError('Audit read outside bounded metadata')
    if actual != expected: raise ValueError(f'Wrong audit metadata reads: {actual} != {expected}')


def check_audit_screen(data, strings, spec, values):
    rows = screen_rows(data); status = spec.get('status', 0)
    cells = [(2,65,strings['READ_ONLY']), (5,4,strings['AUDIT_TITLE']),
             (6,4,strings['AUDIT_SCOPE']), (8,4,strings['AUDIT_' + REASONS[status]]),
             (9,4,strings['AUDIT_CODES']), (9,32,f'{status:04X} / {spec.get("detail", 0):04X}'),
             (20,4,strings['AUDIT_REVIEW']), (7,4,strings['AUDIT_LIMIT']),
             (21,4,strings['KEY_HELP']), (22,4,strings['FUNCTION_HELP'])]
    blank = ()
    if status:
        cells += [(11,4,strings['LBA_HEX']), (11,32,f'{spec.get("lba", 0):08X}'),
                  (13,4,strings['AUDIT_ERROR_FILE']), (13,32,f'{spec.get("file", 0):04X} / {spec.get("cluster", 0):04X}')]
        blank += (10, 12, 14, 15, 16, 17, 18, 19)
    else:
        used = sum(item[1] for item in values)
        cells += [(10,4,strings['AUDIT_COLUMNS']), (19,4,strings['AUDIT_CLUSTERS']),
                  (19,38,f'{32043:04X} / {used:04X} / {32043-used:04X}')]
        for i, (size, clusters, lba) in enumerate(values):
            cells += [(11+i,4,NAMES[i]), (11+i,17,f'{size:08X}'),
                      (11+i,30,f'{clusters:04X}'), (11+i,41,f'{lba:08X}')]
    for row, col, value in cells:
        if rows[row][col:col+len(value)] != value:
            raise ValueError(f'Wrong audit text at {row},{col}: {value!r}; {rows[row]!r}')
    if data[(8*80+4)*2+1] != (0x1E if status else 0x1A): raise ValueError('Wrong audit result color')
    if any(rows[row][4:78].strip() for row in blank): raise ValueError('Stale audit rows')
    for row in range(2,23):
        if data[(row*80+1)*2] != 0xB3 or data[(row*80+78)*2] != 0xB3: raise ValueError('Overwritten audit frame')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    args = parser.parse_args()
    executable = shutil.which(args.qemu)
    if not executable: raise ValueError('qemu-system-i386 not found')
    qemu = Path(executable).resolve()
    bios = (args.bios or qemu.parent.parent/'share/seabios/bios-256k.bin').resolve()
    if not bios.is_file() or not bios.with_name('vgabios-stdvga.bin').is_file(): raise ValueError('Missing BIOS ROMs')
    source = ROOT/'build'/output_name('hdd', args.language)
    output = ROOT/'build'/output_name('audit', args.language); prepare_output(output)
    result_file = output/'audit-results.json'; result_file.unlink(missing_ok=True)
    manifest = json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    strings = checked_catalog(manifest, args.language)
    for name, info in manifest['artifacts'].items():
        if name.startswith(('stage2', 'int13-')) and sha256(source/name) != info['sha256']:
            raise ValueError('Changed audit-test component: ' + name)
    events = output/'ide-events.txt'; events.write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n', encoding='ascii')
    command = [str(qemu),'-L',str(bios.parent),'-bios',str(bios),'-machine','pc-i440fx-8.2,accel=tcg',
               '-cpu','486','-m','16','-nodefaults','-vga','std','-boot','c','-display','none',
               '-monitor','none','-serial','none','-nic','none','-no-reboot',
               '-global','isa-debugcon.iobase=0xe9','-qmp','stdio']
    fixtures = {**manifest['audit_cases'], 'retroboot-hdd': {}, 'retroboot-handoff': {'handoff': True}}
    scenarios = [(name,spec,mode,rom) for name,spec in fixtures.items() for mode,rom in (('EDD',0),('CHS',1))]
    scenarios.append(('retroboot-handoff', fixtures['retroboot-handoff'], 'EDD', None))
    results, pairs = [], {}
    for fixture, spec, mode, rom in scenarios:
        name = fixture + '-' + (mode.lower() if rom is not None else 'bare')
        variant = 'handoff' if spec.get('handoff') else 'normal'
        payload = (source/('stage2-handoff.bin' if spec.get('handoff') else 'stage2.bin')).read_bytes()
        memory = manifest['memory'][variant]
        image = source/(fixture+'.img'); image_hash = sha256(image)
        if image_hash != manifest['artifacts'][image.name]['sha256']: raise ValueError('Changed audit fixture')
        values = file_values(image)
        with image.open('rb') as stream: mbr = stream.read(512)
        log, trace, error = (output/(name+suffix) for suffix in ('.log','.trace','-stderr.log'))
        log.unlink(missing_ok=True); trace.unlink(missing_ok=True)
        drive = str(image)
        if 'fault_lba' in spec:
            conf = output/(name+'.conf')
            conf.write_text('[inject-error]\nevent = "read_aio"\nerrno = "5"\n'
                f'sector = "{spec["fault_lba"]}"\nonce = "'+('on' if spec['fault_once'] else 'off')+'"\n', encoding='ascii')
            drive = f'blkdebug:{conf}:{image}'
        invocation = command + ['-drive',f'file={drive.replace(",",",,")},format=raw,if=ide,snapshot=on,rerror=report',
                     '-debugcon','file:'+str(log),'-trace',f'events={str(events).replace(",",",,")},file={str(trace).replace(",",",,")}']
        if rom is not None: invocation += ['-option-rom',str(source/f'int13-{rom}.rom')]
        actions = [(None,0),('f10',10),('ret',10),('f4',10),('f9',10),('f10',10),('esc',0),('f8',3),('f10',10),('esc',0)]
        screens, expected, before_low, attempts, selected = [], [], None, 0, 0
        with error.open('w', encoding='utf-8') as errors, subprocess.Popen(invocation, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=errors, text=True, bufsize=1) as process:
            try:
                qmp = Qmp(process); wait_marker(process, log, 'RB MENU READY')
                for serial, (key, view) in enumerate(actions):
                    if key == 'f8': selected = 2
                    if key == 'f10':
                        expected += expected_reads(spec, len(payload), attempts); attempts += 1
                    if key:
                        qmp.call('send-key', {'keys':[{'type':'qcode','data':key}],'hold-time':30}); time.sleep(0.05)
                        wait_marker(process, log, f'RB MENU {serial:04X} view={view:04X} selected={selected:04X} page=0000')
                    qmp.call('stop')
                    paths = {kind:output/f'{name}-{serial:02d}-{kind}.bin' for kind in ('vga','ram','low')}
                    for kind, address, length in (('vga',0xB8000,4000),('ram',0x10000,0x10000),('low',0,0x8000)):
                        qmp.call('pmemsave', {'val':address,'size':length,'filename':str(paths[kind])})
                    ram, low, vga = (paths[k].read_bytes() for k in ('ram','low','vga'))
                    check_runtime_memory(ram, payload, memory, mode)
                    if before_low is None: before_low = low
                    if low[0x7C00:0x7E00] != before_low[0x7C00:0x7E00] or low[0x800:0x840] != before_low[0x800:0x840]:
                        raise ValueError('Audit staged or executed a handoff target')
                    if view == 10: rows = check_audit_screen(vga, strings, spec, values)
                    else:
                        boot = ram[memory['symbols']['_rb_boot']:memory['symbols']['_rb_boot']+12]
                        rows = check_screen(vga, view, selected, mode, mbr, boot, strings)
                        row = 18 if view == 3 else 20
                        if rows[row][4:78].rstrip() != strings['AUDIT_HELP']: raise ValueError('Missing F10 hint')
                    (output/f'{name}-{serial:02d}.txt').write_text('\n'.join(rows)+'\n', encoding='utf-8')
                    if serial in (1, 8): qmp.call('screendump', {'filename':str(output/f'{name}-{serial:02d}.png'),'format':'png'})
                    screens.append({'key':key,'view':view,'vga_sha256':sha256(paths['vga'])})
                    qmp.call('cont')
                qmp.call('quit')
                if process.wait(timeout=5) != 0: raise ValueError('QEMU did not exit cleanly')
            finally:
                if process.poll() is None: process.kill(); process.wait(timeout=5)
        text = log.read_text(encoding='utf-8'); check_c_status(text, mode)
        marker = f'RB AUDIT status={spec.get("status",0):04X} detail={spec.get("detail",0):04X} file={spec.get("file",0):04X} cluster={spec.get("cluster",0):04X}'
        if text.count('RB AUDIT BEGIN') != attempts or re.findall(r'RB AUDIT status=[^\r\n]+', text) != [marker]*attempts:
            raise ValueError('Wrong audit diagnostics: '+name)
        if 'RB HANDOFF' in text or 'RB PROFILE BEGIN' in text: raise ValueError('Audit invoked a handoff path')
        if text.count(f'RB UI {args.language} CP437') != 1: raise ValueError('Wrong audit language')
        trace_text = trace.read_text(encoding='utf-8'); check_trace(trace_text); lbas = read_lbas(trace_text)
        if rom is not None:
            check_bios_route(text, mode)
            boot_calls = check_bios_route(text.split('RB MENU READY',1)[0], mode)
            boot_reads = 1 + boot_calls.count('42' if mode == 'EDD' else '02')
            check_reads(lbas[boot_reads:], expected)
            pairs.setdefault(fixture,{})[mode] = lbas
        elif lbas != pairs[fixture]['EDD']: raise ValueError('Uninstrumented audit reads differ')
        if sha256(image) != image_hash: raise ValueError('Audit changed its image')
        results.append({'name':name,'mode':mode,'status':spec.get('status',0),'screens':screens,
                        'post_menu_reads':expected,'read_lbas':lbas,'image_unchanged':True,'block_writes':0})
        print(f'{name}: {len(screens)} states, bounded metadata reads and allocation checked; no writes', flush=True)
    if any(p['EDD'] != p['CHS'] for p in pairs.values()): raise ValueError('Audit EDD/CHS reads differ')
    result_file.write_text(json.dumps({'ui':manifest['ui'],'qemu_version':subprocess.check_output([str(qemu),'--version'], text=True).splitlines()[0],
        'qemu_sha256':sha256(qemu),'bios_sha256':sha256(bios),'vga_bios_sha256':sha256(bios.with_name('vgabios-stdvga.bin')),
        'machine':'pc-i440fx-8.2','cpu':'486','ram_mib':16,'cases':results}, indent=2, sort_keys=True)+'\n', encoding='utf-8')


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as error:
        print(f'Audit test: {error}', file=sys.stderr); sys.exit(1)
