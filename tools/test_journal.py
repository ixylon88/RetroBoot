"""Exercise Recovery/Enter through BIOS reads, VGA, RAM and unchanged media."""
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
    from .test_audit import expected_reads as audit_reads
    from .ui_text import LANGUAGES, checked_catalog, output_name
except ImportError:
    from build_hdd import ROOT, prepare_output, sha256
    from test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
    from test_menu import Qmp, check_screen, screen_rows, wait_marker
    from test_audit import expected_reads as audit_reads
    from ui_text import LANGUAGES, checked_catalog, output_name

LOAD_REASONS=('','ALLOCATION','CONFIG','STATE','IDENTITY','IO','CHANGED')
OBSERVATIONS=('INVALID','BASELINE','PREPARED_OLD','PREPARED_NEW','COMMITTED_NEW','DIVERGED')


def expected_reads(spec, stage_bytes, attempt):
    status=spec.get('audit_status',0)
    reads=audit_reads(dict(status=status,file=spec.get('audit_file',0)),stage_bytes,0)
    if status:return reads
    reads += [11603,12003,12403,12803][:spec.get('identity_reads',4)]
    if 'identity_reads' in spec:return reads
    if 'fault_lba' in spec:
        reads += [13203,13204]
        if not spec['fault_once']:return reads+[13204,13204,13603,13604,13605,0]
        if attempt==0:reads += [13204]
        reads += [13205]
    else:reads += [13203,13204,13205]
    return reads+[13603,13604,13605,0]


def check_reads(actual, expected):
    allowed={0,63,126,*range(127,411),11603,12003,12403,12803,13203,13204,13205,13603,13604,13605}
    if any(lba not in allowed for lba in actual) or actual!=expected:
        raise ValueError(f'Journal read boundary/order differs: {actual} != {expected}')


