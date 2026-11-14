"""Exercise the read-only F5 composition through real floppy/HDD BIOS reads."""
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
    from .build_rescue import ROOT, prepare_output, sha256
    from .rescue_text import LANGUAGES, load_catalog, metadata, output_name
    from .rescue_match_fixtures import specs, hdd_reads, floppy_reads as expected_floppy, observed, CAPACITY, CHS_CAPACITY
    from .rescue_file_fixtures import specifications as file_specs, expected_file_reads
    from .test_rescue import check_memory, check_screen, check_file_screen, trace_reads, floppy_reads
    from .test_menu import Qmp, screen_rows, wait_marker
except ImportError:
    from build_rescue import ROOT, prepare_output, sha256
    from rescue_text import LANGUAGES, load_catalog, metadata, output_name
    from rescue_match_fixtures import specs, hdd_reads, floppy_reads as expected_floppy, observed, CAPACITY, CHS_CAPACITY
    from rescue_file_fixtures import specifications as file_specs, expected_file_reads
    from test_rescue import check_memory, check_screen, check_file_screen, trace_reads, floppy_reads
    from test_menu import Qmp, screen_rows, wait_marker

ACTIONS = ((None,0),('f5',3),('ret',3),('f4',2),('f5',3),('esc',0),('ret',1),('f5',3),('esc',0))
CD_CASES = ('match','chs','no-hdd','missing-backup','bad-backup','bad-saved-boot',
            'capacity','identity','mbr-io','record-io')


def check_discovery_calls(text,spec):
    calls=re.findall(r'^@([0-9A-F]{2})$',text,re.M)
    expected=[]
    if not spec.get('absent') and not (spec['status'] in (1,2) and spec['rom']<14):
        init=['41','08' if spec.get('chs') else '48'];expected+=init
        for lba in hdd_reads(spec):
            expected.append('02' if spec.get('chs') else '42')
            if lba==spec.get('fault_lba'):expected.append('00')
        if not spec['status'] or spec['rom']>=14:expected+=init
    if calls!=expected:raise ValueError('Match BIOS discovery/read/reset sequence differs')


