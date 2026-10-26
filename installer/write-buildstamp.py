#!/usr/bin/env python3
"""Supply Lorax-compatible installer metadata from the installed Fedora base."""
from datetime import datetime, timezone
import os
from pathlib import Path
import platform


def buildstamp(release, epoch):
    version = release['VERSION_ID']
    if release.get('ID', 'fedora') != 'fedora' or not version.isdecimal():
        raise ValueError(f'Expected a numbered Fedora installer base, got {version}')
    # Missing/unknown maturity never silently turns a development base final.
    final = release.get('RELEASE_TYPE') == 'stable'
    timestamp = datetime.fromtimestamp(epoch, timezone.utc).strftime('%Y%m%d%H%M')
    return (f'[Main]\nProduct=Gniri\nVersion={version}\nIsFinal={final}\n'
            f'UUID={timestamp}.x86_64\n')


if __name__ == '__main__':
    epoch = int(os.environ.get('SOURCE_DATE_EPOCH', datetime.now(timezone.utc).timestamp()))
    Path('/.buildstamp').write_text(buildstamp(platform.freedesktop_os_release(), epoch))