def check_journal_screen(data, strings, spec, crcs):
    rows=screen_rows(data);load=spec.get('load',0);status=spec.get('journal',0);obs=spec.get('observation',0)
    reason='JOURNAL_'+(LOAD_REASONS[load] if load else 'INVALID' if status else OBSERVATIONS[obs])
    copies=spec.get('copies',[0,0])
    cells=[(2,65,strings['READ_ONLY']),(5,4,strings['JOURNAL_TITLE']),(6,4,strings['JOURNAL_SCOPE']),
        (8,4,strings[reason]),(9,4,strings['JOURNAL_LOAD_CODES']),(9,32,f'{load:04X} / {spec.get("detail",0):04X}'),
        (10,4,strings['JOURNAL_COPY_CODES']),(10,32,f'{status:04X} / {copies[0]:04X} / {copies[1]:04X}'),
        (17,4,strings['LBA_HEX']),(17,32,f'{spec.get("lba",0):08X}'),(19,4,strings['JOURNAL_HELP']),
        (20,4,strings['NO_CHANGES']),(21,4,strings['KEY_HELP']),(22,4,strings['FUNCTION_HELP'])]
    blank=[7,11,16,18]
    if load or status:blank += [12,13,14,15]
    else:
        cells += [(12,4,strings['JOURNAL_SEQUENCE']),(12,32,f'{spec["sequence"]:08X}'),
            (13,4,strings['JOURNAL_PHASE']),(13,32,f'{spec["phase"]:04X} / '+('B' if spec['source'] else 'A')),
            (14,4,strings['JOURNAL_CRCS']),(14,32,f'{crcs[0]:08X} / {crcs[1]:08X}'),
            (15,4,strings['VIS_CHANGED']),(15,32,f'{spec["changed"]:02X}')]
    for row,col,value in cells:
        if rows[row][col:col+len(value)]!=value:raise ValueError(f'Journal VGA mismatch at {row},{col}: {value!r}; {rows[row]!r}')
    if any(rows[row][4:78].strip() for row in blank):raise ValueError('Journal failure retains stale selected record')
    color=0x1A if not load and not status and obs in (1,4) else 0x1E
    if data[(8*80+4)*2+1]!=color:raise ValueError('Wrong journal diagnosis color')
    for row in range(2,23):
        if data[(row*80+1)*2]!=0xB3 or data[(row*80+78)*2]!=0xB3:raise ValueError('Journal overwrote frame')
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu',default='qemu-system-i386');parser.add_argument('--bios',type=Path)
    parser.add_argument('--language',choices=LANGUAGES,default='en');parser.add_argument('--case',action='append')
    args=parser.parse_args();exe=shutil.which(args.qemu)
    if not exe:raise ValueError('QEMU not found')
    qemu=Path(exe).resolve();bios=(args.bios or qemu.parent.parent/'share/seabios/bios-256k.bin').resolve()
    source=ROOT/'build'/output_name('hdd',args.language);output=ROOT/'build'/output_name('journal',args.language);prepare_output(output)
    result_file=output/'journal-results.json';result_file.unlink(missing_ok=True)
    manifest=json.loads((source/'manifest.json').read_text());strings=checked_catalog(manifest,args.language)
    for name,info in manifest['artifacts'].items():
        if name.startswith(('stage2','int13-')) and sha256(source/name)!=info['sha256']:raise ValueError('Changed component: '+name)
    scenarios=[(name,spec,spec['mode'],0 if spec['mode']=='EDD' else 1) for name,spec in manifest['journal_cases'].items()]
    for name in ('retroboot-hdd','retroboot-handoff'):
        for mode,rom in (('EDD',0),('CHS',1)):
            spec=dict(observation=1,sequence=1,phase=0,source=0,changed=0) if mode=='EDD' else dict(journal=8,copies=[5,5])
            scenarios.append((name,spec,mode,rom))
    scenarios.append(('retroboot-handoff',dict(observation=1,sequence=1,phase=0,source=0,changed=0),'EDD',None))
    if args.case:
        scenarios=[c for c in scenarios if c[0] in args.case]
        if set(args.case)-{c[0] for c in scenarios}:raise ValueError('Unknown journal case')
    events=output/'ide-events.txt';events.write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
    command=[str(qemu),'-L',str(bios.parent),'-bios',str(bios),'-machine','pc-i440fx-8.2,accel=tcg','-cpu','486','-m','16',
        '-nodefaults','-vga','std','-boot','c','-display','none','-monitor','none','-serial','none','-nic','none','-no-reboot',
        '-global','isa-debugcon.iobase=0xe9','-qmp','stdio']
    actions=[(None,0),('f8',3),('ret',11),('ret',11),('f4',11),('f9',11),('esc',0),('ret',3),('ret',11),('f8',3),('esc',0)]
    results=[];pairs={}
    for fixture,spec,mode,rom in scenarios:
        name=fixture+('-bare' if rom is None else '-'+mode.lower());handoff=fixture=='retroboot-handoff'
        payload=(source/('stage2-handoff.bin' if handoff else 'stage2.bin')).read_bytes();memory=manifest['memory']['handoff' if handoff else 'normal']
        image=source/(fixture+'.img');original=sha256(image)
        if original!=manifest['artifacts'][image.name]['sha256']:raise ValueError('Changed journal fixture')
        with image.open('rb') as stream:
            mbr=stream.read(512);stream.seek((13603 if spec.get('source') else 13203)*512+64);crcs=struct.unpack('<II',stream.read(8))
        log,trace,error=(output/(name+s) for s in ('.log','.trace','-stderr.log'))
        log.unlink(missing_ok=True);trace.unlink(missing_ok=True);drive=str(image)
        if 'fault_lba' in spec:
            conf=output/(name+'.conf');conf.write_text('[inject-error]\nevent = "read_aio"\nerrno = "5"\n'
                f'sector = "{spec["fault_lba"]}"\nonce = "'+('on' if spec['fault_once'] else 'off')+'"\n')
            drive=f'blkdebug:{conf}:{image}'
        geometry=',lcyls=260,lheads=16,lsecs=63' if 'kind' in spec else ''
        invocation=command+['-drive',f'file={drive.replace(",",",,")},format=raw,if=none,id=rb,snapshot=on,rerror=report',
            '-device','ide-hd,drive=rb,bus=ide.0,unit=0'+geometry,
            '-debugcon','file:'+str(log),'-trace',f'events={events},file={trace}']
        if rom is not None:invocation += ['-option-rom',str(source/f'int13-{rom}.rom')]
        expected=[];screens=[];attempt=0;before_low=None
        with error.open('w') as errors,subprocess.Popen(invocation,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,bufsize=1) as process:
            try:
                qmp=Qmp(process);wait_marker(process,log,'RB MENU READY')
                for serial,(key,view) in enumerate(actions):
                    if key=='ret' and view==11:expected += expected_reads(spec,len(payload),attempt);attempt+=1
                    if key:
                        qmp.call('send-key',{'keys':[{'type':'qcode','data':key}],'hold-time':30});time.sleep(0.05)
                        wait_marker(process,log,f'RB MENU {serial:04X} view={view:04X} selected={2 if serial else 0:04X} page=0000')
                    qmp.call('stop');paths={k:output/f'{name}-{serial:02d}-{k}.bin' for k in ('ram','low','vga')}
                    for k,address,length in (('ram',0x10000,0x10000),('low',0,0x8000),('vga',0xB8000,4000)):
                        qmp.call('pmemsave',{'val':address,'size':length,'filename':str(paths[k])})
                    ram,low,vga=(paths[k].read_bytes() for k in ('ram','low','vga'));check_runtime_memory(ram,payload,memory,mode)
                    if before_low is None:before_low=low
                    if low[0x7C00:0x7E00]!=before_low[0x7C00:0x7E00] or low[0x800:0x840]!=before_low[0x800:0x840]:raise ValueError('Journal staged a handoff')
                    if view==11:rows=check_journal_screen(vga,strings,spec,crcs)
                    else:
                        boot=ram[memory['symbols']['_rb_boot']:memory['symbols']['_rb_boot']+12]
                        rows=check_screen(vga,view,2 if serial else 0,mode,mbr,boot,strings)
                    (output/f'{name}-{serial:02d}.txt').write_text('\n'.join(rows)+'\n',encoding='utf-8')
                    if serial in (1,2):qmp.call('screendump',{'filename':str(output/f'{name}-{serial:02d}.png'),'format':'png'})
                    screens.append(dict(key=key,view=view,vga_sha256=sha256(paths['vga'])));qmp.call('cont')
                qmp.call('quit')
                if process.wait(timeout=5)!=0:raise ValueError('QEMU failed to exit')
            finally:
                if process.poll() is None:process.kill();process.wait(timeout=5)
        text=log.read_text();check_c_status(text,mode);copies=spec.get('copies',[0,0])
        marker=f'RB JOURNAL load={spec.get("load",0):04X} detail={spec.get("detail",0):04X} status={spec.get("journal",0):04X} copies={copies[0]:04X}{copies[1]:04X} observation={spec.get("observation",0):04X}'
        if text.count('RB JOURNAL BEGIN')!=3 or re.findall(r'RB JOURNAL load=[^\r\n]+',text)!=[marker]*3:raise ValueError('Wrong journal diagnostics: '+name)
        if 'RB HANDOFF' in text or 'RB PROFILE BEGIN' in text:raise ValueError('Journal entered a boot path')
        trace_text=trace.read_text();check_trace(trace_text);lbas=read_lbas(trace_text)
        if rom is not None:
            check_bios_route(text,mode);calls=check_bios_route(text.split('RB MENU READY',1)[0],mode)
            check_reads(lbas[1+calls.count('42' if mode=='EDD' else '02'):],expected)
            pairs.setdefault(spec.get('kind',fixture),{})[mode]=lbas
        elif lbas!=pairs[fixture]['EDD']:raise ValueError('Uninstrumented journal read sequence differs')
        if sha256(image)!=original:raise ValueError('Journal changed the source image')
        results.append(dict(name=name,fixture=fixture,mode=mode,spec=spec,crcs=crcs,screens=screens,read_lbas=lbas,post_menu_reads=expected,image_unchanged=True,block_writes=0))
        print(f'{name}: {len(screens)} states; bounded fresh journal reads; no writes',flush=True)
    if any(len(p)==2 and p['EDD']!=p['CHS'] for p in pairs.values()):raise ValueError('Journal EDD/CHS sequences differ')
    result_file.write_text(json.dumps(dict(ui=manifest['ui'],qemu_version=subprocess.check_output([str(qemu),'--version'],text=True).splitlines()[0],
        qemu_sha256=sha256(qemu),bios_sha256=sha256(bios),vga_bios_sha256=sha256(bios.with_name('vgabios-stdvga.bin')),
        machine='pc-i440fx-8.2',cpu='486',ram_mib=16,cases=results),indent=2,sort_keys=True)+'\n')


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,IndexError,subprocess.SubprocessError) as error:
        print(f'Journal test: {error}',file=sys.stderr);sys.exit(1)
