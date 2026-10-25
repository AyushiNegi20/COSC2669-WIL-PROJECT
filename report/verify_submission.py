"""Check the report evidence package without running or scoring a language model."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'report'
PACKET = REPORT / 'evidence/historical-release-20260926T233529Z'
TAG = 'report-submission-2026-10-25'


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def verify(source=None, write_hashes=False, git_ref=None):
    errors = []
    originals = [f'{i:03}.json' for i in range(1, 25)] + [
        'results.json', 'questions.json', 'EVALUATION.md']
    hashes = {name: digest(PACKET / name) for name in originals}
    if write_hashes:
        (PACKET / 'SHA256SUMS.json').write_text(
            json.dumps(hashes, indent=2) + '\n', encoding='utf-8', newline='\n')
    elif json.loads((PACKET / 'SHA256SUMS.json').read_text('utf-8')) != hashes:
        errors.append('Historical evidence hashes differ')

    aggregate = json.loads((PACKET / 'results.json').read_text('utf-8'))
    responses = [json.loads((PACKET / f'{i:03}.json').read_text('utf-8'))
                 for i in range(1, 25)]
    if aggregate['results'] != responses:
        errors.append('Individual responses differ from original aggregate')
    if (aggregate['questions'] != 24 or aggregate['errors'] != 0
            or not aggregate['before']['unchanged'] or not aggregate['after']['unchanged']):
        errors.append('Historical run metadata differs from report account')
    if len({item['id'] for item in responses}) != 24:
        errors.append('Historical question IDs are not unique')

    manifest_path = ROOT / 'fintrace/releases/current.json'
    manifest = json.loads(manifest_path.read_text('utf-8'))
    setup = json.loads((ROOT / 'fintrace/config/setup_artifacts.json').read_text('utf-8'))
    if setup['manifest_sha256'] != digest(manifest_path):
        errors.append('Setup manifest checksum differs')
    if setup['repository'] != 'AyushiNegi20/COSC2669-WIL-PROJECT':
        errors.append('Setup incorrectly depends on the private development repository')
    code_files = 0
    for name, expected in manifest['files_sha256'].items():
        if name.startswith(('data/', 'models/')):
            continue
        path = ROOT / 'fintrace' / name
        code_files += 1
        if not path.is_file() or digest(path) != expected:
            errors.append('Manifest-listed code differs: ' + name)

    if source:
        # Existing source files are read only; no historical response is changed.
        source = source.resolve()
        for name in ('scripts/answer_bank_conversational.py', 'scripts/bank_query_routing.py',
                     'releases/current.json'):
            if digest(ROOT / 'fintrace' / name) != digest(source / name):
                errors.append('Runtime checkpoint mismatch: ' + name)
        for name in [f'{i:03}.json' for i in range(1, 25)] + ['results.json']:
            if digest(source / 'reports/runs/release-20260926T233529Z' / name) != hashes[name]:
                errors.append('Original response changed: ' + name)

    if git_ref is not None:
        # Git line-ending filters must not change checksum-covered bytes.
        expected_git = {'report/evidence/historical-release-20260926T233529Z/' + name: value
                        for name, value in hashes.items()}
        expected_git.update({'fintrace/' + name: value
                             for name, value in manifest['files_sha256'].items()
                             if not name.startswith(('data/', 'models/'))})
        for name, expected in expected_git.items():
            result = subprocess.run(['git', 'cat-file', 'blob', git_ref + ':' + name],
                                    cwd=ROOT, capture_output=True, check=False)
            if result.returncode or sha256(result.stdout).hexdigest() != expected:
                errors.append('Stored Git bytes differ: ' + name)

    links_checked = 0
    for path in (REPORT / 'latex').glob('*'):
        if path.suffix not in ('.tex', '.bib'):
            continue
        text = path.read_text('utf-8')
        if 'FinTrace-Backend/' in text:
            errors.append('Private evidence link remains: ' + path.name)
        if r'\instructions{' in text:
            errors.append('Template instructions remain: ' + path.name)
        pattern = (r'https://github\.com/AyushiNegi20/COSC2669-WIL-PROJECT/'
                   r'(?:blob|tree)/' + TAG + r'/([^\s}]+)')
        for target in re.findall(pattern, text):
            links_checked += 1
            if not (ROOT / target.rstrip('),.;')).exists():
                errors.append('Missing public evidence target: ' + target)
    appendix = (REPORT / 'latex/99_appendix.tex').read_text('utf-8')
    for name in ('Yash Keswani', 'Shriram Varadarajan', 'Guruprasad Simimath',
                 'Janhavi Maheshwar Ghate', 'Hashini Santhanakrishnan'):
        after = appendix.split(r'\subsection{' + name + ': Individual Reflection}', 1)[1]
        section = after.split(r'\subsection{', 1)[0]
        if '\n' not in section or any(line.strip() and not line.lstrip().startswith('%')
                                      for line in section.splitlines()):
            errors.append('An owner reflection was filled unexpectedly: ' + name)

    result = {
        'errors': errors, 'historical_responses': len(responses),
        'historical_candidate': aggregate['candidate']['commit'],
        'historical_integrity_before_after': True,
        'manifest_listed_code_files_checked': code_files,
        'report_public_link_targets_checked': links_checked,
        'runtime_manifest_sha256': digest(manifest_path),
        'remaining_owner_reflections': 5,
        'new_model_accuracy_assessment': False,
        'local_data_and_models_verified_by_this_script': False,
    }
    print(json.dumps(result, indent=2))
    return bool(errors)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-backend', type=Path)
    parser.add_argument('--write-hashes', action='store_true')
    parser.add_argument('--git-ref', help='Use HEAD for a commit, or an empty string for staged bytes')
    args = parser.parse_args()
    raise SystemExit(verify(args.source_backend, args.write_hashes, args.git_ref))