def check_match_screen(data,s,spec):
    rows=screen_rows(data);status,detail,nested=(spec[k] for k in ('status','detail','nested'))
    reason='T_OK'
    if status==1:reason='B_MISSING' if detail==5 else 'B_IO' if detail==1 else 'B_FILE_BAD'
    elif status==2:reason='B_BAD'
    elif status==3:reason=('OK','NO_DISK','PARAMS','GEOMETRY')[detail]
    elif status==4:reason={7:'T_CAPACITY',8:'T_GEOMETRY',6:'T_IDENTITY',9:'T_LAYOUT',10:'T_CHANGED'}.get(detail,'T_BAD')
    elif status==5:reason='T_CHANGED'
    cells=[(2,4,s['TITLE']),(2,65,s['READ_ONLY']),(5,4,s['T_SCOPE']),(6,4,s['T_LIMIT']),
           (8,4,s[reason]),(9,4,s['T_CODES']),(9,32,f'0x{status:04X} / 0x{detail:04X} / 0x{nested:04X}'),
           (10,4,s['B_NESTED']),(10,32,f'0x{spec["record"]:04X}'),
           (18,4,s['B_FILE_LBA']),(18,32,f'0x{spec["file_lba"]:08X}'),
           (19,4,s['T_LBA']),(19,32,f'0x{spec["disk_lba"]:08X}'),
           (21,4,s['T_HELP']),(22,4,s['T_BOUNDARY'])]
    blank=[7,20]
    if status:blank+=list(range(11,18))
    else:
        o=observed(spec)
        for row,key,value in (
            (11,'DISK_ID',f'0x{o["disk_id"]:08X}'),(12,'T_MEDIA',bytes.fromhex(o['media_id']).hex(' ').upper()),
            (13,'T_CRC',f'0x{o["layout_crc"]:08X}'),
            (14,'T_ADMIN',f'0x{o["admin_start"]:08X} / 0x{o["admin_sectors"]:08X}'),
            (15,'CAPACITY',f'0x{o["capacity"]:016X}'),
            (16,'T_ROUTE',f'{o["route"]} / 0x{o["heads"]:04X} / 0x{o["spt"]:04X}'),
            (17,'T_GENERATIONS',f'0x{o["config_generation"]:08X} / 0x{o["state_generation"]:08X}')):
            cells += [(row,4,s[key]),(row,29 if key=='T_MEDIA' else 32,value)]
    for row,col,value in cells:
        if rows[row][col:col+len(value)]!=value:raise ValueError(f'Match VGA {row},{col}: expected {value!r}, got {rows[row]!r}')
    if any(rows[r][4:78].strip() for r in blank):raise ValueError('Match page retained stale fields')
    if data[(8*80+4)*2+1]!=(0x1E if status else 0x1A):raise ValueError('Wrong match color')
    for row in range(2,23):
        if row!=4 and (data[(row*80+1)*2]!=0xB3 or data[(row*80+78)*2]!=0xB3):raise ValueError('Match page overwrote frame')
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--language',choices=LANGUAGES,default='en')
    p.add_argument('--qemu',default='qemu-system-i386');p.add_argument('--bios',type=Path);p.add_argument('--case',action='append')
    p.add_argument('--cdrom',action='store_true',help='Boot an El Torito CD with no attached floppy drive')
    p.add_argument('--bare',action='store_true',help='Use the unmodified BIOS for supported CD cases')
    args=p.parse_args()
    if args.bare and not args.cdrom:raise ValueError('--bare requires --cdrom')
    found=shutil.which(args.qemu)
    if not found:raise ValueError('QEMU not found')
    qemu=Path(found).resolve();bios=(args.bios or qemu.parent.parent/'share/seabios/bios-256k.bin').resolve()
    source=ROOT/'build'/output_name('rescue',args.language)
    kind='rescue-iso-test'+('-bare' if args.bare else '') if args.cdrom else 'rescue-match-test'
    out=ROOT/'build'/(kind+('-de' if args.language=='de' else ''));prepare_output(out)
    report=out/'match-results.json';report.unlink(missing_ok=True)
    manifest=json.loads((source/'manifest.json').read_text());s=load_catalog(args.language)
    if manifest['ui']!=metadata(args.language) or manifest['rescue_match_cases']!=specs():raise ValueError('Stale rescue match build')
    cases=specs()
    if args.cdrom:
        cases={k:v for k,v in cases.items() if k in CD_CASES and (not args.bare or k!='chs')}
    if args.case:
        if set(args.case)-cases.keys():raise ValueError('Unknown match case')
        cases={k:v for k,v in cases.items() if k in args.case}
    events=out/'events.txt';events.write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
    command=[str(qemu),'-L',str(bios.parent),'-bios',str(bios),'-machine','pc-i440fx-8.2,accel=tcg','-cpu','486','-m','16',
        '-nodefaults','-vga','std','-boot','d' if args.cdrom else 'a','-display','none','-monitor','none','-serial','none','-nic','none','-no-reboot',
        '-global','isa-debugcon.iobase=0xe9','-qmp','stdio']
    results=[]
    for name,original in cases.items():
        spec=dict(original);image=source/('match-'+name+'.img')
        if args.cdrom and name in ('match','missing-backup'):
            image=source/('retroboot-rescue-demo.img' if name=='match' else 'retroboot-rescue.img')
        images=[image]
        log,trace,err=(out/(name+suffix) for suffix in ('.log','.trace','-stderr.log'))
        log.unlink(missing_ok=True);trace.unlink(missing_ok=True)
        floppy=out/(name+'-floppy.img');shutil.copyfile(image,floppy)
        work=None;expected_work=None;expected_image=sha256(floppy)
        medium=floppy
        if args.cdrom:
            try:
                from .build_rescue_iso import package, inspect_iso
            except ImportError:
                from build_rescue_iso import package, inspect_iso
            medium=out/(name+'.iso');medium.write_bytes(package(floppy.read_bytes()))
            inspect_iso(medium.read_bytes(),floppy.read_bytes())
            # Both successful and missing-file cases boot the exact published ISO.
            if name in ('match','missing-backup'):
                cd_source=ROOT/'build'/('rescue-iso'+('-de' if args.language=='de' else ''))
                published=cd_source/('retroboot-rescue-demo.iso' if name=='match' else 'retroboot-rescue.iso')
                if medium.read_bytes()!=published.read_bytes():raise ValueError('CD test differs from published ISO')
            medium_hash=sha256(medium)
            media_args=['-drive',f'file={medium},format=raw,if=none,id=rbcd,media=cdrom,readonly=on',
                        '-device','ide-cd,drive=rbcd,bus=ide.1,unit=0']
        else:media_args=['-drive',f'file={floppy},format=raw,if=floppy,readonly=on']
        invocation=command+media_args+['-debugcon','file:'+str(log),
                            '-trace',f'events={events},file={trace}']
        if not spec.get('absent'):
            disk=source/('disk-match-'+spec['kind']+'.img');images.append(disk)
            work=out/(name+'-hdd.img');shutil.copyfile(disk,work);expected_work=sha256(work);drive=str(work)
            if 'fault_lba' in spec:
                conf=out/(name+'.conf');conf.write_text('[inject-error]\nevent = "read_aio"\nerrno = "5"\nsector = "'+str(spec['fault_lba'])+'"\nonce = "off"\n')
                drive=f'blkdebug:{conf}:{work}'
            invocation+=['-drive',f'file={drive},format=raw,if=none,id=rb,rerror=report',
                '-device','ide-hd,drive=rb,bus=ide.0,unit=0,cyls=260,heads=16,secs=63,lcyls=260,lheads=16,lsecs=63']
        rom=1 if spec.get('chs') else spec['rom']
        if not args.bare:invocation+=['-option-rom',str(source/f'int13-{rom}.rom')]
        before={str(path):sha256(path) for path in images}
        if any(h!=manifest['artifacts'][Path(path).name]['sha256'] for path,h in before.items()):raise ValueError('Changed match source fixture')
        screens=[];expected=[];floppy_expected=[];markers=[];first_low=None;previous_low=None
        actions=list(ACTIONS)
        if rom>=14:actions[6]=('f4',2) # keep each injected two-probe operation isolated
        with err.open('w') as errors,subprocess.Popen(invocation,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,bufsize=1) as process:
            try:
                qmp=Qmp(process);wait_marker(process,log,'RB RESCUE READY')
                for serial,(key,view) in enumerate(actions):
                    data=floppy.read_bytes()
                    if view==3:
                        expected+=hdd_reads(spec);floppy_expected+=expected_floppy(data,spec)
                        markers.append(f'RB MATCH status={spec["status"]:04X} detail={spec["detail"]:04X} nested={spec["nested"]:04X} record={spec["record"]:04X}')
                    file_case=spec.get('file_case','file-demo')
                    if view==2:floppy_expected+=expected_file_reads(data,file_case)
                    diagnosis=dict(layout=0,entries=5,ebrs=1,marker=1)
                    if spec.get('absent'):diagnosis=dict(status=1)
                    elif spec['kind']=='bad-mbr':diagnosis=dict(layout=2,entries=0,ebrs=0,marker=1,signature=0xAA00)
                    elif spec.get('fault_lba')==0:diagnosis=dict(status=4)
                    if view==1:expected+=[] if spec.get('absent') else [0,0,0] if spec.get('fault_lba')==0 else [0,0] if spec['kind']=='bad-mbr' else [0,63,0]
                    if key:
                        qmp.call('send-key',{'keys':[{'type':'qcode','data':key}],'hold-time':30});time.sleep(0.05)
                        wait_marker(process,log,f'RB RESCUE KEY {serial:04X} view={view:04X}')
                    time.sleep(0.08)
                    if serial in (1,2):
                        qmp.call('screendump',{'filename':str(out/f'{name}-{serial:02d}.png'),'format':'png'})
                    qmp.call('stop')
                    paths={k:out/f'{name}-{serial:02d}-{k}.bin' for k in ('ram','low','vga')}
                    for k,address,length in (('ram',0x10000,65536),('low',0,0x8000),('vga',0xB8000,4000)):
                        qmp.call('pmemsave',{'val':address,'size':length,'filename':str(paths[k])})
                    ram,low,vga=(paths[k].read_bytes() for k in ('ram','low','vga'))
                    check_memory(ram,(source/'retroboot-rescue.bin').read_bytes(),manifest['memory']['retroboot-rescue'],zero_bss=serial==0)
                    if first_low is None:first_low=low
                    if low[0x7C00:0x7E00]!=first_low[0x7C00:0x7E00] or low[0x800:0x840]!=first_low[0x800:0x840]:raise ValueError('Match staged a boot')
                    if view==2 and previous_low[0x500:0x560]!=low[0x500:0x560]:raise ValueError('File view changed HDD context')
                    previous_low=low
                    if view==3:
                        rows=check_match_screen(vga,s,spec)
                        if not args.bare:check_discovery_calls(log.read_text().rsplit('RB MATCH BEGIN',1)[1],spec)
                    elif view==2:rows=check_file_screen(vga,s,file_specs()[file_case])
                    else:
                        mbr=bytes(512)
                        if work:
                            with work.open('rb') as f:mbr=f.read(512)
                        capacity=CHS_CAPACITY if spec.get('chs') else CAPACITY+(spec['kind']=='capacity')
                        rows=check_screen(vga,s,view,diagnosis,'CHS' if spec.get('chs') else 'EDD',capacity,(16,63) if spec.get('chs') else (0,0),mbr)
                    (out/f'{name}-{serial:02d}.txt').write_text('\n'.join(rows)+'\n',encoding='utf-8')
                    actual=trace_reads(trace.read_text());floppy_actual=floppy_reads(log.read_text())
                    if actual!=expected:raise ValueError(f'HDD read sequence differs: {name}, state {serial}, {len(actual)} / {len(expected)}')
                    if not args.bare and floppy_actual!=floppy_expected:raise ValueError(f'Floppy read sequence differs: {name}, state {serial}, {len(floppy_actual)} / {len(floppy_expected)}')
                    screens.append(dict(key=key,view=view,vga_sha256=sha256(paths['vga']),status=spec['status']))
                    if serial==1 and spec.get('mutation'):
                        if spec['mutation']=='hdd':
                            with work.open('r+b') as f:f.seek(510);f.write(b'\0')
                            expected_work=sha256(work);spec.update(status=4,detail=6,nested=1,kind='bad-mbr')
                        else:
                            with floppy.open('r+b') as f:f.seek(19*512+64);f.write(b'\xe5')
                            expected_image=sha256(floppy);spec.update(status=1,detail=5,nested=0,file_case='file-missing')
                    qmp.call('cont')
                qmp.call('quit')
                if process.wait(timeout=5):raise ValueError('QEMU exit failed')
            finally:
                if process.poll() is None:process.kill();process.wait(timeout=5)
        text=log.read_text();trace_text=trace.read_text()
        if re.findall(r'RB MATCH status=[^\r\n]+',text)!=markers:raise ValueError('Wrong match markers')
        if '!W' in text or 'ide_sector_write' in trace_text or 'blk_co_pwritev' in trace_text:raise ValueError('Guest attempted a disk write')
        if any(sha256(Path(path))!=h for path,h in before.items()):raise ValueError('Source image changed')
        if sha256(floppy)!=expected_image or (work and sha256(work)!=expected_work):raise ValueError('Guest changed test media')
        if args.cdrom and sha256(medium)!=medium_hash:raise ValueError('Guest changed CD image')
        results.append(dict(name=name,spec=original,screens=screens,read_lbas=expected,floppy_lbas=floppy_expected,
            log=text,source_unchanged=True,block_writes=0,host_mutation=original.get('mutation')))
        if args.cdrom:
            results[-1].update(boot_medium='cdrom',iso_sha256=medium_hash,floppy_attached=False,
                              instrumented_bios=not args.bare,floppy_reads_observed=not args.bare)
            if args.bare:
                results[-1]['expected_floppy_lbas']=results[-1].pop('floppy_lbas')
            medium.unlink()
        floppy.unlink()
        if work:work.unlink()
        print(f'{name}: {len(screens)} states; fresh file/device checks; exact reads; no guest writes',flush=True)
    report.write_text(json.dumps(dict(ui=manifest['ui'],qemu_version=subprocess.check_output([str(qemu),'--version'],text=True).splitlines()[0],
        qemu_sha256=sha256(qemu),bios_sha256=sha256(bios),vga_bios_sha256=sha256(bios.with_name('vgabios-stdvga.bin')),
        machine='pc-i440fx-8.2',cpu='486',ram_mib=16,cases=results),indent=2,sort_keys=True)+'\n')


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,IndexError,subprocess.SubprocessError) as error:print('Rescue match test: '+str(error),file=sys.stderr);sys.exit(1)
