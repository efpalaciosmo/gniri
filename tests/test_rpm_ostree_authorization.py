import json
from pathlib import Path
import shutil
import runpy
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
RULE = ROOT / 'system_files/usr/share/polkit-1/rules.d/10-gniri-rpm-ostree.rules'
CONFIGURE = runpy.run_path(str(ROOT / 'build/configure-rpm-ostree.py'))['configure_policy']


class RpmOstreeActionTests(unittest.TestCase):
    def test_bootc_missing_actions_are_registered_with_authentication_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vendor = root / 'vendor.policy'
            original = '<policyconfig><action id="org.projectatomic.rpmostree1.upgrade"/></policyconfig>'
            vendor.write_text(original)
            CONFIGURE(root)
            generated = root / 'org.gniri.rpmostree1.policy'
            actions = {a.attrib['id']: a for a in ET.parse(generated).iter('action')}
            self.assertNotIn('org.projectatomic.rpmostree1.upgrade', actions)
            for name in ('rebase', 'rollback', 'repo-refresh'):
                action = actions['org.projectatomic.rpmostree1.' + name]
                self.assertEqual(action.findtext('defaults/allow_any'), 'auth_admin')
                self.assertEqual(action.findtext('defaults/allow_inactive'), 'auth_admin')
                self.assertEqual(action.findtext('defaults/allow_active'), 'auth_admin_keep')
            before = generated.read_bytes()
            CONFIGURE(root)
            self.assertEqual(generated.read_bytes(), before)
            self.assertEqual(vendor.read_text(), original)


@unittest.skipUnless(shutil.which('node'), 'Executing polkit JavaScript requires Node.js')
class RpmOstreeAuthorizationTests(unittest.TestCase):
    def evaluate(self, cases):
        runner = '''
const fs = require('fs');
const vm = require('vm');
let rule;
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {
    polkit: {Result: {YES: 'yes'}, addRule: fn => { rule = fn; }}
});
const cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify(cases.map(c => rule({id: c.action}, {
    active: c.active, local: c.local, isInGroup: group => c.groups.includes(group)
}) ?? null)));
'''
        result = subprocess.run(['node', '-e', runner, str(RULE), json.dumps(cases)],
                                text=True, capture_output=True, check=True)
        return json.loads(result.stdout)

    def case(self, action, active=True, local=True, groups=('wheel',)):
        return dict(action=action, active=active, local=local, groups=groups)

    def test_local_active_administrators_can_manage_rpm_ostree(self):
        cases = [self.case('org.projectatomic.rpmostree1.' + action)
                 for action in ('client-management', 'upgrade', 'rebase', 'rollback',
                                'repo-refresh', 'install-uninstall-packages')]
        self.assertEqual(self.evaluate(cases), ['yes'] * len(cases))

    def test_other_users_sessions_and_actions_keep_the_default_policy(self):
        action = 'org.projectatomic.rpmostree1.rebase'
        cases = [self.case(action, groups=()), self.case(action, active=False),
                 self.case(action, local=False),
                 self.case('org.freedesktop.systemd1.manage-units'),
                 self.case('org.libvirt.unix.manage'),
                 self.case('org.projectatomic.rpmostree1.future-privileged-action'),
                 self.case(action + '.unexpected')]
        self.assertEqual(self.evaluate(cases), [None] * len(cases))
