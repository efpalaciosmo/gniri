#!/usr/bin/env python3
"""Record the exact inputs associated with the ISO, never a readiness claim."""
import json
from pathlib import Path
import subprocess
import sys


def main():
    payload, target, base, builder, output = sys.argv[1:]
    inspection = json.loads(subprocess.check_output(['podman', 'image', 'inspect', payload]))[0]
    labels = inspection['Config']['Labels']
    installer = json.loads(subprocess.check_output([
        'podman', 'image', 'inspect', 'localhost/gniri-installer:latest']))[0]
    revision = subprocess.check_output([
        'git', '-c', f'safe.directory={Path.cwd()}', 'describe', '--always', '--dirty', '--abbrev=40'],
        text=True).strip()
    record = {'payload_reference': payload, 'payload_image_id': inspection['Id'],
              'update_reference': target, 'base_image': base, 'builder': builder,
              'source_revision': labels.get('org.opencontainers.image.revision'),
              'installer_source_revision': revision, 'installer_image_id': installer['Id'],
              'validation': 'UNTESTED: complete docs/testing.md for this exact artifact'}
    Path(output).write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    main()
