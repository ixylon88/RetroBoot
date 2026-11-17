"""Bind rescue artifacts and evidence to a content snapshot of project sources."""
import hashlib


SOURCE_DIRECTORIES = ('bios', 'boot', 'core', 'include', 'runtime',
                      'tests', 'tools', 'ui', 'profiles')
SOURCE_SUFFIXES = {'.asm', '.c', '.h', '.inc', '.wlink', '.py', '.json', '.txt'}


def source_hashes(root):
    # Conservative dependency set: shared code and host tools are included.
    # Build outputs, caches and documentation do not invalidate an artifact.
    paths = {path for directory in SOURCE_DIRECTORIES
             for path in (root / directory).rglob('*')
             if path.is_file() and path.suffix in SOURCE_SUFFIXES}
    if (root / 'Makefile').is_file():
        paths.add(root / 'Makefile')
    result = {}
    for path in sorted(paths):
        with path.open('rb') as stream:
            result[path.relative_to(root).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return result


def check_build_inputs(manifest, root):
    current = source_hashes(root)
    if not current or manifest.get('build_inputs') != current:
        raise ValueError('Stale rescue build inputs; rebuild with make rescue-check '
                         'RB_LANGUAGE=<en|de> before testing or packaging')
