"""Boot the independent floppy with absent/damaged HDDs; verify no disk writes."""
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
    from .build_inputs import check_build_inputs
    from .build_rescue import ROOT, prepare_output, sha256, HDD_CASES
    from .rescue_text import LANGUAGES, load_catalog, metadata, output_name
    from .test_menu import Qmp, screen_rows, wait_marker
    from .test_hdd import check_bios_route
    from .backup_vectors import cases as backup_cases
    from .backup_encode_vectors import assertions as encode_assertions
    from .backup_stream_vectors import assertions as stream_assertions
    from .backup_live_vectors import assertions as live_assertions, check_reads as check_live_reads
    from .rescue_file_fixtures import specifications as file_specs, expected_file_reads
    from .backup_boot_vectors import cases as boot_cases
    from .backup_record_vectors import cases as record_cases
    from .backup_target_vectors import ASSERTIONS as TARGET_ASSERTIONS, check_reads as check_target_reads
    from .backup_plan_vectors import assertions as plan_assertions, check_reads as check_plan_reads
    from .backup_payload_vectors import assertions as payload_assertions, check_reads as check_payload_reads
except ImportError:
    from build_inputs import check_build_inputs
    from build_rescue import ROOT, prepare_output, sha256, HDD_CASES
    from rescue_text import LANGUAGES, load_catalog, metadata, output_name
    from test_menu import Qmp, screen_rows, wait_marker
    from test_hdd import check_bios_route
    from backup_vectors import cases as backup_cases
    from backup_encode_vectors import assertions as encode_assertions
    from backup_stream_vectors import assertions as stream_assertions
    from backup_live_vectors import assertions as live_assertions, check_reads as check_live_reads
    from rescue_file_fixtures import specifications as file_specs, expected_file_reads
    from backup_boot_vectors import cases as boot_cases
    from backup_record_vectors import cases as record_cases
    from backup_target_vectors import ASSERTIONS as TARGET_ASSERTIONS, check_reads as check_target_reads
    from backup_plan_vectors import assertions as plan_assertions, check_reads as check_plan_reads
    from backup_payload_vectors import assertions as payload_assertions, check_reads as check_payload_reads

REASONS=('OK','NO_DISK','PARAMS','GEOMETRY','IO','CHANGED')
FILE_ACTIONS=((None,0),('f4',2),('ret',2),('esc',0),('ret',1),('f4',2),('esc',0))
ACTIONS=((None,0),('ret',1),('ret',1),('f2',1),('f9',1),('esc',0),('ret',1))

def expected_reads(spec,attempt):
    if spec.get('status') in (1,2,3):return []
    if spec.get('status')==4:return [0,0,0]
    if spec.get('layout') in (2,5) and not spec.get('error_lba'):return [0,0]
    if spec.get('fault_lba')==63:return [0,63,63,63,0]
    return ([0] if spec.get('fault_once') and attempt==0 else [])+[0,63,0]

def trace_reads(trace):
    reads=[(int(a),int(b)) for a,b in re.findall(r'ide_sector_read sector=(\d+) nsectors=(\d+)',trace)]
    if any(count!=1 for _,count in reads):raise ValueError('Rescue used a multi-sector HDD read')
    return [lba for lba,_ in reads]

def check_memory(ram,payload,memory,zero_bss=True):
    h=memory['header'];start,end=h['bss_begin'],h['bss_end']
    if (len(ram)!=65536 or ram[:len(payload)]!=payload or (zero_bss and any(ram[start:end]))
            or ram[end:0xE000]!=b'\xa5'*(0xE000-end)
            or ram[0xE000:0xE002]!=b'\x5a\xa5'):
        raise ValueError('Rescue code/BSS/stack guard changed')

