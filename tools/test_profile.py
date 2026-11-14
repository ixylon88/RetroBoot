"""Run F9 through fresh records, visibility gates and an exact owned test VBR."""
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
    from .config_fixtures import FILE_LBAS as CFG_LBAS
    from .profile_fixtures import BASE_READS, expected_preview
    from .test_handoff import check_receipt
    from .test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
    from .test_menu import Qmp, check_screen, screen_rows, wait_marker
    from .test_state import PROOF_KEYS
    from .test_visibility import check_visibility_screen
    from .ui_text import LANGUAGES, checked_catalog, output_name
except ImportError:
    from build_hdd import ROOT, prepare_output, sha256
    from config_fixtures import FILE_LBAS as CFG_LBAS
    from profile_fixtures import BASE_READS, expected_preview
    from test_handoff import check_receipt
    from test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
    from test_menu import Qmp, check_screen, screen_rows, wait_marker
    from test_state import PROOF_KEYS
    from test_visibility import check_visibility_screen
    from ui_text import LANGUAGES, checked_catalog, output_name

REASONS = ('', 'PROFILE_TEST_SELECTION', 'PROFILE_TEST_PROOF', 'PROFILE_TEST_CHANGE',
           'PROFILE_TEST_TARGET', 'PROFILE_TEST_CODE')


