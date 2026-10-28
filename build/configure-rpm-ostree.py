#!/usr/bin/env python3
"""Register desktop actions omitted by the generic bootc package policy."""
from pathlib import Path
import xml.etree.ElementTree as ET

PREFIX = 'org.projectatomic.rpmostree1.'
DESKTOP_ACTIONS = {
    'deploy': 'Update base OS',
    'upgrade': 'Update base OS',
    'rebase': 'Switch to a different base OS',
    'rollback': 'Roll back OS updates',
    'bootconfig': 'Change boot configuration',
    'reload-daemon': 'Reload the rpm-ostree daemon state',
    'cancel': 'Cancel an active transaction',
    'cleanup': 'Clear cache and pending data',
    'repo-refresh': 'Refresh repository metadata',
    'repo-modify': 'Modify repository settings',
}


def configure_policy(directory):
    directory = Path(directory)
    destination = directory / 'org.gniri.rpmostree1.policy'
    registered = set()
    for path in directory.glob('*.policy'):
        if path != destination:
            registered.update(action.attrib['id'] for action in ET.parse(path).iter('action'))
    policy = ET.Element('policyconfig')
    for name, description in DESKTOP_ACTIONS.items():
        if PREFIX + name in registered:
            continue
        action = ET.SubElement(policy, 'action', id=PREFIX + name)
        ET.SubElement(action, 'description').text = description
        ET.SubElement(action, 'message').text = 'Authentication is required to manage the operating system'
        defaults = ET.SubElement(action, 'defaults')
        for key, value in (('allow_any', 'auth_admin'), ('allow_inactive', 'auth_admin'),
                           ('allow_active', 'auth_admin_keep')):
            ET.SubElement(defaults, key).text = value
    ET.indent(policy, space='  ')
    destination.write_text(ET.tostring(policy, encoding='unicode') + '\n')
    destination.chmod(0o644)


if __name__ == '__main__':
    configure_policy('/usr/share/polkit-1/actions')