def check_screen(data,strings,view,spec,mode,capacity,geometry,mbr):
    rows=screen_rows(data);status=spec.get('status',0);layout=spec.get('layout',0)
    reason='READY' if not view else REASONS[status] if status else 'BAD_LAYOUT' if layout else 'OK'
    cells=[(2,4,strings['TITLE']),(2,65,strings['READ_ONLY']),(5,4,strings['SCOPE']),(6,4,strings['LIMIT']),
        (8,4,strings[reason]),(21,4,strings['HELP']),(22,4,strings['IDENTITY'])]
    blank=[]
    if not view:blank=list(range(9,20))
    else:
        cells += [(9,4,strings['CODES']),(9,32,f'0x{status:04X} / 0x{layout:04X}'),(11,4,strings['DRIVES']),
            (11,32,'0x0000 / 0x0080'),(19,4,strings['LBA']),(19,32,f'0x{spec.get("error_lba",0):08X}')]
        if status in (1,2,3):blank += [12,13,14]
        else:
            cells += [(12,4,strings['ROUTE']),(12,32,mode),(13,4,strings['CAPACITY']),(13,32,f'0x{capacity:016X}'),
                (14,4,strings['GEOMETRY_LABEL']),(14,32,f'0x{geometry[0]:04X} / 0x{geometry[1]:04X}')]
        if status:blank += [15,16,17,18]
        else:
            import zlib
            cells += [(15,4,strings['DISK_ID']),(15,32,f'0x{struct.unpack_from("<I",mbr,440)[0]:08X}'),
                (16,4,strings['CRC']),(16,32,f'0x{zlib.crc32(mbr):08X}'),(17,4,strings['SIGNATURE']),
                (17,32,f'0x{spec.get("signature",0xAA55):04X} / 0x{spec.get("marker",0):04X}'),
                (18,4,strings['COUNTS']),(18,32,f'0x{spec.get("entries",0):04X} / 0x{spec.get("ebrs",0):04X}')]
    for row,col,value in cells:
        if rows[row][col:col+len(value)]!=value:raise ValueError(f'Rescue VGA {row},{col}: expected {value!r}, got {rows[row]!r}')
    if any(rows[row][4:78].strip() for row in blank):raise ValueError('Rescue retained stale diagnosis fields')
    color=0x1A if view and not status and not layout else 0x1E
    if data[(8*80+4)*2+1]!=color:raise ValueError('Wrong rescue status color')
    for row in range(2,23):
        if row!=4 and (data[(row*80+1)*2]!=0xB3 or data[(row*80+78)*2]!=0xB3):raise ValueError('Rescue overwrote frame')
    return rows

def floppy_reads(text):
    return [int(n,16) for n in re.findall(r'^%([0-9A-F]{4})$',text,re.M)]


def check_file_screen(data,s,spec):
    rows=screen_rows(data);status=spec['file'];check=spec['check'];detail=spec['detail']
    reason='B_MISSING' if status==5 else 'B_IO' if status==1 else 'B_FILE_BAD' if status else 'B_BAD' if check else 'B_OK'
    cells=[(2,4,s['TITLE']),(2,65,s['READ_ONLY']),(5,4,s['B_SCOPE']),(6,4,s['B_LIMIT']),
        (8,4,s[reason]),(9,4,s['B_CODES']),(9,32,f'0x{status:04X} / 0x{check:04X} / 0x{detail:04X}'),
        (10,4,s['B_NESTED']),(10,32,f'0x{spec['nested']:04X}'),
        (16,4,s['B_FILE_LBA']),(16,32,f'0x{spec['file_lba']:08X}'),
        (17,4,s['B_DISK_LBA']),(17,32,f'0x{spec.get('disk_lba',0):08X}'),
        (18,4,s['B_EXTENT']),(18,32,f'0x{spec.get('kind',0):04X} / 0x{spec.get('index',0):04X}'),
        (21,4,s['B_HELP']),(22,4,s['B_BOUNDARY'])]
    blank=[7,11,15,19,20]
    if status or check:blank += [12,13,14]
    else:cells += [(12,4,s['B_COUNTS']),(12,32,'0x0002 / 0x0001 / 0x0001'),
        (13,4,s['B_SECTORS']),(13,32,f'0x{spec['reserved']:04X}'),(14,4,s['B_READY']),(14,32,'0x0001')]
    for row,col,value in cells:
        if rows[row][col:col+len(value)]!=value:raise ValueError(f'File VGA {row},{col}: expected {value!r}, got {rows[row]!r}')
    if any(rows[row][4:78].strip() for row in blank):raise ValueError('File page retained stale fields')
    if data[(8*80+4)*2+1]!=(0x1A if not status and not check else 0x1E):raise ValueError('Wrong file status color')
    for row in range(2,23):
        if row!=4 and (data[(row*80+1)*2]!=0xB3 or data[(row*80+78)*2]!=0xB3):raise ValueError('File page overwrote frame')
    return rows


