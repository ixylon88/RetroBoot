"""Build an independent, read-only FAT12 diagnostic floppy, never install it."""
import argparse
import json
import os
import re
import struct
import subprocess
import sys
import zlib

try:
    from .build_inputs import source_hashes, check_build_inputs
    from .mbr_restart_fixtures import carrier_images, witness_floppy, RESERVATION_CARRIER, RESERVATION_WITNESS
    from .build_abi_probe import inspect_map, prepare_output
    from .build_hdd import layout, write_fixture
    from .rescue_text import LANGUAGES, metadata, output_name, render_header
    from .setup_toolchain import LOCK, ROOT, TOOLCHAIN, sha256, verify
    from .backup_vectors import model_header, cases as backup_cases, sources as backup_sources
    from .backup_encode_vectors import model_header as encode_header, cases as encode_cases, assertions as encode_assertions
    from .backup_stream_vectors import model_header as stream_header, cases as stream_cases, assertions as stream_assertions
    from .backup_live_vectors import model_header as live_header, cases as live_cases, assertions as live_assertions, expected_reads as live_reads
    from .rescue_file_fixtures import make_fixture as file_fixture, specifications as file_specs, file_chain, put_backup
    from .backup_boot_vectors import model_header as boot_header, cases as boot_cases, fixture as boot_fixture
    from .backup_record_vectors import model_header as record_header, cases as record_cases, fixture as record_fixture
    from .journal_records import io_model_header
    from .backup_target_vectors import ASSERTIONS as TARGET_ASSERTIONS, expected_reads as target_reads
    from .backup_plan_vectors import model_header as plan_header, assertions as plan_assertions, expected_reads as plan_reads, cases as plan_cases
    from .backup_payload_vectors import model_header as payload_header, assertions as payload_assertions, expected_reads as payload_reads, cases as payload_cases
    from .rescue_match_fixtures import disk as match_disk, floppy as match_floppy, specs as match_specs, backup as match_backup, resealed_original
    from .rescue_plan_fixtures import disk as plan_disk, specs as plan_specs, stream_reference
except ImportError:
    from build_inputs import source_hashes, check_build_inputs
    from mbr_restart_fixtures import carrier_images, witness_floppy, RESERVATION_CARRIER, RESERVATION_WITNESS
    from build_abi_probe import inspect_map, prepare_output
    from build_hdd import layout, write_fixture
    from rescue_text import LANGUAGES, metadata, output_name, render_header
    from setup_toolchain import LOCK, ROOT, TOOLCHAIN, sha256, verify
    from backup_vectors import model_header, cases as backup_cases, sources as backup_sources
    from backup_encode_vectors import model_header as encode_header, cases as encode_cases, assertions as encode_assertions
    from backup_stream_vectors import model_header as stream_header, cases as stream_cases, assertions as stream_assertions
    from backup_live_vectors import model_header as live_header, cases as live_cases, assertions as live_assertions, expected_reads as live_reads
    from rescue_file_fixtures import make_fixture as file_fixture, specifications as file_specs, file_chain, put_backup
    from backup_boot_vectors import model_header as boot_header, cases as boot_cases, fixture as boot_fixture
    from backup_record_vectors import model_header as record_header, cases as record_cases, fixture as record_fixture
    from journal_records import io_model_header
    from backup_target_vectors import ASSERTIONS as TARGET_ASSERTIONS, expected_reads as target_reads
    from backup_plan_vectors import model_header as plan_header, assertions as plan_assertions, expected_reads as plan_reads, cases as plan_cases
    from backup_payload_vectors import model_header as payload_header, assertions as payload_assertions, expected_reads as payload_reads, cases as payload_cases
    from rescue_match_fixtures import disk as match_disk, floppy as match_floppy, specs as match_specs, backup as match_backup, resealed_original
    from rescue_plan_fixtures import disk as plan_disk, specs as plan_specs, stream_reference

