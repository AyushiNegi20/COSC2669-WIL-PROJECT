"""Download only pinned public model files. Never send report text to a service."""
import argparse
from pathlib import Path
from huggingface_hub import snapshot_download
from build_bank_chunks import ROOT, read, save, sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tokenizers-only', action='store_true')
    args = parser.parse_args()
    config = read(ROOT / 'config/banking_retrieval.json')
    patterns = ['*.json', '*.txt', '*.model', '*.tiktoken']
    if not args.tokenizers_only:
        patterns.append('*.safetensors')
    records = {}
    for name, model in config['models'].items():
        print(f'Downloading pinned {name}', flush=True)
        folder = Path(snapshot_download(model['id'], revision=model['revision'],
                      cache_dir=str(ROOT / 'models/retrieval'),
                      allow_patterns=patterns, ignore_patterns=['onnx/*', 'openvino/*'], max_workers=3))
        records[name] = {'model': model['id'], 'revision': model['revision'],
                         'path': str(folder.relative_to(ROOT)).replace('\\', '/'),
                         'files': {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p)
                                   for p in folder.rglob('*') if p.is_file()}}
    save(ROOT / 'reports/retrieval_models.json', records)
    print('Public model download finished. No source documents were uploaded.', flush=True)


if __name__ == '__main__':
    main()
