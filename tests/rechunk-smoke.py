#!/usr/bin/env python3
"""Compare images, allowing Chunkah's immutable root and /usr deduplication."""
import hashlib
import os
from pathlib import Path
import stat
import sys


def inventory(root):
    records = {}
    hardlinks = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        if Path(directory) == root / 'sysroot':
            dirs[:] = []
            continue
        paths = [Path(directory, name) for name in dirs + files]
        if Path(directory) == root:
            paths.append(root)
        for path in paths:
            info = path.lstat()
            relative = str(path.relative_to(root))
            data = None
            if stat.S_ISREG(info.st_mode):
                with path.open('rb') as stream:
                    data = hashlib.file_digest(stream, 'sha256').hexdigest()
                if info.st_nlink > 1:
                    hardlinks.setdefault((info.st_dev, info.st_ino), []).append(relative)
            elif path.is_symlink():
                data = os.readlink(path)
            attributes = {name: os.getxattr(path, name, follow_symlinks=False).hex()
                          for name in os.listxattr(path, follow_symlinks=False)
                          if not name.startswith(('user.overlay.', 'trusted.overlay.'))}
            records[relative] = (info.st_mode, info.st_uid, info.st_gid, info.st_rdev,
                                 data, attributes)
    groups = {name: frozenset(names) for names in hardlinks.values() if len(names) > 1
              for name in names}
    return records, groups


def compare_trees(source, target):
    (before, old_links), (after, new_links) = inventory(source), inventory(target)
    assert before.keys() == after.keys(), (before.keys() - after.keys(), after.keys() - before.keys())
    # Imported OCI roots may be 0555 instead of 0755. All other mode bits, root
    # ownership and xattrs must match; bootc deploys the root read-only either way.
    if before['.'][0] == stat.S_IFDIR | 0o755 and after['.'][0] == stat.S_IFDIR | 0o555:
        after['.'] = (before['.'][0], *after['.'][1:])
    differences = [name for name in before if before[name] != after[name]]
    assert not differences, f'Changed content, mode, ownership or xattrs: {differences[:30]}'
    # Splitting old aliases is safe (bootc copies mutable /etc at deployment).
    # Adding aliases between unrelated mutable files could couple later edits.
    for name, group in new_links.items():
        if not all(path.startswith('usr/') for path in group):
            assert group <= old_links.get(name, {name}), f'New hardlinks outside immutable /usr: {name}'
    return len(before)


if __name__ == '__main__':
    count = compare_trees(*map(Path, sys.argv[1:]))
    print(f'{count} paths match: data, modes, owners, symlinks and xattrs; '
          'read-only root mode and immutable /usr hardlink deduplication accepted.')
