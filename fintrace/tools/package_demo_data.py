"""Package only checked processed evidence for a GitHub Release, never credentials."""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from prepare_demo import ROOT, already_present, digest, target_path


def package(root, output):
    files = json.loads((root / 'releases/current.json').read_text(encoding='utf-8'))['files_sha256']
    selected = {k: v for k, v in files.items() if k.startswith('data/processed/')}
    if not selected:
        raise ValueError('No processed artifacts in manifest')
    for name, expected in selected.items():
        if not already_present(target_path(root, name), expected):
            raise ValueError(f'Missing source: {name}')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids replacing an existing published bundle.
    with ZipFile(output, 'x', compression=ZIP_DEFLATED) as archive:
        for name in sorted(selected):
            archive.write(target_path(root, name), arcname=name)
    return {'asset': output.name, 'asset_sha256': digest(output),
            'manifest_sha256': digest(root / 'releases/current.json'),
            'files': len(selected), 'bytes': output.stat().st_size}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(package(ROOT, args.output), indent=2))