IMAGE_BYTES = 1474560
PAYLOAD_LBA = 33
MIN_HEADROOM_BYTES = 1536
PROVENANCE_ASSERTIONS = 219
HDD_CASES = {
    'metadata-only': dict(layout=0,entries=5,ebrs=1,marker=1),
    'unknown-code': dict(layout=0,entries=5,ebrs=1,marker=0),
    'erased-mbr': dict(layout=2,signature=0,marker=0,disk_id=0),
    'bad-signature': dict(layout=2,signature=0xAA00,marker=1),
    'gpt-protective': dict(layout=5,marker=1),
    'bad-ebr': dict(layout=2,error_lba=63,marker=1),
    'loop-ebr': dict(layout=12,error_lba=63,marker=1),
    'mbr-io': dict(status=4,fault_lba=0,fault_once=False),
    'mbr-retry': dict(layout=0,entries=5,ebrs=1,marker=1,fault_lba=0,fault_once=True),
    'ebr-io': dict(layout=1,error_lba=63,marker=1,fault_lba=63,fault_once=False),
}

def inspect_payload(data):
    if (not 33 <= len(data) <= 0xC000 or data[:6]!=b'\xeb\x1eRBRS'
            or struct.unpack_from('<H',data,6)[0]!=32
            or struct.unpack_from('<I',data,8)[0]!=len(data)
            or struct.unpack_from('<3H',data,16)!=(0x1000,32,1)):
        raise ValueError('Invalid rescue header or file bounds')
    begin,end,low,top,flags=struct.unpack_from('<5H',data,22)
    if not len(data)<=begin<end<=low or (low,top,flags)!=(0xE000,0xFFFE,0):raise ValueError('Invalid rescue BSS/stack')
    return dict(file_bytes=len(data),bss_begin=begin,bss_end=end,stack_low=low,stack_top=top)

def seal_payload(data):
    inspect_payload(data);result=bytearray(data)
    struct.pack_into('<I',result,12,zlib.crc32(result[32:]));return bytes(result)

def check_headroom(header):
    # Build reserve below the fixed stack guard, not additional stack space.
    remaining = header['stack_low'] - header['bss_end']
    if remaining < MIN_HEADROOM_BYTES:
        raise ValueError(f'Rescue static-memory headroom {remaining} bytes; '
                         f'at least {MIN_HEADROOM_BYTES} required')
    return remaining

def fat12_set(fat,cluster,value):
    if not 0<=cluster<2849 or not 0<=value<=0xFFF:raise ValueError('FAT12 entry outside fixture')
    at=cluster+cluster//2;pair=struct.unpack_from('<H',fat,at)[0]
    pair=(pair&0x000F)|(value<<4) if cluster&1 else (pair&0xF000)|value
    struct.pack_into('<H',fat,at,pair)

def make_image(boot,payload):
    inspect_payload(payload)
    if struct.unpack_from('<I',payload,12)[0]!=zlib.crc32(payload[32:]):raise ValueError('Unsealed rescue payload')
    if (len(boot)!=512 or boot[510:]!=b'\x55\xaa' or boot[11:36]
            !=struct.pack('<HBHBHHBHHHII',512,1,1,2,224,2880,0xF0,9,18,2,0,0)):
        raise ValueError('Unsupported rescue FAT12 BPB')
    image=bytearray(IMAGE_BYTES);image[:512]=boot
    fat=bytearray(9*512);fat[:3]=b'\xf0\xff\xff';sectors=(len(payload)+511)//512
    for i in range(sectors):fat12_set(fat,i+2,0xFFF if i==sectors-1 else i+3)
    image[512:10*512]=fat;image[10*512:19*512]=fat
    root=19*512;image[root:root+11]=b'RB RESCUE  ';image[root+11]=8
    root+=32;image[root:root+11]=b'RBRESCUEBIN';image[root+11]=0x20
    for offset in (16,18,24):struct.pack_into('<H',image,root+offset,0x21) # 1980-01-01
    struct.pack_into('<HI',image,root+26,2,len(payload))
    padded=payload+b'\xa5'*(-len(payload)%512)
    image[PAYLOAD_LBA*512:PAYLOAD_LBA*512+len(padded)]=padded
    return bytes(image)

