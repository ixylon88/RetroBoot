"""Independent rescue catalog; reuse the existing exact CP437 C encoding."""
import hashlib
import json

try:
    from .ui_text import ROOT, LANGUAGES, c_literal, unique_keys
except ImportError:
    from ui_text import ROOT, LANGUAGES, c_literal, unique_keys

KEYS = ('TITLE','READ_ONLY','SCOPE','LIMIT','READY','OK','BAD_LAYOUT','NO_DISK',
        'PARAMS','GEOMETRY','IO','CHANGED','CODES','DRIVES','ROUTE','CAPACITY',
        'GEOMETRY_LABEL','DISK_ID','CRC','SIGNATURE','COUNTS','LBA','HELP','IDENTITY',
        'B_SCOPE','B_LIMIT','B_MISSING','B_IO','B_FILE_BAD','B_BAD','B_OK','B_CODES','B_NESTED','B_COUNTS','B_SECTORS','B_READY','B_FILE_LBA','B_DISK_LBA','B_EXTENT','B_HELP','B_BOUNDARY')
WIDTHS = dict.fromkeys(KEYS,74)
WIDTHS.update(dict.fromkeys(KEYS[12:22],28));WIDTHS.update(TITLE=60,READ_ONLY=13)

WIDTHS.update(dict.fromkeys(('B_CODES','B_NESTED','B_COUNTS','B_SECTORS','B_READY','B_FILE_LBA','B_DISK_LBA','B_EXTENT'),28))

def catalog_path(language):
    if language not in LANGUAGES:raise ValueError('Unsupported rescue language')
    return ROOT/'ui/rescue'/(language+'.json')

def validate(strings):
    if not isinstance(strings,dict) or set(strings)!=set(KEYS):raise ValueError('Unexpected rescue text keys')
    for key,value in strings.items():
        if not isinstance(value,str) or not value or any(ord(c)<32 or ord(c)==127 for c in value):
            raise ValueError('Invalid rescue text: '+key)
        try:data=value.encode('cp437')
        except UnicodeEncodeError as error:raise ValueError('Not CP437: '+key) from error
        if len(data)>WIDTHS[key]:raise ValueError('Rescue text exceeds field: '+key)
    return strings

def load_catalog(language):
    return validate(json.loads(catalog_path(language).read_text(encoding='utf-8'),object_pairs_hook=unique_keys))

def render_header(language):
    strings=load_catalog(language)
    return ('/* Generated rescue catalog; CP437 bytes. */\n#define RB_RS_LANGUAGE "'+language+'"\n'
            +'\n'.join('#define RB_RS_'+key+' '+c_literal(strings[key]) for key in KEYS)+'\n')

def metadata(language):
    return dict(language=language,encoding='cp437',catalog_sha256=hashlib.sha256(catalog_path(language).read_bytes()).hexdigest())

def output_name(kind,language):
    if kind not in ('rescue','rescue-repeat','rescue-test') or language not in LANGUAGES:raise ValueError('Unknown rescue output')
    return kind if language=='en' else kind+'-'+language