def scenarios():
    cases=[dict(name=name+'-'+mode.lower(),fixture=name,spec=spec,mode=mode,rom=rom)
           for name,spec in HDD_CASES.items() for mode,rom in (('EDD',0),('CHS',1))]
    cases += [dict(name='no-hdd',fixture=None,spec=dict(status=1),mode='EDD',rom=0)]
    for rom in range(2,10):
        spec=dict(HDD_CASES['metadata-only']) if rom<4 else dict(status=3 if rom<6 else 2)
        cases.append(dict(name=f'bios-{rom}',fixture='metadata-only',spec=spec,mode='CHS' if rom<6 else 'EDD',rom=rom))
    cases += [dict(name='bare',fixture='metadata-only',spec=HDD_CASES['metadata-only'],mode='EDD',rom=None),
              dict(name='floppy-retry',fixture='metadata-only',spec=HDD_CASES['metadata-only'],mode='EDD',rom=10)]
    for image,marker in (('rescue-model','RB RESCUE MODEL PASS'),('backup-model','RB BACKUP MODEL PASS'),('rescue-bss-fault','RB RESCUE STARTUP ERROR'),
            ('backup-records-model','RB BACKUP RECORDS PASS'),('backup-boot-model','RB BACKUP BOOT PASS'),('rescue-file-model','RB RESCUE FILE PASS'),
            ('backup-target-model','RB BACKUP TARGET PASS'),
            ('backup-plan-model','RB BACKUP PLAN PASS'),
            ('backup-payload-model','RB BACKUP PAYLOAD PASS'),
            ('backup-encode-model','RB BACKUP ENCODE PASS'),
            ('backup-stream-model','RB BACKUP STREAM PASS'),
            ('backup-live-model','RB BACKUP LIVE PASS'),
            ('rescue-data-fault','RB RESCUE STARTUP ERROR'),('rescue-crc-fault','RB RESCUE LOAD ERROR'),
            ('rescue-header-fault','RB RESCUE LOAD ERROR')):
        cases.append(dict(name=image,image=image,fixture=None,rom=0,marker=marker))
    cases.append(dict(name='floppy-io',fixture=None,rom=0,marker='RB RESCUE LOAD ERROR',floppy_fault=False))
    cases.append(dict(name='floppy-rejected',fixture=None,rom=11,marker='RB RESCUE LOAD ERROR'))
    for name,spec in file_specs().items():
        cases.append(dict(name=name,image=name,file_case=name,file_spec=spec,
            fixture='metadata-only' if name=='file-demo-hdd' else None,
            spec=HDD_CASES['metadata-only'] if name=='file-demo-hdd' else dict(status=1),mode='EDD',
            rom=12 if name=='file-retry' else 13 if name=='file-root-io' else 0))
    return cases

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--language',choices=LANGUAGES,default='en')
    p.add_argument('--qemu',default='qemu-system-i386');p.add_argument('--bios',type=Path);p.add_argument('--case',action='append');args=p.parse_args()
    found=shutil.which(args.qemu)
    if not found:raise ValueError('QEMU not found')
    qemu=Path(found).resolve();bios=(args.bios or qemu.parent.parent/'share/seabios/bios-256k.bin').resolve()
    source=ROOT/'build'/output_name('rescue',args.language);out=ROOT/'build'/output_name('rescue-test',args.language);prepare_output(out)
    report=out/'rescue-results.json';report.unlink(missing_ok=True)
    manifest=json.loads((source/'manifest.json').read_text());strings=load_catalog(args.language)
    check_build_inputs(manifest, ROOT)
    if manifest['ui']!=metadata(args.language):raise ValueError('Stale rescue language build')
    cases=scenarios()
    if args.case:
        cases=[c for c in cases if c['name'] in args.case]
        if set(args.case)-{c['name'] for c in cases}:raise ValueError('Unknown rescue case')
    events=out/'events.txt';events.write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
    command=[str(qemu),'-L',str(bios.parent),'-bios',str(bios),'-machine','pc-i440fx-8.2,accel=tcg','-cpu','486','-m','16',
        '-nodefaults','-vga','std','-boot','a','-display','none','-monitor','none','-serial','none','-nic','none','-no-reboot',
        '-global','isa-debugcon.iobase=0xe9','-qmp','stdio']
    results=[]
    for case in cases:
        name=case['name'];image_name=case.get('image','retroboot-rescue');image=source/(image_name+'.img')
        images=[image];drive=str(image);log=out/(name+'.log');trace=out/(name+'.trace');err=out/(name+'-stderr.log')
        log.unlink(missing_ok=True);trace.unlink(missing_ok=True)
        if 'floppy_fault' in case:
            conf=out/(name+'-floppy.conf');conf.write_text('[inject-error]\nevent = "read_aio"\nerrno = "5"\nsector = "33"\nonce = "'+('on' if case['floppy_fault'] else 'off')+'"\n')
            drive=f'blkdebug:{conf}:{image}'
        invocation=command+['-drive',f'file={drive.replace(",",",,")},format=raw,if=floppy,readonly=on',
            '-debugcon','file:'+str(log),'-trace',f'events={events},file={trace}']
        mbr=bytes(512);work_disk=None
        if case.get('fixture'):
            disk=source/('disk-'+case['fixture']+'.img');images.append(disk)
            # A disposable writable raw copy exposes writes to the trace. Fixed
            # physical/logical geometry avoids QEMU's pre-boot MBR geometry read.
            work_disk=out/(name+'-work.img');shutil.copyfile(disk,work_disk);hdpath=str(work_disk)
            with disk.open('rb') as stream:mbr=stream.read(512)
            spec=case['spec']
            if 'fault_lba' in spec:
                conf=out/(name+'-hdd.conf');conf.write_text('[inject-error]\nevent = "read_aio"\nerrno = "5"\n'
                    f'sector = "{spec["fault_lba"]}"\nonce = "'+('on' if spec['fault_once'] else 'off')+'"\n')
                hdpath=f'blkdebug:{conf}:{work_disk}'
            invocation += ['-drive',f'file={hdpath.replace(",",",,")},format=raw,if=none,id=rb,rerror=report',
                '-device','ide-hd,drive=rb,bus=ide.0,unit=0,cyls=130,heads=16,secs=63,lcyls=130,lheads=16,lsecs=63']
        if case['rom'] is not None:invocation += ['-option-rom',str(source/f'int13-{case["rom"]}.rom')]
        before={str(path):sha256(path) for path in images}
        if any(value!=manifest['artifacts'][Path(path).name]['sha256'] for path,value in before.items()):raise ValueError('Changed rescue fixture')
        screens=[];expected=[];expected_floppy=[];file_attempt=0;first_low=None;previous_low=None;initial_trace=''
        with err.open('w') as errors,subprocess.Popen(invocation,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,bufsize=1) as process:
            try:
                qmp=Qmp(process)
                # Complete boot-area fault/boundary vectors stream substantially
                # more model sectors; ordinary startup/UI deadlines stay at 15s.
                wait_marker(process,log,case.get('marker','RB RESCUE READY'),
                    timeout=120 if name=='backup-live-model' else 60 if name in ('backup-plan-model','backup-encode-model','backup-payload-model','backup-stream-model') else 15)
                if 'marker' not in case:
                    payload=(source/'retroboot-rescue.bin').read_bytes();memory=manifest['memory']['retroboot-rescue']
                    spec=case['spec'];mode=case['mode'];attempt=0
                    for serial,(key,view) in enumerate(FILE_ACTIONS if 'file_case' in case else ACTIONS):
                        if view==2 and key in ('f4','ret'):
                            expected_floppy+=expected_file_reads(image.read_bytes(),case['file_case'],file_attempt);file_attempt+=1
                        if key=='ret' and view==1:expected+=expected_reads(spec,attempt);attempt+=1
                        if key:
                            qmp.call('send-key',{'keys':[{'type':'qcode','data':key}],'hold-time':30});time.sleep(0.05)
                            wait_marker(process,log,f'RB RESCUE KEY {serial:04X} view={view:04X}')
                        # Allow the display refresh to finish before freezing
                        # the VM; VGA bytes alone do not flush QEMU's renderer.
                        time.sleep(0.08)
                        qmp.call('stop');paths={k:out/f'{name}-{serial:02d}-{k}.bin' for k in ('ram','low','vga')}
                        for k,address,length in (('ram',0x10000,0x10000),('low',0,0x8000),('vga',0xB8000,4000)):
                            qmp.call('pmemsave',{'val':address,'size':length,'filename':str(paths[k])})
                        ram,low,vga=(paths[k].read_bytes() for k in ('ram','low','vga'));check_memory(ram,payload,memory,zero_bss='file_case' not in case or serial==0)
                        if first_low is None:
                            first_low=low;initial_trace=trace.read_text()
                            if trace_reads(initial_trace):raise ValueError('HDD was read before Enter')
                        if low[0x7C00:0x7E00]!=first_low[0x7C00:0x7E00] or low[0x800:0x840]!=first_low[0x800:0x840]:raise ValueError('Rescue staged a HDD boot')
                        if 'file_case' in case and serial==5 and previous_low[0x500:0x560]!=low[0x500:0x560]:raise ValueError('File reader changed HDD context')
                        previous_low=low
                        if floppy_reads(log.read_text())!=expected_floppy:raise ValueError('Unexpected floppy read sequence: '+name)
                        capacity=131072 if mode=='EDD' else 130032 # SeaBIOS exposes 129 * 16 * 63
                        rows=check_file_screen(vga,strings,case['file_spec']) if view==2 else check_screen(vga,strings,view,spec,mode,capacity,(0,0) if mode=='EDD' else (16,63),mbr)
                        (out/f'{name}-{serial:02d}.txt').write_text('\n'.join(rows)+'\n',encoding='utf-8')
                        if serial in (0,1):qmp.call('screendump',{'filename':str(out/f'{name}-{serial:02d}.png'),'format':'png'})
                        if trace_reads(trace.read_text())!=expected:raise ValueError('Unexpected rescue HDD sector sequence: '+name)
                        screens.append(dict(key=key,view=view,vga_sha256=sha256(paths['vga'])));qmp.call('cont')
                else:
                    qmp.call('stop');qmp.call('screendump',{'filename':str(out/(name+'.png')),'format':'png'})
                    if case['name']=='rescue-model' and 'R=001C' not in log.read_text():raise ValueError('Missing native rescue assertions')
                    if case['name']=='backup-model' and f'B={3*len(backup_cases()):04X}' not in log.read_text():raise ValueError('Missing native backup assertions')
                    if case['name']=='backup-records-model' and f'C={4*len(record_cases()):04X}' not in log.read_text():raise ValueError('Missing native saved-record assertions')
                    if case['name']=='backup-boot-model' and f'D={6*len(boot_cases()):04X}' not in log.read_text():raise ValueError('Missing native boot-area assertions')
                    if case['name']=='rescue-file-model' and 'E=0020' not in log.read_text():raise ValueError('Missing native file assertions')
                    if case['name']=='backup-target-model':
                        if f'F={TARGET_ASSERTIONS:04X}' not in log.read_text():raise ValueError('Missing native target assertions')
                        match=re.search(r'^L=([0-9A-F,]+)$',log.read_text(),re.M)
                        if not match:raise ValueError('Missing target-model read evidence')
                        check_target_reads([int(x,16) for x in match[1].split(',') if x])
                    if case['name'] in ('backup-stream-model','backup-live-model'):
                        marker=f'K={live_assertions():04X}' if name=='backup-live-model' else f'J={stream_assertions():04X}'
                        if marker not in log.read_text():raise ValueError('Missing native stream assertions')
                        if name=='backup-live-model':
                            match=re.search(r'^L=([0-9A-F,]+)$',log.read_text(),re.M)
                            if not match:raise ValueError('Missing live-binding read evidence')
                            check_live_reads([int(x,16) for x in match[1].split(',') if x])
                        paths={k:out/(name+'-'+k+'.bin') for k in ('ram','vga')}
                        qmp.call('pmemsave',{'val':0x10000,'size':65536,'filename':str(paths['ram'])})
                        qmp.call('pmemsave',{'val':0xB8000,'size':4000,'filename':str(paths['vga'])})
                        check_memory(paths['ram'].read_bytes(),(source/(name+'.bin')).read_bytes(),manifest['memory'][name],zero_bss=False)
                        visible='\n'.join(screen_rows(paths['vga'].read_bytes()))
                        if marker not in visible or case['marker'] not in visible or '!' in visible:
                            raise ValueError('Stream result is not visible on VGA')
                        (out/(name+'.txt')).write_text(visible+'\n',encoding='utf-8')
                    if case['name']=='backup-encode-model':
                        marker=f'H={encode_assertions():04X}'
                        if marker not in log.read_text():raise ValueError('Missing native metadata-encoder assertions')
                        paths={k:out/f'{name}-{k}.bin' for k in ('ram','vga')}
                        for k,address,length in (('ram',0x10000,0x10000),('vga',0xB8000,4000)):
                            qmp.call('pmemsave',{'val':address,'size':length,'filename':str(paths[k])})
                        check_memory(paths['ram'].read_bytes(),(source/(name+'.bin')).read_bytes(),manifest['memory'][name],zero_bss=False)
                        visible='\n'.join(screen_rows(paths['vga'].read_bytes()))
                        if marker not in visible or 'RB BACKUP ENCODE PASS' not in visible or '!' in visible:
                            raise ValueError('Metadata-encoder result is not visible on VGA')
                        (out/(name+'.txt')).write_text(visible+'\n',encoding='utf-8')
                    if case['name']=='backup-payload-model':
                        marker=f'I={payload_assertions():04X}'
                        if marker not in log.read_text():raise ValueError('Missing native payload assertions')
                        match=re.search(r'^P=([0-9A-F,]+)$',log.read_text(),re.M)
                        if not match:raise ValueError('Missing payload read evidence')
                        check_payload_reads([int(x,16) for x in match[1].split(',') if x])
                        paths={k:out/f'{name}-{k}.bin' for k in ('ram','vga')}
                        for k,address,length in (('ram',0x10000,0x10000),('vga',0xB8000,4000)):
                            qmp.call('pmemsave',{'val':address,'size':length,'filename':str(paths[k])})
                        check_memory(paths['ram'].read_bytes(),(source/(name+'.bin')).read_bytes(),manifest['memory'][name],zero_bss=False)
                        visible='\n'.join(screen_rows(paths['vga'].read_bytes()))
                        if marker not in visible or 'RB BACKUP PAYLOAD PASS' not in visible or '!' in visible:
                            raise ValueError('Payload result is not visible on VGA')
                        if 'P=' in visible or ',' in visible:raise ValueError('Payload address trace leaked onto VGA')
                        (out/(name+'.txt')).write_text(visible+'\n',encoding='utf-8')
                    if case['name']=='backup-plan-model':
                        if f'G={plan_assertions():04X}' not in log.read_text():raise ValueError('Missing native capture-plan assertions')
                        match=re.search(r'^L=([0-9A-F,]+)$',log.read_text(),re.M)
                        if not match:raise ValueError('Missing capture-plan read evidence')
                        check_plan_reads([int(x,16) for x in match[1].split(',') if x])
                        vga=out/(name+'-vga.bin')
                        qmp.call('pmemsave',{'val':0xB8000,'size':4000,'filename':str(vga)})
                        rows=screen_rows(vga.read_bytes());visible='\n'.join(rows)
                        if f'G={plan_assertions():04X}' not in visible or 'RB BACKUP PLAN PASS' not in visible:
                            raise ValueError('Capture-plan result is not visible on VGA')
                        if 'L=' in visible or ',' in visible:
                            raise ValueError('Capture-plan address trace leaked onto VGA')
                        (out/(name+'.txt')).write_text(visible+'\n',encoding='utf-8')
                qmp.call('quit')
                if process.wait(timeout=5):raise ValueError('QEMU exit failed')
            finally:
                if process.poll() is None:process.kill();process.wait(timeout=5)
        text=log.read_text();trace_text=trace.read_text();lbas=trace_reads(trace_text)
        if lbas!=expected or '!W' in text or 'ide_sector_write' in trace_text or 'blk_co_pwritev' in trace_text:raise ValueError('Unexpected rescue I/O or write attempt')
        if text.count('!F')!={10:1,11:3,12:1,13:9}.get(case['rom'],0):raise ValueError('Wrong number of floppy retries')
        if 'marker' not in case:
            status=case['spec'].get('status',0);layout_code=case['spec'].get('layout',0)
            marker=f'RB RESCUE status={status:04X} layout={layout_code:04X}'
            if re.findall(r'RB RESCUE status=[^\r\n]+',text)!=[marker]*(1 if 'file_case' in case else 3):raise ValueError('Wrong rescue result markers')
            if 'file_case' in case:
                fs=case['file_spec'];marker=f'RB FILE status={fs["file"]:04X} check={fs["check"]:04X} detail={fs["detail"]:04X} nested={fs["nested"]:04X}'
                if re.findall(r'RB FILE status=[^\r\n]+',text)!=[marker]*3:raise ValueError('Wrong file result markers')
            if case['rom'] is not None and status!=1:
                for part in text.split('RB RESCUE BEGIN')[1:]:
                    calls=check_bios_route(part,case['mode'])
                    if any(c in ('03','05','0B','43') for c in calls):raise ValueError('BIOS write called')
            if text.count('RB RESCUE UI '+args.language+' CP437')!=1:raise ValueError('Wrong rescue language')
        elif 'RB RESCUE READY' in text:raise ValueError('Rejected/model boot entered the normal UI')
        if any(sha256(Path(path))!=value for path,value in before.items()):raise ValueError('Source medium changed')
        if work_disk:
            if sha256(work_disk)!=before[str(disk)]:raise ValueError('Disposable HDD changed')
            work_disk.unlink()
        results.append(dict(case=case,screens=screens,read_lbas=lbas,floppy_lbas=floppy_reads(text),image_unchanged=True,block_writes=0,log=text))
        print(f'{name}: {len(screens)} states; independent startup; unchanged media; no writes',flush=True)
    check_build_inputs(manifest, ROOT)
    report.write_text(json.dumps(dict(ui=manifest['ui'],build_inputs=manifest['build_inputs'],qemu_version=subprocess.check_output([str(qemu),'--version'],text=True).splitlines()[0],
        qemu_sha256=sha256(qemu),bios_sha256=sha256(bios),vga_bios_sha256=sha256(bios.with_name('vgabios-stdvga.bin')),
        machine='pc-i440fx-8.2',cpu='486',ram_mib=16,cases=results),indent=2,sort_keys=True)+'\n')

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,IndexError,subprocess.SubprocessError) as error:print('Rescue test: '+str(error),file=sys.stderr);sys.exit(1)