def hdd_fixture(name):
    if name not in HDD_CASES:raise ValueError('Unknown rescue HDD fixture')
    size,admin,extents=layout(False)
    # Deliberately no HDD boot code, VBR, bootstrap, FAT or Stage 2 contents.
    mbr=bytearray(extents[0]);mbr[432:436]=b'RBM1';ebr=bytearray(extents[63*512])
    if name=='unknown-code':mbr[:440]=b'\xcc'*440
    elif name=='erased-mbr':mbr[:]=bytes(512)
    elif name=='bad-signature':mbr[510]=0
    elif name=='gpt-protective':mbr[498]=0xEE
    elif name=='bad-ebr':ebr[510]=0
    elif name=='loop-ebr':
        ebr[466]=5;struct.pack_into('<II',ebr,470,0,128520)
    return size,{0:bytes(mbr),63*512:bytes(ebr)}

def build(kind='rescue',language='en'):
    if kind not in ('rescue','rescue-repeat'):raise ValueError('Unsupported rescue build output')
    inputs = source_hashes(ROOT)
    destination=ROOT/'build'/output_name(kind,language);prepare_output(destination)
    lock=json.loads(LOCK.read_text());nasm=TOOLCHAIN/('nasm-'+lock['nasm']['version'])/'nasm'
    wcc,wlink=(TOOLCHAIN/'watcom'/name for name in ('wcc','wlink'))
    for name,p in (('wcc',wcc),('wlink',wlink)):verify(p,lock['open_watcom']['executables'][name])
    if subprocess.check_output([str(nasm),'-v'],text=True).split()[:3]!=['NASM','version',lock['nasm']['version']]:raise ValueError('Wrong NASM')
    env={k:v for k,v in os.environ.items() if k.upper() not in {'WCC','WLINK','WATCOM','INCLUDE','LIB','LIBPATH'}}
    def run(*args):
        r=subprocess.run([str(a) for a in args],cwd=ROOT,env=env,capture_output=True,text=True)
        if r.returncode or 'Warning!' in r.stdout+r.stderr:raise ValueError('Build failed: '+r.stdout+r.stderr)
    (destination/'rescue_text.h').write_text(render_header(language),encoding='ascii')
    (destination/'backup_vectors.h').write_text(model_header(),encoding='ascii')
    (destination/'backup_encode_vectors.h').write_text(encode_header(),encoding='ascii')
    (destination/'backup_stream_vectors.h').write_text(stream_header(),encoding='ascii')
    (destination/'backup_live_vectors.h').write_text(live_header(),encoding='ascii')
    (destination/'backup_record_vectors.h').write_text(record_header(),encoding='ascii')
    (destination/'backup_boot_vectors.h').write_text(boot_header(),encoding='ascii')
    (destination/'journal_io_fixture.h').write_text(io_model_header(),encoding='ascii')
    (destination/'backup_plan_vectors.h').write_text(plan_header(),encoding='ascii')
    (destination/'backup_payload_vectors.h').write_text(payload_header(),encoding='ascii')
    objects=[]
    for name,source in (('runtime','core/rescue_runtime.c'),('inspect','core/rescue_inspect.c'),('partitions','core/partitions.c'),('config','core/config.c'),('model','tests/rescue/model.c')):
        obj=destination/(name+'.obj');run(wcc,'-q','-3','-ms','-ecc','-s','-zl','-zld','-w4','-wx','-i=include','-i='+str(destination),'-fo='+str(obj),source)
        if name!='model':objects.append(obj)
    for name,source in (('rescue-ui','core/rescue.c'),('rescue-plan','core/rescue_plan.c'),('rescue-file','core/rescue_file.c'),
            ('rescue-file-tests','tests/rescue/file.c'),('rescue-backup','core/rescue_backup.c'),('backup','core/backup.c'),('backup-tests','tests/backup/model.c'),
            ('backup-format','core/backup_format.c'),('backup-encode','core/backup_encode.c'),
            ('backup-encode-tests','tests/backup/encode.c'),
            ('backup-stream','core/backup_stream.c'),('backup-stream-tests','tests/backup/stream.c'),
            ('mbr-provenance','core/mbr_provenance.c'),('mbr-provenance-tests','tests/backup/provenance.c'),
            ('mbr-restart-core','core/mbr_restart.c'),('mbr-restart-tests','tests/backup/restart.c'),
            ('mbr-reservation-core','core/mbr_reservation.c'),('mbr-reservation-tests','tests/backup/reservation.c'),
            ('backup-live','core/backup_live.c'),('backup-live-tests','tests/backup/live.c'),
            ('backup-boot','core/backup_boot.c'),('backup-boot-tests','tests/backup/boot.c'),
            ('fat-boot','core/fat_boot.c'),('fingerprint','core/fingerprint.c'),('backup-links','core/backup_links.c'),
            ('backup-records','core/backup_records.c'),('backup-record-tests','tests/backup/records.c'),
            ('backup-target','core/backup_target.c'),('backup-target-tests','tests/backup/target.c'),
            ('backup-plan','core/backup_plan.c'),('backup-plan-tests','tests/backup/plan.c'),
            ('backup-payload-tests','tests/backup/payload.c'),
            ('target-audit','core/admin_audit.c'),
            ('saved-state','core/state.c'),('saved-record-io','core/record_io.c'),('saved-volume','core/volume.c')):
        run(wcc,'-q','-3','-ms','-ecc','-s','-zl','-zld','-w4','-wx','-i=include','-i='+str(destination),
            '-fo='+str(destination/(name+'.obj')),source)
    for name,source in (('ui','bios/ui.asm'),('disk','bios/disk.asm'),('probe','bios/rescue.asm'),('abi','runtime/abi.asm'),('arith','runtime/arith.asm'),('end','runtime/end.asm')):
        obj=destination/(name+'.obj');run(nasm,'-Werror','-f','obj','-I','./',source,'-o',obj);objects.append(obj)
    run(nasm,'-Werror','-f','obj','-I','./','bios/floppy.asm','-o',destination/'floppy.obj')
    run(nasm,'-Werror','-f','obj','-I','./','-DRB_RESERVATION_WRITE=1','bios/floppy.asm','-o',destination/'fixture-write.obj')
    artifacts={};memory={}
    def remember(path):artifacts[path.name]=dict(bytes=path.stat().st_size,sha256=sha256(path))
    def floppy(name,payload):
        boot=destination/(name+'-boot.bin');run(nasm,'-Werror','-f','bin','-I','./','-DRB_RESCUE_BYTES='+str(len(payload)),
            '-DRB_RESCUE_CRC='+str(zlib.crc32(payload)),'boot/rescue.asm','-o',boot)
        image=destination/(name+'.img');image.write_bytes(make_image(boot.read_bytes(),payload));remember(boot);remember(image)
    for name,defines in (('retroboot-rescue',[]),('rescue-bss-fault',['-DRB_RESCUE_BAD_BSS=1']),
            ('rescue-model',['-DRB_RESCUE_MODEL=1']),('backup-model',['-DRB_RESCUE_BACKUP_MODEL=1']),
            ('backup-encode-model',['-DRB_RESCUE_ENCODE_MODEL=1']),
            ('backup-stream-model',['-DRB_RESCUE_STREAM_MODEL=1']),
            ('backup-live-model',['-DRB_RESCUE_LIVE_MODEL=1']),
            ('mbr-provenance-model',['-DRB_RESCUE_PROVENANCE_MODEL=1']),
            ('mbr-restart',['-DRB_RESCUE_RESTART=1']),
            ('mbr-reserve',['-DRB_RESCUE_RESERVE=1']),
            ('backup-records-model',['-DRB_RESCUE_RECORD_MODEL=1']),
            ('backup-boot-model',['-DRB_RESCUE_BOOT_MODEL=1']),
            ('backup-target-model',['-DRB_RESCUE_TARGET_MODEL=1']),
            ('backup-plan-model',['-DRB_RESCUE_PLAN_MODEL=1']),
            ('backup-payload-model',['-DRB_RESCUE_PAYLOAD_MODEL=1']),
            ('rescue-file-model',['-DRB_RESCUE_FILE_MODEL=1'])):
        obj,binary,mapfile=(destination/(name+suffix) for suffix in ('.obj','.bin','.map'))
        run(nasm,'-Werror','-f','obj','-I','./',*defines,'core/rescue_start.asm','-o',obj)
        extra=[destination/'model.obj'] if name=='rescue-model' else [destination/'backup.obj',destination/'backup-tests.obj'] if name=='backup-model' else []
        if name=='backup-encode-model':
            extra=[destination/(n+'.obj') for n in ('backup','backup-encode','backup-encode-tests')]
        if name=='backup-stream-model':
            extra=[destination/(n+'.obj') for n in ('backup-stream','backup-stream-tests',
                'backup-encode','backup-format','fingerprint')]
        if name=='backup-records-model':
            extra=[destination/(n+'.obj') for n in ('backup','backup-records','backup-links','saved-state','saved-record-io','saved-volume','backup-record-tests')]
        if name=='backup-boot-model':
            extra=[destination/(n+'.obj') for n in ('backup','backup-records','backup-links','saved-state','saved-record-io','saved-volume','backup-boot','fat-boot','backup-boot-tests')]
        if name=='rescue-file-model':
            extra=[destination/(n+'.obj') for n in ('rescue-file','rescue-file-tests')]
        if name=='backup-target-model':
            extra=[destination/(n+'.obj') for n in ('backup-target','backup-links','backup-target-tests','target-audit',
                'saved-state','saved-record-io','saved-volume')]
        if name in ('backup-plan-model','backup-payload-model'):
            test_object='backup-payload-tests' if name=='backup-payload-model' else 'backup-plan-tests'
            extra=[destination/(n+'.obj') for n in ('backup-plan',test_object,'backup-target','backup-links','fat-boot',
                'target-audit','saved-state','saved-record-io','saved-volume')]
        if name=='mbr-provenance-model':
            extra=[destination/(n+'.obj') for n in ('mbr-provenance','mbr-provenance-tests')]
        if name=='mbr-restart':
            extra=[destination/(n+'.obj') for n in ('mbr-restart-core','mbr-restart-tests','floppy')]
        if name=='mbr-reserve':
            extra=[destination/(n+'.obj') for n in ('mbr-restart-core','mbr-reservation-core',
                'mbr-reservation-tests','floppy','fixture-write')]
        if name=='backup-live-model':
            extra=[destination/(n+'.obj') for n in ('backup-live','backup-live-tests','backup-stream','backup-encode',
                'backup-plan','backup-target','backup-links','fat-boot','target-audit','saved-state','saved-record-io','saved-volume')]
        if name in ('retroboot-rescue','rescue-bss-fault'):
            extra=[destination/(n+'.obj') for n in ('rescue-ui','rescue-file','rescue-backup','floppy',
                'backup','backup-records','backup-links','saved-state','saved-record-io','saved-volume','backup-boot','backup-target','target-audit',
                'backup-plan','rescue-plan','fat-boot','backup-live','backup-stream','backup-encode')]
        if destination/'backup.obj' in extra or destination/'backup-plan.obj' in extra:
            extra.append(destination/'backup-format.obj')
        if destination/'backup-target.obj' in extra:
            extra.append(destination/'fingerprint.obj')
        linked=[obj,*objects[:-1],*extra,objects[-1]]
        run(wlink,'@core/stage2.wlink','name',binary,'option','map='+str(mapfile),'file',','.join(map(str,linked)))
        data=seal_payload(binary.read_bytes());binary.write_bytes(data);header=inspect_payload(data)
        symbols={n:int(a,16) for a,n in re.findall(r'^([0-9a-fA-F]{8})[+*]?\s+(\w+)\s*$',mapfile.read_text(),re.MULTILINE)}
        symbols={n:symbols[n] for n in ('rb_entry','rb_file_end','rb_bss_begin','rb_bss_end','_rb_rescue_initialized','_rb_rescue_bss')}
        if (symbols['rb_entry']!=32 or symbols['rb_file_end']!=len(data)
                or symbols['rb_bss_begin']!=header['bss_begin'] or symbols['rb_bss_end']!=header['bss_end']
                or not 32<=symbols['_rb_rescue_initialized']<=len(data)-2
                or not header['bss_begin']<=symbols['_rb_rescue_bss']<=header['bss_end']-32):raise ValueError('Rescue map/header mismatch')
        memory[name]=dict(header=header,segments=inspect_map(mapfile,header),symbols=symbols,
            headroom_bytes=check_headroom(header))
        remember(binary);floppy(name,data)
    restart = destination / 'mbr-restart.img'
    restart.write_bytes(witness_floppy(restart.read_bytes()))
    remember(restart)
    histories = carrier_images()
    reserve = destination / 'mbr-reserve.img'
    reserve.write_bytes(witness_floppy(reserve.read_bytes(), witness_id=RESERVATION_WITNESS,
                                       carrier_id=RESERVATION_CARRIER))
    remember(reserve)
    data_floppy = destination / 'mbr-reserve-data.img'
    data_floppy.write_bytes(carrier_images(RESERVATION_CARRIER)['staged'])
    remember(data_floppy)
    cut_rom = destination / 'int13-reserve.rom'
    run(nasm, '-Werror', '-f', 'bin', '-I', './', '-DRB_RESERVE_INJECT=1',
        'tests/bios/int13_rom.asm', '-o', cut_rom)
    rom = bytearray(cut_rom.read_bytes())
    rom[-1] = -sum(rom) & 255
    cut_rom.write_bytes(rom)
    remember(cut_rom)
    for name in ('current', 'older'):
        carrier = destination / ('mbr-restart-' + name + '.img')
        carrier.write_bytes(histories[name])
        remember(carrier)
    payload=(destination/'retroboot-rescue.bin').read_bytes()
    bad=bytearray(payload);struct.pack_into('<H',bad,memory['retroboot-rescue']['symbols']['_rb_rescue_initialized'],0xDEAD)
    floppy('rescue-data-fault',seal_payload(bad))
    original=(destination/'retroboot-rescue.img').read_bytes()
    for name,offset in (('rescue-crc-fault',PAYLOAD_LBA*512+40),('rescue-header-fault',PAYLOAD_LBA*512+20)):
        bad=bytearray(original);bad[offset]^=1;p=destination/(name+'.img');p.write_bytes(bad);remember(p)
    for name in file_specs():
        p=destination/(name+'.img');p.write_bytes(file_fixture(original,name));remember(p)
    p=destination/'retroboot-rescue-demo.img';p.write_bytes(file_fixture(original,'file-demo'));remember(p)
    for suffix in ('','-chs','-resealed'):
        p=destination/('retroboot-rescue-stream'+suffix+'.img')
        p.write_bytes(put_backup(original,stream_reference(chs=suffix=='-chs',resealed=suffix=='-resealed'))[0]);remember(p)
    for name,spec in match_specs().items():
        p=destination/('match-'+name+'.img');p.write_bytes(match_floppy(original,spec));remember(p)
    for kind in sorted({s['kind'] for s in match_specs().values()}):
        size,extents=match_disk(kind);p=destination/('disk-match-'+kind+'.img');write_fixture(p,size,extents);remember(p)
    for kind in sorted({s['kind'] for s in plan_specs().values()}):
        size,extents=plan_disk(kind);p=destination/('disk-plan-'+kind+'.img');write_fixture(p,size,extents);remember(p)
    size,extents=plan_disk();p=destination/'retroboot-rescue-target-hdd.img';write_fixture(p,size,extents);remember(p)
    size,extents=plan_disk('bad-fsinfo');p=destination/'retroboot-rescue-bad-fsinfo-hdd.img';write_fixture(p,size,extents);remember(p)
    size,extents=plan_disk('bad-reference');p=destination/'retroboot-rescue-bad-reference-hdd.img';write_fixture(p,size,extents);remember(p)
    for name in HDD_CASES:
        size,extents=hdd_fixture(name);p=destination/('disk-'+name+'.img');write_fixture(p,size,extents);remember(p)
    changed_header=destination/'resealed-backup-header.raw';changed_header.write_bytes(match_backup(generation=2)[:512])
    changed_tail=destination/'resealed-original-tail.raw';changed_tail.write_bytes(resealed_original(True))
    tail_image=(destination/'match-resealed-file-tail.img').read_bytes()
    # Original-MBR payload is file sector five. Derive its physical address.
    tail_lba=file_chain(tail_image)[5];cylinder,within=divmod(tail_lba,36);head,sector=divmod(within,18)
    for mode in range(20):
        extra=['-DRB_REPLACEMENT_SECTOR="'+str(changed_header if mode==17 else changed_tail)+'"'] if mode in (17,18) else []
        if mode==18:extra+=['-DRB_SAVED_CX='+str((cylinder<<8)|sector+1),'-DRB_SAVED_DH='+str(head)]
        p=destination/f'int13-{mode}.rom';run(nasm,'-Werror','-f','bin','-DRB_RESCUE_TRACE=1','-DRB_ROM_MODE='+str(mode),*extra,'tests/bios/int13_rom.asm','-o',p)
        data=bytearray(p.read_bytes());data[-1]=-sum(data)&255;p.write_bytes(data);remember(p)
    manifest=dict(format_version=1,purpose='independent-read-only-rescue-diagnosis',ui=metadata(language),toolchain=lock,build_inputs=inputs,
        host_executable_sha256=dict(nasm=sha256(nasm),wcc=sha256(wcc),wlink=sha256(wlink)),memory=memory,artifacts=artifacts,hdd_cases=HDD_CASES)
    example=destination/'synthetic-container.rbb';example.write_bytes(backup_sources()[0]);remember(example)
    manifest['backup_encode_model']=dict(cases=encode_cases(),assertions=encode_assertions(),
        scope='metadata-sector encoding only; explicit payload CRC claims, no source capture or disk writes')
    manifest['backup_stream_model']=dict(cases=stream_cases(),assertions=stream_assertions(),
        scope='provisional container bytes from explicit sources; no live collection, destination durability or disk writes')
    manifest['backup_model']=dict(cases=backup_cases(),assertions=3*len(backup_cases()),
        scope='container-integrity-only; synthetic data, no live media match or restore')
    example=destination/'synthetic-records.rbb';example.write_bytes(record_fixture());remember(example)
    manifest['backup_records_model']=dict(cases=record_cases(),assertions=4*len(record_cases()),
        scope='saved partition/record consistency only; no filesystem completeness, live media match or restore')
    example=destination/'synthetic-boot-areas.rbb';example.write_bytes(boot_fixture());remember(example)
    manifest['backup_file_cases']=file_specs()
    manifest['backup_target_model']=dict(assertions=TARGET_ASSERTIONS,read_lbas=target_reads(),
        scope='two live metadata acquisitions compared with supplied claims; model only, no file import or restore')
    manifest['backup_plan_model']=dict(assertions=plan_assertions(),read_lbas=plan_reads(),
        cases=plan_cases(),scope='preliminary live ranges and complete FAT boot-area checks; no backup file, MBR approval or restore')
    manifest['backup_payload_model']=dict(assertions=payload_assertions(),read_lbas=payload_reads(),
        cases=payload_cases(),scope='validated live ranges and streamed payload CRCs; no retained bytes, MBR approval, export or restore')
    manifest['backup_live_model']=dict(assertions=live_assertions(),read_lbas=live_reads(),cases=live_cases(),
        scope='fresh live extent binding and provisional stream; explicit MBR roles, no BIOS integration, persistence, approval or restore')
    manifest['mbr_provenance_model'] = dict(assertions=PROVENANCE_ASSERTIONS,
        scope='first-install enrollment, explicit review decisions and role readback against synthetic endpoints')
    manifest['rescue_match_cases']=match_specs()
    manifest['rescue_plan_cases']=plan_specs()
    manifest['backup_boot_model']=dict(cases=boot_cases(),assertions=6*len(boot_cases()),
        scope='saved FAT reserved areas and READY VBR consistency; no live media match or restore')
    check_build_inputs(manifest, ROOT)
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(f'Built {destination.name}: FAT12 1440 KiB, payload {len(payload)} bytes; no HDD loader dependency',flush=True)
    return manifest

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--language',choices=LANGUAGES,default='en');p.add_argument('--repeat',action='store_true');a=p.parse_args()
    first=build(language=a.language)
    if a.repeat:
        if first!=build('rescue-repeat',a.language):raise ValueError('Repeated rescue build differs')
        print('Reproducibility: all rescue binaries, images and manifests are identical')
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:print('Rescue build: '+str(error),file=sys.stderr);sys.exit(1)
