"""Zbiorcza kontrola 3.5; nowy katalog wynikowy, bez modyfikowania źródeł."""
import argparse
import json
from pathlib import Path
import re
import tempfile

from market_levels.charts.renderer import render_window
from market_levels.datasets.packaging import (diagnostic_output, seal, verify_files, verify_smoke)
from market_levels.data_processing.staging import publication_workspace, publish_directory
from market_levels.labeling.pilot import read_pilot, sha256, verify_labeling


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', type=Path, required=True)
    parser.add_argument('--smoke', type=Path, required=True)
    parser.add_argument('--pilot', type=Path, required=True)
    parser.add_argument('--labeling', type=Path, required=True)
    parser.add_argument('--test-log', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--check-local-sources', action='store_true')
    args = parser.parse_args()
    output = diagnostic_output(args.output)
    verify_files(args.preflight)
    smoke = verify_smoke(args.smoke)
    loaded, pilot_ledger = read_pilot(args.pilot)
    with tempfile.TemporaryDirectory(prefix='ds-pilot-') as tmp:
        for i, (record, candles) in enumerate(loaded):
            rendering = render_window(candles, Path(tmp)/f'{i:03d}.png')
            if rendering['png_sha256'] != record['png_sha256']:
                raise ValueError('Niezgodny oryginalny PNG pilotażu')
    verify_labeling(args.labeling, args.pilot, re_render=True)
    plan = json.loads((args.preflight/'plan.json').read_text(encoding='utf-8'))
    source_checks = []
    if args.check_local_sources:
        ledger = dict(plan['source_integrity']['sha256'])
        ledger.update(pilot_ledger)
        for name, digest in ledger.items():
            if sha256(Path(name)) != digest:
                raise ValueError(f'Źródło zmieniło się: {name}')
            source_checks.append({'path': name, 'sha256': digest, 'unchanged': True})
    log_bytes = args.test_log.read_bytes()
    log = log_bytes.decode('utf-8', errors='replace')
    if log_bytes.startswith((b'\xff\xfe', b'\xfe\xff')):
        log = log_bytes.decode('utf-16')
    matches = re.findall(r'Ran (\d+) tests? in ([\d.]+)s', log)
    if len(matches) != 1 or not re.search(r'^OK\s*$', log, flags=re.MULTILINE) or re.search(r'^(FAILED|ERROR:|FAIL:)', log, flags=re.MULTILINE):
        raise ValueError('Log nie potwierdza jednego udanego przebiegu testów')
    count, seconds = matches[0]
    report = {'status': 'verified_diagnostic_only', 'final_dataset_built': False,
              'tests': {'passed': int(count), 'failed': 0, 'seconds': float(seconds)},
              'smoke': smoke, 'original_pilot_png_replayed': len(loaded),
              'labeling_replayed': 32, 'local_sources_checked': source_checks,
              'large_sources_required_for_preflight': True,
              'artifacts': {str(p): sha256(p/'manifest.json') for p in (args.preflight, args.smoke, args.labeling)}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with publication_workspace(output.parent, prefix='.ds-') as temporary:
        stage = temporary/'batch'
        stage.mkdir()
        (stage/'tests.log').write_text(log, encoding='utf-8')
        (stage/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        seal(stage, {'kind': 'stage35_integrity', 'schema_version': 1})
        verify_files(stage)
        publish_directory(stage, output)
    print(f'OK: {count} testów, 8 nowych przykładów, 32 oryginalne PNG i 32 etykiety/overlays; {len(source_checks)} źródeł lokalnych')


if __name__ == '__main__':
    main()
