#!/usr/bin/env python3
"""Repack a Gniri image locally, validate it, then replace its tag."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

CHUNKAH_IMAGE = 'quay.io/coreos/chunkah:v0.6.0@sha256:f812b02f304ac192cdfa722a7043fd775fa03ed48fa047ff8213c1fe1c4637ab'
ROOT = Path(__file__).resolve().parents[1]


def run(*args, capture=False):
    result = subprocess.run(args, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else None


def rechunk(source, destination, work):
    before = json.loads(run('podman', 'image', 'inspect', source, capture=True))[0]
    source_id = before['Id']
    (work / 'config.json').write_text(json.dumps([before]))
    # Fedora's inherited embedded OSTree repo is build metadata, not the deployed
    # rootfs. Remove it and its labels as required by Chunkah's bootc contract.
    # This does not change bootc's installed OSTree + composefs backend.
    run('podman', 'run', '--rm', '--network=none',
        f'--mount=type=image,src={source_id},target=/chunkah',
        '-v', f'{work}:/run/out:Z', CHUNKAH_IMAGE,
        'build', '--rootfs', '/chunkah', '--config', '/run/out/config.json',
        '--prune', '/sysroot/', '--label', 'ostree.commit-',
        '--label', 'ostree.final-diffid-', '--max-layers', '128',
        '--compressed', '--threads', '4', '--output', 'oci:/run/out/image')
    image_id = run('podman', 'pull', f'oci:{work}/image', capture=True)
    after = json.loads(run('podman', 'image', 'inspect', image_id, capture=True))[0]
    assert before['Architecture'] == after['Architecture']
    for key in ('Env', 'Cmd', 'Entrypoint', 'User', 'WorkingDir', 'StopSignal', 'Labels'):
        expected = before['Config'].get(key)
        if key == 'Labels':
            expected = {k: v for k, v in (expected or {}).items()
                        if k not in ('ostree.commit', 'ostree.final-diffid')}
        assert expected == after['Config'].get(key), f'Image configuration changed: {key}'
    run('podman', 'run', '--rm', '--pull=never', '--network=none', '--entrypoint',
        'bootc', image_id, 'container', 'lint', '--fatal-warnings')
    run('podman', 'run', '--rm', '--pull=never', '--network=none',
        f'--mount=type=image,src={source_id},target=/run/source',
        f'--mount=type=image,src={image_id},target=/run/target',
        '-v', f'{ROOT}/tests/rechunk-smoke.py:/run/rechunk-smoke.py:ro',
        '--entrypoint', 'python3', source_id,
        '/run/rechunk-smoke.py', '/run/source', '/run/target')
    # No published or local source tag is replaced until every validation passes.
    run('podman', 'tag', image_id, destination)
    index = json.loads((work / 'image/index.json').read_text())
    manifest = json.loads((work / 'image/blobs/sha256' /
                           index['manifests'][0]['digest'].split(':')[1]).read_text())
    report = {'source_id': source_id, 'image_id': image_id,
              'source_size_bytes_podman': before['Size'],
              'result_size_bytes_podman': after['Size'],
              'result_layer_bytes_gzip': sum(layer['size'] for layer in manifest['layers']),
              'layers': len(manifest['layers']), 'chunkah': CHUNKAH_IMAGE}
    (work / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--tag', help='Destination tag; defaults to replacing the source tag')
    parser.add_argument('--output', type=Path, help='Keep OCI output and report in a new directory')
    args = parser.parse_args()
    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)
    if args.output:
        work = args.output.resolve()
        work.mkdir(parents=True, exist_ok=False)
        rechunk(args.source, args.tag or args.source, work)
    else:
        with tempfile.TemporaryDirectory(prefix='rechunk-', dir=cache) as temporary:
            rechunk(args.source, args.tag or args.source, Path(temporary))


if __name__ == '__main__':
    main()
