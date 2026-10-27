import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOCAL = 'localhost/gniri:development'
REMOTE = 'ghcr.io/example/gniri'
DIGEST = 'sha256:' + 'a' * 64


class IsoReferencesTests(unittest.TestCase):
    def validate(self, payload, target):
        return subprocess.run([
            'bash', '-c', 'source "$1"; gniri_validate_iso_refs "$2" "$3"',
            'validate', str(ROOT / 'scripts/iso-common.sh'), payload, target,
        ], capture_output=True, text=True)

    def test_local_image_needs_no_registry_digest_or_key(self):
        self.assertEqual(self.validate(LOCAL, LOCAL).returncode, 0)

    def test_published_payload_is_immutable(self):
        self.assertEqual(self.validate(f'{REMOTE}@{DIGEST}', f'{REMOTE}:stable').returncode, 0)
        self.assertNotEqual(self.validate(f'{REMOTE}:stable', f'{REMOTE}:stable').returncode, 0)

    def test_mixed_local_and_published_sources_are_rejected(self):
        self.assertNotEqual(self.validate(LOCAL, f'{REMOTE}:stable').returncode, 0)
        self.assertNotEqual(self.validate(f'{REMOTE}@{DIGEST}', LOCAL).returncode, 0)

    def test_wrong_repository_is_rejected(self):
        self.assertNotEqual(self.validate(f'{REMOTE}@{DIGEST}', 'ghcr.io/other/gniri:stable').returncode, 0)

    def test_invalid_inputs_are_rejected(self):
        for value in ('', '../image', 'localhost/gniri:other', '$(touch /tmp/never)', 'image\nreboot'):
            with self.subTest(value=value):
                self.assertNotEqual(self.validate(value, value).returncode, 0)

    def test_make_iso_defaults_to_the_local_recipe(self):
        result = subprocess.run(['make', '-n', 'iso'], cwd=ROOT, text=True,
                                capture_output=True, check=True)
        self.assertIn('build IMAGE=localhost/gniri:development', result.stdout)
        self.assertIn('bash scripts/build-local-iso.sh', result.stdout)
        self.assertNotIn('ghcr.io/owner/gniri', result.stdout)

    def test_host_network_is_opt_in_and_reaches_all_build_stages(self):
        result = subprocess.run(['make', '-n', 'iso', 'BUILD_NETWORK=host'], cwd=ROOT,
                                text=True, capture_output=True, check=True)
        self.assertIn('--network "host"', result.stdout)
        self.assertIn('GNIRI_BUILD_NETWORK="host" GNIRI_REFRESH="0" bash scripts/build-local-iso.sh', result.stdout)
        script = (ROOT / 'scripts/build-iso.sh').read_text()
        self.assertIn('network_args=()', script)
        self.assertIn('network_args+=(--network="$3")', script)
        self.assertEqual(script.count('"${network_args[@]}"'), 2)

    def test_published_workflow_still_verifies_signatures(self):
        workflow = (ROOT / '.github/workflows/iso.yml').read_text()
        self.assertIn('cosign verify --new-bundle-format=false --key trust/cosign.pub', workflow)
        self.assertIn('bash scripts/build-iso.sh "$image@$digest" "$image:stable"', workflow)

    def test_legacy_payload_base_is_rejected_with_the_correct_rebuild_instructions(self):
        script = (ROOT / 'scripts/build-iso.sh').read_text()
        guard = 'base=$(' + script.split('base=$(', 1)[1].split('\nfresh_args=()', 1)[0]
        valid = f'quay.io/fedora/fedora-bootc:latest@{DIGEST}'
        for payload in (LOCAL, f'{REMOTE}@{DIGEST}'):
            for base in ('', '<no value>', 'quay.io/fedora/fedora-bootc:latest',
                         f'quay.io/fedora/fedora-bootc:45@{DIGEST}', valid):
                with self.subTest(payload=payload, base=base):
                    result = subprocess.run([
                        'bash', '-eu', '-c',
                        'podman() { printf "%s\\n" "$MOCK_BASE"; };\n' + guard + '\nprintf "%s" "$base"',
                    ], env=dict(os.environ, payload=payload, MOCK_BASE=base), text=True, capture_output=True)
                    if base == valid:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout, valid)
                    else:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn(payload, result.stderr)
                        self.assertIn('lacks a resolved stable base', result.stderr)
                        self.assertIn('make build' if payload == LOCAL else 'signed candidate digest', result.stderr)

    def test_generic_iso_has_required_builder_rootfs_metadata(self):
        script = (ROOT / 'scripts/build-iso.sh').read_text()
        self.assertIn('--bootc-default-fs ext4', script)
        self.assertIn('bootc-generic-iso', script)
        installer = (ROOT / 'installer/prepare.sh').read_text()
        active = '\n'.join(line for line in installer.splitlines()
                           if not line.lstrip().startswith('#'))
        for directive in ('autopart', '--fstype', 'rootflags=', '--bootc-default-fs'):
            self.assertNotIn(directive, active)
        self.assertFalse((ROOT / 'system_files/usr/lib/bootc/install').exists())

    def test_payload_is_streamed_from_an_oci_directory_not_live_ram(self):
        script = (ROOT / 'scripts/build-iso.sh').read_text()
        installer = (ROOT / 'installer/prepare.sh').read_text()
        containerfile = (ROOT / 'installer/Containerfile').read_text()
        self.assertIn('podman save --format oci-dir --output "$payload_dir" "$payload"', script)
        self.assertIn('mktemp -d "$PWD/output/installer-payload.XXXXXX"', script)
        self.assertIn('trap cleanup EXIT', script)
        self.assertIn('rm -rf -- "$payload_dir"', script)
        self.assertIn('--build-context "gniri-payload=$payload_dir"', script)
        self.assertIn('COPY --from=gniri-payload / /usr/share/gniri/installer-payload/', containerfile)
        self.assertIn('skopeo inspect oci:/usr/share/gniri/installer-payload', containerfile)
        self.assertIn('bootc --source-imgref oci:/usr/share/gniri/installer-payload --target-imgref ${target}', installer)
        self.assertNotIn('--source-imgref containers-storage:', installer)
        self.assertNotIn('--bootc-installer-payload-ref', script)
        self.assertNotIn('remount,size=', script + installer)

    def test_selinux_permissive_mode_is_scoped_to_the_installer(self):
        installer = (ROOT / 'installer/prepare.sh').read_text()
        self.assertIn('inst.graphical selinux=1 enforcing=0', installer)
        self.assertIn("grep -qx 'SELINUX=permissive' /etc/selinux/config", installer)
        self.assertIn('\nselinux --enforcing\n', installer)
        active = '\n'.join(line for line in installer.splitlines()
                           if not line.lstrip().startswith('#'))
        self.assertNotIn('selinux=0', active)
        validation = (ROOT / 'build/validate-image.sh').read_text()
        self.assertIn("grep -qx 'SELINUX=enforcing' /etc/selinux/config", validation)
        self.assertIn("intersection(inspection['kargs'])", validation)
        for path in (ROOT / 'system_files').rglob('*'):
            if path.is_file():
                text = path.read_text()
                self.assertNotIn('enforcing=0', text, str(path))
                self.assertNotIn('SELINUX=permissive', text, str(path))


