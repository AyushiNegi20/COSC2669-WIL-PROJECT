"""Create or verify an immutable-named extraction snapshot before external review.

This freezes an experimental version, not an accuracy certification. New pages,
reference answers and scores belong to a separate holdout run directory.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys

from extract_bank_reports import ROOT, BASE, expanded, read, save

RELEASE_FILES = [
    'config/banking_sources.json', 'config/banking_extraction_scope.json',
    'config/numeric_consistency.json', 'requirements-extraction.txt',
    'scripts/extract_bank_reports.py', 'scripts/pdf_visibility.py',
    'scripts/benchmark_pdf_extraction.py', 'scripts/download_bank_sources.py',
    'scripts/inspect_extraction_pages.py', 'scripts/validate_bank_extraction.py',
    'scripts/check_numeric_consistency.py', 'scripts/freeze_extraction.py',
    'tests/test_pdf_extraction.py', 'tests/test_numeric_consistency.py',
    'tests/test_extraction_freeze.py', 'eval/extraction/reference.json',
    'eval/extraction/additional_checks.json', 'docs/BANKING_PDF_EXTRACTION.md',
    'docs/EXTRACTION_HOLDOUT_HANDOFF.md', 'reports/extraction_benchmark.json',
    'reports/banking_extraction_acceptance.json', 'reports/extraction_environment.json',
    'reports/numeric_consistency.json',
]


def relative_path(root, name):
    path = (root/name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'Path escapes repository: {name}')
    return path


def digest(path, canonical_text=False):
    data = path.read_bytes()
    if canonical_text:
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def verify_entries(root, entries, canonical_text=False):
    errors = []
    for name, expected in entries.items():
        path = relative_path(root, name)
        if not path.is_file():
            errors.append(f'Missing: {name}')
        elif digest(path, canonical_text) != expected:
            errors.append(f'Changed: {name}')
    return errors


def create_snapshot(target):
    if target.exists():
        raise FileExistsError('Freeze already exists. Do not overwrite it; choose a new release ID.')
    # Only the extraction suite belongs to this freeze, not unrelated local work.
    test_result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
                                  '-p', 'test_*extraction*.py', '-v'], cwd=ROOT)
    if test_result.returncode:
        raise ValueError('Extraction tests failed')
    numeric_tests = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
                                    '-p', 'test_numeric_consistency.py', '-v'], cwd=ROOT)
    if numeric_tests.returncode:
        raise ValueError('Numeric consistency tests failed')
    acceptance = subprocess.run([sys.executable, 'scripts/validate_bank_extraction.py'], cwd=ROOT)
    if acceptance.returncode:
        raise ValueError('Extraction acceptance checks failed')
    audit = read(ROOT/'reports/numeric_consistency.json')
    if audit['errors'] or audit['status'] == 'invalid_inputs':
        raise ValueError('Invalid numeric consistency run')
    errors = verify_entries(ROOT, audit['input_sha256'])
    if errors:
        raise ValueError(f'Stale numeric consistency inputs: {errors}')
    if audit['settings'] != read(ROOT/'config/numeric_consistency.json'):
        raise ValueError('Numeric settings changed since the consistency run')
    # Code/config hashes prove which guard produced the report, not just its inputs.
    errors = verify_entries(ROOT, audit['checker_sha256'], canonical_text=True)
    if errors:
        raise ValueError(f'Stale numeric consistency checker: {errors}')
    environment = read(ROOT/'reports/extraction_environment.json')
    for package, expected in environment['versions'].items():
        if package != 'python' and importlib.metadata.version(package) != expected:
            raise ValueError(f'Installed package differs from recorded environment: {package}')
    if read(ROOT/'reports/banking_extraction_acceptance.json')['errors']:
        raise ValueError('Existing acceptance checks failed')
    scope = read(ROOT/'config/banking_extraction_scope.json')['pages']
    local_files = dict(audit['input_sha256'])
    for doc in read(ROOT/'config/banking_sources.json')['documents']:
        local_files[f"data/raw/{doc['file']}"] = doc['sha256']
        for page in expanded(scope[doc['id']]):
            name = f"data/processed/banking_v1/structured/{doc['id']}/page_{page:03}.json"
            local_files[name] = digest(ROOT/name)
    for name in (audit['details_path'], audit['review_queue_path'], audit['review_markdown_path'],
                 'data/processed/banking_v1/summary.json'):
        local_files[name] = digest(relative_path(ROOT, name))
    for model in environment['models']:
        for item in model['files']:
            name = f"models/huggingface/hub/{model['model']}/snapshots/{model['revision']}/{item['path']}"
            local_files[name] = item['sha256']
    errors = verify_entries(ROOT, local_files)
    if errors:
        raise ValueError(f'Local snapshot inputs changed: {errors}')
    snapshot = {
        'release_id': target.stem, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'frozen_for_independent_evaluation_not_accuracy_certified',
        'hash_policy': 'Release text files: SHA-256 after CRLF to LF. Local artifacts: exact-byte SHA-256.',
        'files': {name: digest(ROOT/name, True) for name in RELEASE_FILES},
        'local_artifacts': local_files,
        'numeric_consistency_status': audit['status'], 'numeric_counts': audit['counts'],
        'holdout': {'status': 'not_selected_or_scored', 'independent_reviewer': None},
        'limitations': ['Pending review flags are retained, not waived by freezing.',
                        'All 72 current structured pages are development-exposed after automated auditing.',
                        'Local outputs are not uploaded by creating this snapshot.',
                        'This manifest is tamper-evident when independently retained, not a signed release.'],
    }
    save(target, snapshot)
    print(json.dumps({'release_id': target.stem, 'files': len(snapshot['files']),
                      'local_artifacts': len(local_files), 'manifest_sha256': digest(target)}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--create', metavar='RELEASE_ID')
    group.add_argument('--verify', metavar='MANIFEST')
    parser.add_argument('--local', action='store_true', help='Also verify ignored local data and PDFs.')
    args = parser.parse_args()
    if args.create:
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,79}', args.create):
            parser.error('Use a short lowercase release ID, with digits, underscores or hyphens.')
        create_snapshot(ROOT/'releases'/f'{args.create}.json')
        return 0
    path = Path(args.verify)
    snapshot = read(path if path.is_absolute() else ROOT/path)
    errors = verify_entries(ROOT, snapshot['files'], canonical_text=True)
    if args.local:
        errors += verify_entries(ROOT, snapshot['local_artifacts'])
    print(json.dumps({'release_id': snapshot['release_id'], 'unchanged': not errors,
                      'local_artifacts_checked': args.local, 'errors': errors}, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
