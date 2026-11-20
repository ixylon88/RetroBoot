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
        'B_SCOPE','B_LIMIT','B_MISSING','B_IO','B_FILE_BAD','B_BAD','B_OK','B_CODES','B_NESTED','B_COUNTS','B_SECTORS','B_READY','B_FILE_LBA','B_DISK_LBA','B_EXTENT','B_HELP','B_BOUNDARY',
        'T_SCOPE','T_LIMIT','T_OK','T_CAPACITY','T_GEOMETRY','T_IDENTITY','T_LAYOUT','T_CHANGED','T_BAD',
        'T_CODES','T_MEDIA','T_CRC','T_ADMIN','T_ROUTE','T_GENERATIONS','T_LBA','T_HELP','T_BOUNDARY',
        'P_SCOPE','P_LIMIT','P_OK','P_BAD','P_CODES','P_ERROR','P_COUNTS','P_SECTORS',
        'P_TABLE','P_PAGE','P_HELP','P_BOUNDARY','P_MBR','P_BOOT',
        'S_SCOPE','S_LIMIT','S_OK','S_BAD','S_COUNT','S_HELP','S_REPROBE','S_DIFFER',
        'A_MENU','A_DATA','A_BACK','A_SAVE_DATA','A_SAVE_BACK','A_DIFF','A_NEXT','A_DECIDE','A_YES','A_TARGET','A_CARRIER','A_SECTORS',
        'D_MODEL','D_SERIAL','D_PROFILE','D_EXPECT','D_LIVE','D_ABSENT','D_WRONG','D_ACTION','D_INSERT','D_CANCEL','D_CAPTURE_FAIL')
WIDTHS = dict.fromkeys(KEYS,74)
WIDTHS.update(dict.fromkeys(KEYS[12:22],28));WIDTHS.update(TITLE=60,READ_ONLY=13)

WIDTHS.update(dict.fromkeys(('B_CODES','B_NESTED','B_COUNTS','B_SECTORS','B_READY','B_FILE_LBA','B_DISK_LBA','B_EXTENT'),28))
WIDTHS.update(dict.fromkeys(('T_CODES','T_MEDIA','T_CRC','T_ADMIN','T_ROUTE','T_GENERATIONS','T_LBA'),28))

WIDTHS['T_MEDIA'] = 24
WIDTHS.update(dict.fromkeys(('P_CODES','P_ERROR','P_COUNTS','P_SECTORS','P_PAGE'),28))
WIDTHS.update(P_MBR=19,P_BOOT=19,S_COUNT=28)

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
