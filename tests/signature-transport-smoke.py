#!/usr/bin/env python3
"""Real Skopeo regression, with ephemeral TLS/auth/signatures and no external network.

Run only as root INSIDE a disposable container: its policy/key/auth configuration
is replaced with test fixtures. No production signing key or GHCR token is used.
"""
import base64
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import runpy
import ssl
import subprocess
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
OCI = 'application/vnd.oci.image.'
AUTH = 'Basic ' + base64.b64encode(b'fixture:local-only').decode()


def encode(value):
    return json.dumps(value, separators=(',', ':')).encode()


def digest(value):
    return 'sha256:' + hashlib.sha256(value).hexdigest()


def run(*command, expected=None, **kwargs):
    result = subprocess.run(command, text=True, capture_output=True, timeout=60, **kwargs)
    output = result.stdout + result.stderr
    if expected is None:
        if result.returncode:
            raise RuntimeError(f'{command} failed ({result.returncode}):\n{output}')
    elif not result.returncode or not re.search(expected, output, re.IGNORECASE):
        raise RuntimeError(f'{command}: expected failure matching {expected!r}:\n{output}')
    print(output, end='', flush=True)
    return result


class Registry(BaseHTTPRequestHandler):
    """Read-only Registry V2 fixture; Skopeo and OpenSSL are NOT mocked."""

    objects = {}
    signature_error = None

    def do_GET(self):
        if self.headers.get('Authorization') != AUTH:
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="signature-fixture"')
            self.end_headers()
            return
        if self.path == '/v2/':
            content, media_type = b'{}', 'application/json'
        elif self.path == '/v2/gniri/tags/list':
            content, media_type = encode({'name': 'gniri', 'tags': []}), 'application/json'
        elif self.path == self.signature_error:
            self.send_response(503)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(encode({'errors': [{'code': 'UNKNOWN', 'message': 'signature service unavailable'}]}))
            return
        elif self.path in self.objects:
            content, media_type = self.objects[self.path]
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(encode({'errors': [{'code': 'MANIFEST_UNKNOWN', 'message': 'missing fixture'}]}))
            return
        self.send_response(200)
        self.send_header('Content-Type', media_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Docker-Content-Digest', digest(content))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(content)

    do_HEAD = do_GET

    def log_message(self, *args):
        pass


def blob(value, media_type):
    content = value if isinstance(value, bytes) else encode(value)
    descriptor = {'mediaType': media_type, 'digest': digest(content), 'size': len(content)}
    Registry.objects[f'/v2/gniri/blobs/{descriptor["digest"]}'] = content, media_type
    return descriptor


def image(kind):
    # A real (empty) tar layer exercises blob transfer, not only manifest parsing.
    tar = b'\0' * 10240
    layer = blob(gzip.compress(tar, mtime=0), OCI + 'layer.v1.tar+gzip')
    config = blob({'architecture': 'amd64', 'os': 'linux', 'config': {'Labels': {'fixture': kind}},
                   'rootfs': {'type': 'layers', 'diff_ids': [digest(tar)]}}, OCI + 'config.v1+json')
    manifest = encode({'schemaVersion': 2, 'mediaType': OCI + 'manifest.v1+json',
                       'config': config, 'layers': [layer]})
    image_digest = digest(manifest)
    Registry.objects[f'/v2/gniri/manifests/{image_digest}'] = manifest, OCI + 'manifest.v1+json'
    return image_digest


def sign(repository, image_digest, key):
    payload = {'critical': {'identity': {'docker-reference': repository},
                            'image': {'docker-manifest-digest': image_digest},
                            'type': 'cosign container image signature'}, 'optional': None}
    signature = subprocess.check_output(['openssl', 'dgst', '-sha256', '-sign', str(key)], input=encode(payload))
    layer = blob(payload, 'application/vnd.dev.cosign.simplesigning.v1+json')
    layer['annotations'] = {'dev.cosignproject.cosign/signature': base64.b64encode(signature).decode()}
    config = blob({}, OCI + 'config.v1+json')
    manifest = encode({'schemaVersion': 2, 'mediaType': OCI + 'manifest.v1+json',
                       'config': config, 'layers': [layer]})
    tag = image_digest.replace(':', '-') + '.sig'
    Registry.objects[f'/v2/gniri/manifests/{tag}'] = manifest, OCI + 'manifest.v1+json'


def check(work, repository):
    authfile = Path('/run/registry-auth.json')
    authfile.write_text(json.dumps({'auths': {repository.split('/')[0]: {'auth': AUTH.split()[1]}}}))
    authfile.chmod(0o600)
    policy_file = Path('/usr/share/gniri/bootc-policy.json')
    policy = runpy.run_path(str(ROOT / 'build/signature-policy.py'))['signature_policies']({}, repository)[1]
    policy_file.parent.mkdir(parents=True, exist_ok=True)
    policy_file.write_text(json.dumps(policy))
    key_dir = Path('/usr/share/gniri/keys')
    key_dir.mkdir(exist_ok=True)
    for name in ('trusted', 'wrong'):
        run('openssl', 'genpkey', '-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:P-256',
            '-out', str(work / f'{name}.key'))
    run('openssl', 'pkey', '-in', str(work / 'trusted.key'), '-pubout', '-out', str(key_dir / 'cosign.pub'))
    good, unsigned, wrong = (image(kind) for kind in ('signed', 'unsigned', 'wrong-key'))
    sign(repository, good, work / 'trusted.key')
    sign(repository, wrong, work / 'wrong.key')
    references = [f'{repository}@{value}' for value in (good, unsigned, wrong)]
    copy = ['skopeo', '--policy', str(policy_file), 'copy', '--authfile', str(authfile)]
    run('skopeo', '--version')
    # Reproduce the exact CI failure, before demonstrating that the fix works.
    run(*copy, f'docker://{references[0]}', f'oci:{work}/before',
        expected='Pushing signatures for OCI images is not supported')
    print('PASS: reproduced the original OCI signature destination failure', flush=True)
    smoke = ['bash', str(ROOT / 'tests/signature-smoke.sh')]
    run(*smoke, *references)
    destination = Path('/var/tmp/signed-policy-test')
    index = json.loads((destination / 'index.json').read_text())
    if index['manifests'][0]['digest'] != good:
        raise RuntimeError('Verified source manifest digest changed during OCI export')
    manifest = json.loads((destination / 'blobs/sha256' / good.split(':')[1]).read_text())
    for descriptor in [manifest['config'], *manifest['layers']]:
        data = (destination / 'blobs/sha256' / descriptor['digest'].split(':')[1]).read_bytes()
        if digest(data) != descriptor['digest']:
            raise RuntimeError('OCI export contains a corrupt blob')
    print('PASS: trusted source copied; unsigned and wrong-key sources rejected', flush=True)
    # A missing image or auth failure must fail the smoke test, not count as a
    # successful negative signature test. These checks use the actual shell script.
    missing = f'{repository}@sha256:' + '0' * 64
    for position in (1, 2):
        broken = references.copy()
        broken[position] = missing
        run(*smoke, *broken, expected='manifest unknown|missing fixture')
    Registry.signature_error = '/v2/gniri/manifests/' + wrong.replace(':', '-') + '.sig'
    try:
        run(*smoke, *references, expected='signature service unavailable|503')
    finally:
        Registry.signature_error = None
    authfile.write_text('{"auths":{}}')
    run(*smoke, *references, expected='authentication required|unauthorized')
    authfile.write_text(json.dumps({'auths': {repository.split('/')[0]: {'auth': AUTH.split()[1]}}}))
    # Prove the test detects a bypassed policy instead of silently going green.
    policy['transports']['docker'][repository] = [{'type': 'insecureAcceptAnything'}]
    policy_file.write_text(json.dumps(policy))
    run(*smoke, *references, expected='ERROR: an unsigned or wrong-key image was accepted')
    print('PASS: missing images, signature-fetch failures, bad auth and a weakened policy cannot make the smoke test pass', flush=True)


def main():
    if os.geteuid() != 0 or not Path('/run/.containerenv').is_file():
        raise SystemExit('Run only as root inside a disposable Podman container; see docs/testing.md.')
    with tempfile.TemporaryDirectory(prefix='gniri-signature-transport-') as temporary:
        work = Path(temporary)
        run('openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256',
            '-nodes', '-days', '1', '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost',
            '-keyout', str(work / 'tls.key'), '-out', str(work / 'tls.crt'))
        with ThreadingHTTPServer(('127.0.0.1', 0), Registry) as server:
            repository = f'localhost:{server.server_port}/gniri'
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(work / 'tls.crt', work / 'tls.key')
            server.socket = context.wrap_socket(server.socket, server_side=True)
            cert_dir = Path('/etc/containers/certs.d') / repository.split('/')[0]
            cert_dir.mkdir(parents=True)
            (cert_dir / 'ca.crt').write_bytes((work / 'tls.crt').read_bytes())
            registries = Path('/etc/containers/registries.d')
            registries.mkdir(parents=True, exist_ok=True)
            (registries / 'signature-fixture.yaml').write_text(f'docker:\n  {repository}:\n    use-sigstore-attachments: true\n')
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                check(work, repository)
            finally:
                server.shutdown()
                thread.join()


if __name__ == '__main__':
    main()
