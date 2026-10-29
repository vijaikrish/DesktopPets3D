"""Copy the project into a clean folder that can be uploaded to GitHub (no caches, review output, builds or venvs).

    python tools/export_repo.py <destination>  [--force]

Only the listed top-level entries are copied; inside them __pycache__, *.pyc, _probe_data and build output are skipped.
The destination must not exist (or be an earlier export, with --force: files are updated in place, files that no
longer exist in the project are removed, its .git, .venv and release/ folders are kept).
"""
import fnmatch
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INCLUDE = ['app', 'web', 'pets', 'docs', 'tests', 'tools', 'packaging', 'licenses', '.github',
           'README.md', 'CHANGELOG.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'requirements.txt',
           'requirements-build.txt', '.gitignore', '.gitattributes',
           'run.bat', 'run_debug.bat', 'setup_windows.bat', 'setup.sh', 'run.sh', 'run_mac.command']
SKIP = ['__pycache__', '*.pyc', '_probe_data', 'build_icons', '.DS_Store', 'Thumbs.db', '*.bak']
KEEP_IN_DEST = {'.git', 'release', '.venv'}


def _ignore(_dir, names):
    return [n for n in names if any(fnmatch.fnmatch(n, pat) for pat in SKIP)]


def _source_files():
    """Relative paths of every file that belongs in the export."""
    out = set()
    for name in INCLUDE:
        src = os.path.join(ROOT, name)
        if os.path.isfile(src):
            out.add(name)
        elif os.path.isdir(src):
            for d, dirs, files in os.walk(src):
                dirs[:] = [x for x in dirs if not any(fnmatch.fnmatch(x, pat) for pat in SKIP)]
                for f in files:
                    if not any(fnmatch.fnmatch(f, pat) for pat in SKIP):
                        out.add(os.path.relpath(os.path.join(d, f), ROOT))
        else:
            print('missing (skipped):', name)
    return out


def export(dest, force=False):
    """Copy file by file (updates in place: cloud-synced folders such as OneDrive refuse to delete busy folders)."""
    dest = os.path.abspath(dest)
    if os.path.commonpath([dest, ROOT]) == ROOT:
        raise SystemExit('destination must be outside the project')
    if os.path.exists(dest) and not force:
        raise SystemExit(f'{dest} exists (use --force to refresh an earlier export)')
    wanted = _source_files()
    for rel in sorted(wanted):
        dst = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel), dst)
    stale = 0
    for d, dirs, files in os.walk(dest, topdown=True):
        if d == dest:
            dirs[:] = [x for x in dirs if x not in KEEP_IN_DEST]
            files = [f for f in files if f not in KEEP_IN_DEST]
        for f in files:
            rel = os.path.relpath(os.path.join(d, f), dest)
            if rel not in wanted:
                try:
                    os.remove(os.path.join(d, f))
                    stale += 1
                except OSError as e:
                    print('could not remove', rel, e)
    for d, dirs, files in os.walk(dest, topdown=False):         # empty folders left by removed files
        top = os.path.relpath(d, dest).split(os.sep)[0]
        if d != dest and top not in KEEP_IN_DEST and not os.listdir(d):
            try:
                os.rmdir(d)
            except OSError:
                pass
    print(f'exported {len(wanted)} files to {dest} ({stale} stale files removed)')
    return dest


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        raise SystemExit(__doc__)
    export(args[0], force='--force' in sys.argv)
