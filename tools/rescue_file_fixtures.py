"""Owned FAT12 backup-file fixtures and independent physical-read expectations."""
import struct

try:
    from .backup_boot_vectors import fixture, cases as boot_cases, materialize
    from .backup_record_vectors import entries
except ImportError:
    from backup_boot_vectors import fixture, cases as boot_cases, materialize
    from backup_record_vectors import entries

ROOT = 19*512


def put_backup(original,data):
    try:
        from .build_rescue import fat12_set
    except ImportError:
        from build_rescue import fat12_set
    if len(original)!=1474560 or len(data)%512 or not 5<=len(data)//512<=2048:
        raise ValueError('Unsupported rescue backup fixture')
    image=bytearray(original)
    payload_size=struct.unpack_from('<I',image,ROOT+32+28)[0]
    occupied=set(range(2,2+(payload_size+511)//512))
    chain=[]
    for cluster in [341,700,340,2848,*range(100,2849)]:
        if cluster not in occupied and cluster not in chain:
            chain.append(cluster)
        if len(chain)==len(data)//512:
            break
    if len(chain)!=len(data)//512:
        raise ValueError('Insufficient free test clusters')
    fat=bytearray(image[512:5120])
    for i,cluster in enumerate(chain):
        fat12_set(fat,cluster,chain[i+1] if i+1<len(chain) else 0xFFF)
        image[(cluster+31)*512:(cluster+32)*512]=data[i*512:(i+1)*512]
    image[512:5120]=fat;image[5120:9728]=fat
    image[ROOT+64:ROOT+76]=b'RBBACKUPRBB\x20'
    struct.pack_into('<HI',image,ROOT+90,chain[0],len(data))
    return image,chain


def specifications():
    cases={name:dict(file=status,check=0,detail=0,nested=0,file_lba=lba)
        for name,status,lba in (
            ('file-missing',5,0),('file-bpb',2,0),('file-fats',3,10),('file-fat-header',3,1),
            ('file-loop',9,19),('file-crosslink',9,19),('file-short',8,19),('file-long',8,19),
            ('file-free',8,19),('file-bad-cluster',8,19),('file-directory',4,19),
            ('file-high-cluster',4,19),('file-size',7,19),('file-empty',7,19),('file-oversize',7,19),
            ('file-duplicate',6,19),('file-subdirectory',4,19),('file-root-io',1,19))}
    for name in ('file-demo','file-large','file-late-root','file-lfn','file-retry','file-demo-hdd'):
        cases[name]=dict(file=0,check=0,detail=0,nested=0,file_lba=0,reserved=131 if name=='file-large' else 33)
    cases['file-container-crc']=dict(file=0,check=1,detail=1,nested=3,file_lba=0)
    cases['file-fsinfo']=dict(file=0,check=7,detail=1,nested=0,file_lba=0,disk_lba=131073,kind=4,index=1)
    cases['file-last-root']=dict(file=0,check=0,detail=0,nested=0,file_lba=0,reserved=33)
    return cases


def make_fixture(original,name):
    try:
        from .build_rescue import fat12_set
    except ImportError:
        from build_rescue import fat12_set
    if name not in specifications():
        raise ValueError('Unknown file fixture')
    if name=='file-missing':
        return original
    data=fixture(reserved=130) if name=='file-large' else fixture()
    if name=='file-fsinfo':
        data=materialize(next(c for c in boot_cases() if c['name']=='primary-fsinfo-lead'))
    image,chain=put_backup(original,data)
    fat=bytearray(image[512:5120])
    if name=='file-bpb':image[13]=2
    elif name=='file-fats':image[5120+300]^=1
    elif name=='file-fat-header':fat[0]=0xF8
    elif name=='file-loop':fat12_set(fat,chain[0],chain[0])
    elif name=='file-crosslink':struct.pack_into('<H',image,ROOT+90,2)
    elif name=='file-short':fat12_set(fat,chain[0],0xFFF)
    elif name=='file-long':fat12_set(fat,chain[-1],500)
    elif name=='file-free':fat12_set(fat,chain[0],0)
    elif name=='file-bad-cluster':fat12_set(fat,chain[0],0xFF7)
    elif name=='file-directory':image[ROOT+75]=0x10
    elif name=='file-high-cluster':struct.pack_into('<H',image,ROOT+84,1)
    elif name in ('file-size','file-empty','file-oversize'):
        struct.pack_into('<I',image,ROOT+92,{'file-size':len(data)-1,'file-empty':0,'file-oversize':1049088}[name])
    elif name=='file-duplicate':image[ROOT+96:ROOT+128]=image[ROOT+64:ROOT+96]
    elif name=='file-subdirectory':image[ROOT+96:ROOT+108]=b'SUBDIR     \x10'
    elif name in ('file-late-root','file-last-root','file-lfn'):
        target=bytes(image[ROOT+64:ROOT+96]);slot=223 if name=='file-last-root' else 17 if name=='file-late-root' else 4
        for i in range(2,slot):image[ROOT+i*32]=0xE5
        image[ROOT+slot*32:ROOT+(slot+1)*32]=target
        if name=='file-lfn':image[ROOT+96:ROOT+108]=b'ALONGNAME  \x0f'
    elif name=='file-container-crc':image[(chain[0]+31)*512+508]^=1
    if name!='file-fats':image[512:5120]=fat;image[5120:9728]=fat
    return bytes(image)


def file_chain(image):
    """Host-only decoding from raw bytes, independent of the native map."""
    for at in range(ROOT,33*512,32):
        if image[at:at+11]==b'RBBACKUPRBB' and image[at+11]!=0x0F:
            cluster=struct.unpack_from('<H',image,at+26)[0]
            count=struct.unpack_from('<I',image,at+28)[0]//512
            break
    else:return []
    chain=[];fat=image[512:5120]
    for _ in range(count):
        if not 2<=cluster<=2848 or cluster in chain:raise ValueError('Invalid fixture chain')
        chain.append(cluster)
        pair=int.from_bytes(fat[cluster*3//2:cluster*3//2+2],'little')
        cluster=(pair>>4 if cluster&1 else pair)&0xFFF
    if cluster<0xFF8:raise ValueError('Overlong fixture chain')
    return [c+31 for c in chain]


def expected_file_reads(image,name,attempt=0):
    spec=specifications()[name]
    if spec['file']:
        if name=='file-bpb':return [0]
        if name=='file-fats':return list(range(11))
        if name=='file-fat-header':return list(range(19))
        if name=='file-missing':return list(range(33))
        if name=='file-root-io':return list(range(19))+[19]*3
        return list(range(20))
    mapping=file_chain(image)
    data=b''.join(image[lba*512:(lba+1)*512] for lba in mapping)
    reads=list(range(33))
    if name=='file-retry' and not attempt:reads.insert(19,19)
    if name=='file-container-crc':return reads+[mapping[0]]
    reads+=mapping
    table=entries(data)
    reads += [mapping[e[4]] for e in table if e[0] in (2,3,5,6,7,8)]
    for owner in (131072,126):
        for e in sorted((e for e in table if e[0]==4 and e[6]==owner),key=lambda e:e[2]):
            for offset in range(e[3]):
                reads.append(mapping[e[4]+offset])
                if name=='file-fsinfo' and owner==131072 and offset==1:return reads
    return reads+list(range(33))
