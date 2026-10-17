"""Build/check a package inventory; sync only managed files with mandatory backup."""

import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import shutil
import sys


ROOT_FILES = ('SKILL.md', 'README.md', 'LICENSE', 'CHANGELOG.md', 'SECURITY.md', 'DESIGN.md', 'VERSION')
DIRECTORIES = ('references', 'assets', 'examples', 'evals', 'templates', 'scripts', 'tests')
MANIFEST = 'package-manifest.json'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def ensure(condition, message):
    if not condition:
        raise ValueError(message)


def inside(root, name):
    ensure(isinstance(name, str) and name and '\\' not in name
           and not Path(name).is_absolute() and not PureWindowsPath(name).drive, 'invalid package path')
    path = root / name
    ensure(path.resolve().is_relative_to(root) and path.resolve() != root, 'package path escape')
    ensure(not any(p.is_symlink() or p.is_junction() for p in [path, *path.parents] if p != root.parent),
           'linked package paths are not supported; use a regular copy')
    return path


def inventory(root):
    paths = [root / name for name in ROOT_FILES if (root / name).is_file()]
    for directory in DIRECTORIES:
        for path in (root / directory).rglob('*'):
            if '__pycache__' in path.parts or path.suffix == '.pyc':
                continue
            inside(root, path.relative_to(root).as_posix())
            if path.is_file():
                paths.append(path)
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(paths)}


def build(root):
    root = Path(root).resolve()
    doc = {'name': 'ip-diagram-creator', 'version': (root / 'VERSION').read_text().strip(),
           'files': inventory(root)}
    ensure('SKILL.md' in doc['files'], 'missing SKILL.md')
    (root / MANIFEST).write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8', newline='\n')
    return doc


def verified(root):
    doc = json.loads((root / MANIFEST).read_text(encoding='utf-8'))
    ensure(doc.get('name') == 'ip-diagram-creator' and isinstance(doc.get('files'), dict), 'invalid manifest')
    ensure('SKILL.md' in doc['files'] and 'VERSION' in doc['files'], 'incomplete manifest')
    for name, expected in doc['files'].items():
        path = inside(root, name)
        ensure(path.is_file() and digest(path) == expected, f'package hash mismatch: {name}')
    ensure(inventory(root) == doc['files'], 'unlisted package files; rebuild manifest')
    ensure(doc.get('version') == (root / 'VERSION').read_text().strip(), 'version mismatch')
    return doc


def synchronize(source, target, backup=None):
    source, target = Path(source).resolve(), Path(target).absolute()
    ensure(not source.is_relative_to(target.resolve()) and not target.resolve().is_relative_to(source), 'source/target overlap')
    ensure(not target.is_symlink() and not target.is_junction(), 'linked target is not supported')
    target = target.resolve()
    doc = verified(source)
    names = [*doc['files'], MANIFEST]
    changed = []
    for name in names:
        dest = inside(target, name)
        ensure(not dest.exists() or dest.is_file(), f'destination is not a file: {name}')
        if not dest.is_file() or digest(dest) != digest(source / name):
            changed.append(name)
    extra = sorted(p.relative_to(target).as_posix() for p in target.rglob('*')
                   if p.is_file() and p.relative_to(target).as_posix() not in names
                   and '__pycache__' not in p.parts)
    result = {'version': doc['version'], 'changed': changed, 'extra': extra, 'applied': False}
    if backup is None or not changed:
        return result
    backup = Path(backup).absolute()
    ensure(not backup.exists() and not backup.is_symlink(), 'backup must be a new path')
    backup = backup.resolve()
    ensure(not any(backup.is_relative_to(p) or p.is_relative_to(backup) for p in (source, target)), 'backup overlap')
    backup.mkdir(parents=True)
    # Finish backing up every replaced file before writing any managed target file.
    for name in changed:
        old = target / name
        if old.is_file():
            saved = backup / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old, saved)
    (backup / 'sync-receipt.json').write_text(json.dumps({
        'target': str(target), 'source': str(source), 'changed': changed,
        'new_files': [n for n in changed if not (target / n).exists()]}, indent=2), encoding='utf-8')
    for name in changed:
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, dest)
        ensure(digest(dest) == digest(source / name), f'copy hash mismatch: {name}')
    result['applied'] = True
    result['backup'] = str(backup)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--build', action='store_true', help='Regenerate inventory after intentional source edits')
    parser.add_argument('--target', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    try:
        ensure(not args.apply or (args.target and args.backup), '--apply requires --target and --backup')
        ensure(not args.build or not args.target, 'build and sync must be separate operations')
        if args.build:
            result = build(args.source)
            print(json.dumps({'version': result['version'], 'files': len(result['files'])}))
        elif args.target:
            result = synchronize(args.source, args.target, args.backup if args.apply else None)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0 if args.apply or not result['changed'] else 1
        else:
            result = verified(args.source.resolve())
            print(json.dumps({'version': result['version'], 'verified_files': len(result['files'])}))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'INVALID: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
