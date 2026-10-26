import copy
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
UPDATES = runpy.run_path(str(ROOT / 'system_files/usr/bin/gniri-stage-update'))
REFERENCE = 'ghcr.io/example/gniri:stable'


def host(signature='containerPolicy'):
    image = {'image': REFERENCE, 'transport': 'registry', 'signature': signature}
    return {'spec': {'image': image, 'bootOrder': 'default'},
            'status': {'booted': {'image': {'image': copy.deepcopy(image)}}, 'rollbackQueued': False}}


class UpdateTests(unittest.TestCase):
    def run_update(self, status):
        with patch('subprocess.run') as run:
            UPDATES['stage_update'](REFERENCE, status)
            return run.call_args_list

    def test_normal_update_never_applies_or_reboots(self):
        calls = self.run_update(host())
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args[0], ['bootc', 'upgrade'])

    def test_first_update_enrolls_signature_enforcement(self):
        calls = self.run_update(host('insecure'))
        self.assertEqual(calls[0].args[0], ['bootc', 'switch', '--enforce-container-sigpolicy', REFERENCE])

    def test_queued_rollback_is_not_overridden(self):
        status = host()
        status['spec']['bootOrder'] = 'rollback'
        with patch('subprocess.run') as run, self.assertRaises(UPDATES['UpdateSkipped']):
            UPDATES['stage_update'](REFERENCE, status)
        run.assert_not_called()

    def test_manual_source_change_is_not_overridden(self):
        status = host()
        status['spec']['image']['image'] = 'ghcr.io/other/system:stable'
        with patch('subprocess.run') as run, self.assertRaises(UPDATES['UpdateSkipped']):
            UPDATES['stage_update'](REFERENCE, status)
        run.assert_not_called()

    def test_local_development_does_not_contact_registry(self):
        with patch('subprocess.run') as run, self.assertRaises(UPDATES['UpdateSkipped']):
            UPDATES['stage_update']('localhost/gniri:development', host())
        run.assert_not_called()

    def test_timer_replaces_all_upstream_schedules(self):
        text = (ROOT / 'system_files/usr/lib/systemd/system/bootc-fetch-apply-updates.timer.d/10-gniri.conf').read_text()
        for reset in ('OnBootSec=\n', 'OnCalendar=\n', 'OnUnitInactiveSec=\n'):
            self.assertIn(reset, text)
        self.assertIn('Persistent=true', text)
        self.assertEqual([line for line in text.splitlines() if line.startswith('OnCalendar=') and line != 'OnCalendar='],
                         ['OnCalendar=Sun *-*-* 10:00:00'])
        for name in ('OnBootSec', 'OnUnitInactiveSec'):
            self.assertEqual([line for line in text.splitlines() if line.startswith(name + '=')], [name + '='])
        self.assertIn('RandomizedDelaySec=30min', text)

    def test_scheduled_publication_is_weekly_not_daily(self):
        text = (ROOT / '.github/workflows/build.yml').read_text()
        self.assertIn("cron: '20 6 * * 6'", text)
        self.assertNotIn("cron: '20 6 * * *'", text)

    def test_builds_never_promote_stable(self):
        text = (ROOT / '.github/workflows/build.yml').read_text()
        guard = "github.event_name != 'pull_request' && github.ref == 'refs/heads/main'"
        self.assertEqual(text.count(guard), 4)
        self.assertIn('persist-credentials: false', text)
        self.assertNotRegex(text, r'podman push[^\n]+"\$IMAGE:stable"')
        promotion = (ROOT / '.github/workflows/promote.yml').read_text()
        self.assertIn('environment: stable', promotion)
        self.assertIn('release-gate.py validate', promotion)
        self.assertIn('--preserve-digests', promotion)

    def test_image_metadata_is_after_expensive_package_layers(self):
        text = (ROOT / 'Containerfile').read_text()
        self.assertGreater(text.index('ARG IMAGE_REF='), text.index('bash /run/gniri-build/install-upstream.sh'))
        self.assertIn('ARG SOURCE_URL=""', text)

    def test_service_replaces_dangerous_upstream_command(self):
        text = (ROOT / 'system_files/usr/lib/systemd/system/bootc-fetch-apply-updates.service.d/10-gniri.conf').read_text()
        self.assertIn('ExecStart=\nExecStart=/usr/bin/gniri-stage-update', text)
        self.assertNotIn('--apply', text)

    def test_installer_never_automatically_formats_disks(self):
        text = (ROOT / 'installer/prepare.sh').read_text()
        # Ignore comments explaining the omission.
        active = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#'))
        for token in ('clearpart --all', 'zerombr', 'autopart --', '--non-interactive', 'selinux=0'):
            self.assertNotIn(token, active)