@unittest.skipIf(os.geteuid() == 0, 'Tests the unprivileged-to-rootful orchestration')
class LocalIsoOrchestrationTests(unittest.TestCase):
    """Mock sudo/Podman: never build an ISO, touch system files or require root."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.log = self.directory / 'commands.log'
        podman = self.directory / 'podman'
        podman.write_text('''#!/usr/bin/env bash
set -euo pipefail
printf 'podman %s\\n' "$*" >> "$COMMAND_LOG"
case "$1 ${2:-}" in
    'image exists') exit "${MISSING_IMAGE:-0}" ;;
    'image inspect')
        if [[ ${MOCK_ROOTFUL:-0} == 1 && ${MISMATCH:-0} == 1 ]]; then
            printf 'sha256:different\\n'
        else printf 'sha256:local-image\\n'; fi ;;
    'save --format')
        if [[ ${FAIL_SAVE:-0} == 1 ]]; then exit 9; fi
        printf 'OCI archive' ;;
    'load ') cat > /dev/null ;;
    *) exit 99 ;;
esac
''')
        sudo = self.directory / 'sudo'
        sudo.write_text('''#!/usr/bin/env bash
set -euo pipefail
printf 'sudo %s\\n' "$*" >> "$COMMAND_LOG"
case "$1" in
    -v) exit 0 ;;
    podman) shift; export MOCK_ROOTFUL=1; exec podman "$@" ;;
    bash|chown) exit 0 ;;
    *) exit 99 ;;
esac
''')
        for path in (podman, sudo):
            path.chmod(0o755)

    def run_recipe(self, **variables):
        env = dict(os.environ, PATH=str(self.directory) + os.pathsep + os.environ['PATH'],
                   COMMAND_LOG=str(self.log), **variables)
        result = subprocess.run(['bash', str(ROOT / 'scripts/build-local-iso.sh')],
                                cwd=ROOT, env=env, text=True, capture_output=True)
        return result, self.log.read_text() if self.log.exists() else ''

    def test_streams_the_local_image_to_rootful_storage(self):
        result, log = self.run_recipe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'podman save --format oci-archive {LOCAL}', log)
        self.assertIn('sudo podman load', log)
        self.assertIn(f'sudo bash scripts/build-iso.sh {LOCAL} {LOCAL}', log)
        self.assertNotIn('podman pull', log)
        self.assertNotIn('cosign', log)

    def test_missing_image_stops_before_sudo(self):
        result, log = self.run_recipe(MISSING_IMAGE='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('make build', result.stderr)
        self.assertNotIn('sudo', log)

    def test_host_network_survives_sudo_environment_filtering(self):
        result, log = self.run_recipe(GNIRI_BUILD_NETWORK='host')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'sudo bash scripts/build-iso.sh {LOCAL} {LOCAL} host', log)

    def test_export_failure_never_starts_iso_build(self):
        result, log = self.run_recipe(FAIL_SAVE='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('sudo bash scripts/build-iso.sh', log)

    def test_loaded_image_identity_is_checked(self):
        result, log = self.run_recipe(MISMATCH='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('does not match', result.stderr)
        self.assertNotIn('sudo bash scripts/build-iso.sh', log)