def check_rejection(data, strings, status, expected):
    rows = screen_rows(data)
    proof = expected.get('proof', 0) if status == 2 else 0
    detail = expected.get('detail', 0) if status == 2 else 0
    for row, col, value in ((2,65,strings['READ_ONLY']), (5,4,strings['PROFILE_TEST_FAILED']),
            (6,4,strings[REASONS[status]]), (8,4,strings['PROFILE_TEST_REASON']),
            (10,4,f'0x{status:04X} / 0x{proof:04X} / 0x{detail:04X}'), (14,4,strings['LBA_HEX']),
            (14,23,f'0x{expected.get("error_lba", 0) if status in (2,5) else 0:08X}'),
            (17,4,strings['NO_CHANGES']), (19,4,strings['PROFILE_TEST_REVIEW']),
            (21,4,strings['KEY_HELP']), (22,4,strings['FUNCTION_HELP'])):
        if rows[row][col:col+len(value)] != value:
            raise ValueError(f'Wrong profile rejection at {row},{col}: {value!r}; {rows[row]!r}')
    if status == 2:
        value = strings[PROOF_KEYS[proof]]
        if rows[12][4:4+len(value)] != value: raise ValueError('Missing fresh proof failure reason')
    elif rows[12][4:78].strip(): raise ValueError('Stale proof reason on profile rejection')
    if data[(6*80+4)*2+1] != 0x1E: raise ValueError('Wrong rejection color')
    for row in range(2,23):
        if data[(row*80+1)*2] != 0xB3 or data[(row*80+78)*2] != 0xB3: raise ValueError('Overwritten profile frame')
    if any(rows[row][4:78].strip() for row in (7,9,11,13,15,16,18,20)):
        raise ValueError('Profile rejection retained a stale plan or start hint')
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu',default='qemu-system-i386')
    parser.add_argument('--bios',type=Path)
    parser.add_argument('--language',choices=LANGUAGES,default='en')
    args=parser.parse_args()
    executable=shutil.which(args.qemu)
    if not executable: raise ValueError('qemu-system-i386 not found')
    qemu=Path(executable).resolve()
    bios=(args.bios or qemu.parent.parent/'share/seabios/bios-256k.bin').resolve()
    if not bios.is_file() or not bios.with_name('vgabios-stdvga.bin').is_file(): raise ValueError('Missing BIOS ROMs')
    source=ROOT/'build'/output_name('hdd',args.language)
    output=ROOT/'build'/output_name('profile',args.language)
    prepare_output(output)
    result_file=output/'profile-results.json';result_file.unlink(missing_ok=True)
    manifest=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    strings=checked_catalog(manifest,args.language)
    for name,info in manifest['artifacts'].items():
        if name.startswith(('stage2','int13-','handoff-vbr')) and sha256(source/name)!=info['sha256']:
            raise ValueError('Changed profile-test component: '+name)
    vbr=(source/'handoff-vbr.bin').read_bytes()
    events=output/'ide-events.txt';events.write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n',encoding='ascii')
    command=[str(qemu),'-L',str(bios.parent),'-bios',str(bios),'-machine','pc-i440fx-8.2,accel=tcg',
             '-cpu','486','-m','16','-nodefaults','-vga','std','-boot','c','-display','none',
             '-monitor','none','-serial','none','-nic','none','-no-reboot',
             '-global','isa-debugcon.iobase=0xe9','-qmp','stdio']
    fixtures={**manifest['profile_cases'],'retroboot-handoff':{'base':'retroboot-handoff'},
              'retroboot-hdd':{'base':'retroboot-hdd','normal':True}}
    scenarios=[(name,spec,mode,rom) for name,spec in fixtures.items() for mode,rom in (('EDD',0),('CHS',1))]
    scenarios.append(('retroboot-handoff',fixtures['retroboot-handoff'],'EDD',None))
    results,pairs=[],{}

    for fixture,spec,mode,rom in scenarios:
        name=fixture+'-'+(mode.lower() if rom is not None else 'bare')
        preview=expected_preview(spec)
        status=spec.get('status',0);normal=spec.get('normal',False)
        variant='normal' if normal else 'handoff'
        payload=(source/('stage2'+('' if normal else '-handoff')+'.bin')).read_bytes()
        memory=manifest['memory'][variant]
        image=source/(fixture+'.img');image_hash=sha256(image)
        if image_hash!=manifest['artifacts'][image.name]['sha256']: raise ValueError('Changed profile fixture')
        with image.open('rb') as stream:
            mbr=stream.read(512);stream.seek(CFG_LBAS[0]*512);config=stream.read(512)
        count=struct.unpack_from('<H',config,36)[0]
        # Legacy records still appear on F7. The F9 selection gate rejects them.
        if config[8:10]==b'\x01\x00' and count:
            config=config[:64]+b''.join(config[64+i*48:112+i*48]+bytes(4) for i in range(count))+bytes(512-64-count*52)
        log,trace,error=(output/(name+suffix) for suffix in ('.log','.trace','-stderr.log'))
        log.unlink(missing_ok=True);trace.unlink(missing_ok=True)
        drive=str(image)
        if 'fault_lba' in preview:
            conf=output/(name+'.conf')
            conf.write_text('[inject-error]\nevent = "read_aio"\nerrno = "5"\n'
                f'sector = "{preview["fault_lba"]}"\nonce = "'+('on' if preview['fault_once'] else 'off')+'"\n',encoding='ascii')
            drive=f'blkdebug:{conf}:{image}'
        invocation=command+['-drive',f'file={drive.replace(",",",,")},format=raw,if=ide,snapshot=on,rerror=report',
                           '-debugcon','file:'+str(log),'-trace',
                           f'events={str(events).replace(",",",,")},file={str(trace).replace(",",",,")}']
        if rom is not None: invocation+=['-option-rom',str(source/f'int13-{rom}.rom')]
        actions=[(None,0),('f9',0),('f7',8)]
        if spec.get('selected'): actions+=[('left',8)]
        if normal: actions += [('f9',8),('esc',0)]
        elif not status: actions += [('f9',10)]
        else: actions += [('f9',9),('ret',9),('f4',9),('f9',9),('esc',0),('f8',3),('f7',8),('esc',0)]
        screens,expected_reads,before_low,receipt=[],[],None,None
        selected,index,proofs,attempts=0,0,0,0
        with error.open('w',encoding='utf-8') as errors, subprocess.Popen(invocation,stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=errors,text=True,bufsize=1) as process:
            try:
                qmp=Qmp(process);wait_marker(process,log,'RB MENU READY')
                for serial,(key,view) in enumerate(actions):
                    if key=='f8': selected=2
                    if key=='f7':
                        index=0;expected_reads+=preview.get('reads',BASE_READS)
                    if key=='left': index=count-1
                    expected=preview['plans'][index]
                    execute=key=='f9' and view in (9,10) and (serial==3 or serial==4 and spec.get('selected'))
                    if execute:
                        expected_reads+=preview.get('reads',BASE_READS);attempts+=1
                    if key in ('f7','left') or execute and status!=1:
                        if expected.get('proof',0) in (0,14,15):
                            target=struct.unpack_from('<I',config,68+index*52)[0]
                            reads=expected.get('proof_reads',[0,63,target])
                            if proofs and preview.get('fault_once'): reads=[0,63,target]
                            expected_reads+=reads
                        proofs+=1
                    if key:
                        qmp.call('send-key',{'keys':[{'type':'qcode','data':key}],'hold-time':30});time.sleep(0.05)
                        if view==10: wait_marker(process,log,'Test VBR reached. Reboot to return.\n\n')
                        else: wait_marker(process,log,f'RB MENU {serial:04X} view={view:04X} selected={selected:04X} page=0000')
                    qmp.call('stop')
                    paths={kind:output/f'{name}-{serial:02d}-{kind}.bin' for kind in ('vga','ram','low')}
                    for kind,address,length in (('vga',0xB8000,4000),('ram',0x10000,0x10000),('low',0,0x8000)):
                        qmp.call('pmemsave',{'val':address,'size':length,'filename':str(paths[kind])})
                    ram,low,vga=(paths[k].read_bytes() for k in ('ram','low','vga'))
                    check_runtime_memory(ram,payload,memory,mode)
                    if before_low is None: before_low=low
                    if view==10:
                        receipt=check_receipt(low,before_low,vbr);rows=screen_rows(vga)
                        if not rows[0].startswith('RB HANDOFF PASS'): raise ValueError('Missing visible profile test success')
                    else:
                        if low[0x7C00:0x7E00]!=before_low[0x7C00:0x7E00] or low[0x800:0x840]!=before_low[0x800:0x840]:
                            raise ValueError('Rejected or unrequested profile was staged/executed')
                        if view==9:
                            rejection=dict(expected, error_lba=131072) if status==5 else expected
                            rows=check_rejection(vga,strings,status,rejection)
                        elif view==8:
                            rows=check_visibility_screen(vga,strings,preview,expected,mbr,config,index,count)
                            hint='' if normal else strings['PROFILE_TEST_HELP']
                            if rows[20][4:78].rstrip()!=hint: raise ValueError('Wrong availability of F9 hint')
                        else:
                            boot=ram[memory['symbols']['_rb_boot']:memory['symbols']['_rb_boot']+12]
                            rows=check_screen(vga,view,selected,mode,mbr,boot,strings)
                    (output/f'{name}-{serial:02d}.txt').write_text('\n'.join(rows)+'\n',encoding='utf-8')
                    if serial==2 or view in (9,10):
                        qmp.call('screendump',{'filename':str(output/f'{name}-{serial:02d}.png'),'format':'png'})
                    screens.append({'key':key,'view':view,'entry':index,'vga_sha256':sha256(paths['vga'])})
                    qmp.call('cont')
                qmp.call('quit')
                if process.wait(timeout=5)!=0: raise ValueError('QEMU did not exit cleanly')
            finally:
                if process.poll() is None: process.kill();process.wait(timeout=5)
        text=log.read_text(encoding='utf-8');check_c_status(text,mode)
        if text.count('RB PROFILE BEGIN')!=attempts or 'RB HANDOFF BEGIN' in text or 'RB HANDOFF FAIL' in text:
            raise ValueError('Profile test used the wrong entry path')
        expected_pass=int(not normal and not status)
        if text.count('RB HANDOFF PASS')!=expected_pass or bool(receipt)!=bool(expected_pass):
            raise ValueError('Contradictory profile handoff outcome')
        if status:
            proof=preview['plans'][spec.get('selected',0)].get('proof',0) if status!=1 else 0
            detail=preview['plans'][spec.get('selected',0)].get('detail',0) if status!=1 else 0
            index_text=0xFFFF if status==1 else spec.get('selected',0)
            marker=f'RB PROFILE REJECT status={status:04X} proof={proof:04X} detail={detail:04X} index={index_text:04X}'
            if re.findall(r'RB PROFILE REJECT[^\r\n]+',text)!=[marker]: raise ValueError('Wrong profile rejection diagnostics: '+name)
        if text.count(f'RB UI {args.language} CP437')!=1: raise ValueError('Wrong profile test language')
        trace_text=trace.read_text(encoding='utf-8');check_trace(trace_text);lbas=read_lbas(trace_text)
        if rom is not None:
            check_bios_route(text,mode)
            boot_calls=check_bios_route(text.split('RB MENU READY',1)[0],mode)
            boot_reads=1+boot_calls.count('42' if mode=='EDD' else '02')
            if lbas[boot_reads:]!=expected_reads:
                raise ValueError(f'Wrong profile reads: {name}: {lbas[boot_reads:]} != {expected_reads}')
            pairs.setdefault(fixture,{})[mode]=lbas
        elif lbas!=pairs[fixture]['EDD']: raise ValueError('Uninstrumented profile reads differ')
        if sha256(image)!=image_hash: raise ValueError('Profile test changed its image')
        results.append({'name':name,'mode':mode,'status':status,'screens':screens,'receipt':receipt,
                        'post_menu_reads':expected_reads,'read_lbas':lbas,'image_unchanged':True,'block_writes':0})
        print(f'{name}: {len(screens)} states, fresh profile gate and exact T07 target checked; no writes',flush=True)
    if any(p['EDD']!=p['CHS'] for p in pairs.values()): raise ValueError('Profile EDD/CHS reads differ')
    result_file.write_text(json.dumps({'ui':manifest['ui'],'qemu_version':subprocess.check_output([str(qemu),'--version'],text=True).splitlines()[0],
        'qemu_sha256':sha256(qemu),'bios_sha256':sha256(bios),'vga_bios_sha256':sha256(bios.with_name('vgabios-stdvga.bin')),
        'machine':'pc-i440fx-8.2','cpu':'486','ram_mib':16,'cases':results},indent=2,sort_keys=True)+'\n',encoding='utf-8')


if __name__=='__main__':
    try: main()
    except (OSError,ValueError,KeyError,IndexError,subprocess.SubprocessError) as error:
        print(f'Profile test: {error}',file=sys.stderr);sys.exit(1)
