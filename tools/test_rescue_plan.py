"""Exercise rescue F6 through real BIOS reads, paging and fresh failure paths."""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    from .build_rescue import ROOT, prepare_output, sha256
    from .rescue_text import LANGUAGES, load_catalog, metadata, output_name
    from .rescue_plan_fixtures import specs, hdd_reads, ranges, SYSTEM
    from .rescue_match_fixtures import specs as match_specs, hdd_reads as match_reads, floppy_reads as match_floppy
    from .rescue_file_fixtures import specifications as file_specs, expected_file_reads
    from .test_rescue import check_memory, check_screen, check_file_screen, trace_reads, floppy_reads
    from .test_rescue_match import check_match_screen
    from .test_menu import Qmp, screen_rows, wait_marker
except ImportError:
    from build_rescue import ROOT, prepare_output, sha256
    from rescue_text import LANGUAGES, load_catalog, metadata, output_name
    from rescue_plan_fixtures import specs, hdd_reads, ranges, SYSTEM
    from rescue_match_fixtures import specs as match_specs, hdd_reads as match_reads, floppy_reads as match_floppy
    from rescue_file_fixtures import specifications as file_specs, expected_file_reads
    from test_rescue import check_memory, check_screen, check_file_screen, trace_reads, floppy_reads
    from test_rescue_match import check_match_screen
    from test_menu import Qmp, screen_rows, wait_marker

ACTIONS=((None,0),('f6',4),('right',4),('right',4),('left',4),('left',4),('ret',4),('esc',0),('f6',4),('esc',0))
CD_CASES=('plan','demo','chs','no-hdd','bad-fsinfo')


def check_discovery(text,spec):
    calls=re.findall(r'^@([0-9A-F]{2})$',text,re.M);expected=[]
    if not spec.get('absent'):
        init=['41','08' if spec.get('chs') or spec['rom']==4 else '48'];expected+=init
        for lba in hdd_reads(spec):
            expected.append('02' if spec.get('chs') else '42')
            if lba==spec.get('fault_lba'):expected.append('00')
        if not (spec['probe'] or spec['status']) or spec['rom'] in (14,15):expected+=init
    if calls!=expected:raise ValueError('Plan BIOS discovery/read/reset sequence differs')


