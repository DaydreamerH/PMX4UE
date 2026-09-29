"""Package current source bytes (including uncommitted/new files), never local outputs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--exclude-prefix', action='append', default=[],
                        help='Repository-relative directory to omit from this package (repeatable)')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    prefixes = []
    for value in args.exclude_prefix:
        prefix = value.replace('\\', '/').strip('/')
        if not prefix or Path(value).is_absolute() or '..' in prefix.split('/'):
            parser.error('Exclusions must be repository-relative directories')
        prefixes.append(prefix + '/')
    if output.exists() or output.is_relative_to(root):
        parser.error('Use a new ZIP path outside the source repository')
    inventory = subprocess.check_output([
        'git', '-c', f'safe.directory={root.as_posix()}', '-C', str(root),
        'ls-files', '--cached', '--others', '--exclude-standard', '-z'
    ]).decode('utf-8').split('\0')
    excluded, selected = [], []
    for name in sorted(set(filter(None, inventory))):
        path = root/name
        parts = Path(name).parts
        local = (any(name.startswith(prefix) for prefix in prefixes)
                 or any(p in {'.git', '.local', '__pycache__', '.pytest_cache', 'Binaries', 'Intermediate', 'Saved', 'runs'} for p in parts)
                 or path.suffix.lower() in {'.zip', '.pyc', '.log', '.pmx', '.fbx', '.blend', '.uasset', '.umap'}
                 or (parts[0] == 'characters' and path.name in {'character.json', 'local.json'}))
        if local or not path.is_file():
            excluded.append(name)
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise RuntimeError('Source path must be an ordinary file inside repository: ' + name)
        selected.append(name)
    required = {'START_HERE.md', 'pmx4ue.py', 'tools/ue_skeleton_guard.py', 'tools/preview_framing.py',
                'tests/test_shoulder_cleanup.py', 'skills/pmx-to-ue/SKILL.md'}
    if not required <= set(selected):
        raise RuntimeError('Missing required source files: ' + str(required-set(selected)))
    manifest = dict(schema='pmx4ue.source-package.v1', version=(root/'VERSION').read_text().strip(),
                    source='working_tree_including_uncommitted_files', excluded=excluded, files={})
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in selected:
            data = (root/name).read_bytes()
            manifest['files'][name] = hashlib.sha256(data).hexdigest()
            archive.writestr('PMX4UE/'+name, data)
        archive.writestr('PMX4UE/PACKAGE_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(selected)+1
        for name, digest in manifest['files'].items():
            assert hashlib.sha256(archive.read('PMX4UE/'+name)).hexdigest() == digest, name
    print(json.dumps(dict(zip=str(output), files=len(selected), bytes=output.stat().st_size,
                         sha256=hashlib.sha256(output.read_bytes()).hexdigest(), excluded=excluded), ensure_ascii=False))


if __name__ == '__main__':
    main()