def check_plan_screen(data,s,spec,page):
    rows=screen_rows(data);probe,status,detail,nested=(spec[k] for k in ('probe','status','detail','nested'))
    reason=('OK','NO_DISK','PARAMS','GEOMETRY')[probe] if probe else 'T_CHANGED' if status==6 else 'P_BAD' if status else 'P_OK'
    cells=[(2,4,s['TITLE']),(2,65,s['READ_ONLY']),(5,4,s['P_SCOPE']),(6,4,s['P_LIMIT']),
        (8,4,s[reason]),(9,4,s['P_CODES']),
        (9,32,f'0x{probe:04X} / 0x{status:04X} / 0x{detail:04X} / 0x{nested:04X}'),
        (10,4,s['P_ERROR']),(10,32,f'0x{spec["lba"]:08X} / 0x{spec["index"]:04X}'),
        (21,4,s['P_HELP']),(22,4,s['P_BOUNDARY'])]
    blank=[7,20]
    if probe or status:blank+=list(range(11,20))
    else:
        cells += [(11,4,s['P_COUNTS']),(11,32,'0x0008 / 0x0002 / 0x00005A00'),
            (12,4,s['P_SECTORS']),(12,32,'0x00000027 / 0x0000002D'),(13,4,s['P_TABLE']),
            (19,4,s['P_PAGE']),(19,32,f'0x{page+1:04X} / 0x0002')]
        shown=ranges()[page*5:page*5+5]
        for i,(kind,lba,count) in enumerate(shown):
            cells += [(14+i,4,f'0x{page*5+i+1:04X}'),(14+i,13,s.get(kind,kind)),
                      (14+i,32,f'0x{lba:08X}'),(14+i,49,f'0x{count:08X}')]
        blank+=list(range(14+len(shown),19))
    for row,col,value in cells:
        if rows[row][col:col+len(value)]!=value:raise ValueError(f'Plan VGA {row},{col}: expected {value!r}, got {rows[row]!r}')
    if any(rows[r][4:78].strip() for r in blank):raise ValueError('Plan page retained stale ranges or size')
    if data[(8*80+4)*2+1]!=(0x1E if probe or status else 0x1A):raise ValueError('Wrong plan status color')
    for row in range(2,23):
        if row!=4 and (data[(row*80+1)*2]!=0xB3 or data[(row*80+78)*2]!=0xB3):raise ValueError('Plan page overwrote frame')
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--language',choices=LANGUAGES,default='en')
    p.add_argument('--qemu',default='qemu-system-i386');p.add_argument('--bios',type=Path);p.add_argument('--case',action='append')
    p.add_argument('--cdrom',action='store_true');p.add_argument('--bare',action='store_true')
    args=p.parse_args()
    if args.bare and not args.cdrom:raise ValueError('--bare requires --cdrom')
    found=shutil.which(args.qemu)
    if not found:raise ValueError('QEMU not found')
    qemu=Path(found).resolve();bios=(args.bios or qemu.parent.parent/'share/seabios/bios-256k.bin').resolve()
    source=ROOT/'build'/output_name('rescue',args.language)
    kind='rescue-plan-iso-test'+('-bare' if args.bare else '') if args.cdrom else 'rescue-plan-test'
    out=ROOT/'build'/(kind+('-de' if args.language=='de' else ''));prepare_output(out)
    report=out/'plan-results.json';report.unlink(missing_ok=True)
    manifest=json.loads((source/'manifest.json').read_text());s=load_catalog(args.language)
    if manifest['ui']!=metadata(args.language) or manifest['rescue_plan_cases']!=specs():raise ValueError('Stale rescue plan build')
    cases=specs()
    if args.cdrom:cases={k:v for k,v in cases.items() if k in CD_CASES and (not args.bare or k!='chs')}
    if args.case:
        if set(args.case)-cases.keys():raise ValueError('Unknown plan case')
        cases={k:v for k,v in cases.items() if k in args.case}
    events=out/'events.txt';events.write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
    command=[str(qemu),'-L',str(bios.parent),'-bios',str(bios),'-machine','pc-i440fx-8.2,accel=tcg','-cpu','486','-m','16',
        '-nodefaults','-vga','std','-boot','d' if args.cdrom else 'a','-display','none','-monitor','none','-serial','none','-nic','none','-no-reboot',
        '-global','isa-debugcon.iobase=0xe9','-qmp','stdio']
    results=[]
    for name,original in cases.items():
        spec=dict(original);stem='retroboot-rescue'+('-demo' if spec.get('demo') else '')
        image=source/(stem+'.img');medium=image
        if args.cdrom:medium=ROOT/'build'/('rescue-iso'+('-de' if args.language=='de' else ''))/(stem+'.iso')
        images=[image,medium];before={str(path):sha256(path) for path in images}
        if before[str(image)]!=manifest['artifacts'][image.name]['sha256']:raise ValueError('Changed plan source floppy')
        if args.cdrom:
            try:from .build_rescue_iso import inspect_iso
            except ImportError:from build_rescue_iso import inspect_iso
            inspect_iso(medium.read_bytes(),image.read_bytes())
        log,trace,err=(out/(name+suffix) for suffix in ('.log','.trace','-stderr.log'))
        log.unlink(missing_ok=True);trace.unlink(missing_ok=True)
        media_args=['-drive',f'file={medium},format=raw,if=none,id=rbcd,media=cdrom,readonly=on','-device','ide-cd,drive=rbcd,bus=ide.1,unit=0'] if args.cdrom else ['-drive',f'file={medium},format=raw,if=floppy,readonly=on']
        invocation=command+media_args+['-debugcon','file:'+str(log),'-trace',f'events={events},file={trace}']
        work=None;expected_work=None
        if not spec.get('absent'):
            disk=source/('retroboot-rescue-target-hdd.img' if spec['kind']=='match' else
                'retroboot-rescue-bad-fsinfo-hdd.img' if spec['kind']=='bad-fsinfo' else 'disk-plan-'+spec['kind']+'.img')
            before[str(disk)]=sha256(disk)
            if before[str(disk)]!=manifest['artifacts'][disk.name]['sha256']:raise ValueError('Changed plan source HDD')
            work=out/(name+'-hdd.img');shutil.copyfile(disk,work);expected_work=sha256(work);drive=str(work)
            if 'fault_lba' in spec:
                conf=out/(name+'.conf');conf.write_text('[inject-error]\nevent = "read_aio"\nerrno = "5"\nsector = "'+str(spec['fault_lba'])+'"\nonce = "off"\n')
                drive=f'blkdebug:{conf}:{work}'
            invocation+=['-drive',f'file={drive},format=raw,if=none,id=rb,rerror=report',
                '-device','ide-hd,drive=rb,bus=ide.0,unit=0,cyls=260,heads=16,secs=63,lcyls=260,lheads=16,lsecs=63']
        rom=1 if spec.get('chs') else spec['rom']
        if not args.bare:invocation+=['-option-rom',str(source/f'int13-{rom}.rom')]
        actions=list(ACTIONS)
        if spec.get('cross_view'):actions[-1:]=[('f5',3),('f6',4),('f4',2),('f6',4),('esc',0)]
        screens=[];expected=[];expected_floppy=[];markers=[];first_low=None;page=0
        with err.open('w') as errors,subprocess.Popen(invocation,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,bufsize=1) as process:
            try:
                qmp=Qmp(process);wait_marker(process,log,'RB RESCUE READY')
                for serial,(key,view) in enumerate(actions):
                    planning=view==4 and key in ('f6','ret')
                    if planning:
                        if spec.get('mutation') and serial>1:spec.update(kind='bad-fsinfo',status=9,detail=7,nested=1,lba=SYSTEM+1)
                        expected+=hdd_reads(spec);page=0
                        markers.append(f'RB PLAN probe={spec["probe"]:04X} status={spec["status"]:04X} detail={spec["detail"]:04X} nested={spec["nested"]:04X}')
                    elif key in ('left','right') and not(spec['probe'] or spec['status']):page=max(0,min(1,page+(1 if key=='right' else -1)))
                    if view==2:expected_floppy+=expected_file_reads(image.read_bytes(),'file-demo')
                    if view==3:
                        expected+=match_reads(match_specs()['match']);expected_floppy+=match_floppy(image.read_bytes(),match_specs()['match'])
                    if key:
                        qmp.call('send-key',{'keys':[{'type':'qcode','data':key}],'hold-time':30});time.sleep(0.05)
                        wait_marker(process,log,f'RB RESCUE KEY {serial:04X} view={view:04X}')
                    time.sleep(0.08);qmp.call('stop')
                    paths={k:out/f'{name}-{serial:02d}-{k}.bin' for k in ('ram','low','vga')}
                    for k,address,length in (('ram',0x10000,65536),('low',0,0x8000),('vga',0xB8000,4000)):
                        qmp.call('pmemsave',{'val':address,'size':length,'filename':str(paths[k])})
                    ram,low,vga=(paths[k].read_bytes() for k in ('ram','low','vga'))
                    check_memory(ram,(source/'retroboot-rescue.bin').read_bytes(),manifest['memory']['retroboot-rescue'],zero_bss=serial==0)
                    if first_low is None:first_low=low
                    if low[0x7C00:0x7E00]!=first_low[0x7C00:0x7E00] or low[0x800:0x840]!=first_low[0x800:0x840]:raise ValueError('Plan staged a boot')
                    if view==4:rows=check_plan_screen(vga,s,spec,page)
                    elif view==2:rows=check_file_screen(vga,s,file_specs()['file-demo'])
                    elif view==3:rows=check_match_screen(vga,s,match_specs()['match'])
                    else:rows=check_screen(vga,s,0,{},'EDD',0,(0,0),bytes(512))
                    if planning and not args.bare:check_discovery(log.read_text().rsplit('RB PLAN BEGIN',1)[1],spec)
                    (out/f'{name}-{serial:02d}.txt').write_text('\n'.join(rows)+'\n',encoding='utf-8')
                    if serial in (1,2,6):qmp.call('screendump',{'filename':str(out/f'{name}-{serial:02d}.png'),'format':'png'})
                    actual=trace_reads(trace.read_text())
                    if actual!=expected:raise ValueError(f'Plan HDD reads differ: {name}, state {serial}, {len(actual)} / {len(expected)}')
                    if not args.bare and floppy_reads(log.read_text())!=expected_floppy:raise ValueError('Plan unexpectedly read a saved file')
                    screens.append(dict(key=key,view=view,page=page,vga_sha256=sha256(paths['vga']),probe=spec['probe'],status=spec['status']))
                    if serial==1 and spec.get('mutation'):
                        with work.open('r+b') as f:f.seek((SYSTEM+1)*512);f.write(bytes(4))
                        expected_work=sha256(work)
                    qmp.call('cont')
                qmp.call('quit')
                if process.wait(timeout=5):raise ValueError('QEMU exit failed')
            finally:
                if process.poll() is None:process.kill();process.wait(timeout=5)
        text=log.read_text();trace_text=trace.read_text()
        if re.findall(r'RB PLAN probe=[^\r\n]+',text)!=markers:raise ValueError('Wrong plan result markers')
        if '!W' in text or 'ide_sector_write' in trace_text or 'blk_co_pwritev' in trace_text:raise ValueError('Guest attempted a disk write')
        if any(sha256(Path(path))!=h for path,h in before.items()):raise ValueError('Source medium changed')
        if work and sha256(work)!=expected_work:raise ValueError('Guest changed the test HDD')
        results.append(dict(name=name,spec=original,screens=screens,read_lbas=expected,log=text,
            source_unchanged=True,block_writes=0,host_mutation=bool(original.get('mutation')),
            boot_medium='cdrom' if args.cdrom else 'floppy',instrumented_bios=not args.bare))
        results[-1]['expected_floppy_lbas' if args.bare else 'floppy_lbas']=expected_floppy
        if work:work.unlink()
        print(f'{name}: {len(screens)} states; fresh plan; exact reads; no guest writes',flush=True)
    report.write_text(json.dumps(dict(ui=manifest['ui'],qemu_version=subprocess.check_output([str(qemu),'--version'],text=True).splitlines()[0],
        qemu_sha256=sha256(qemu),bios_sha256=sha256(bios),vga_bios_sha256=sha256(bios.with_name('vgabios-stdvga.bin')),
        machine='pc-i440fx-8.2',cpu='486',ram_mib=16,cases=results),indent=2,sort_keys=True)+'\n')


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,IndexError,subprocess.SubprocessError) as error:print('Rescue plan test: '+str(error),file=sys.stderr);sys.exit(1)
