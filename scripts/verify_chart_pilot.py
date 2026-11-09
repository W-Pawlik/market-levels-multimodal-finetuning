"""Verify a portable diagnostic pilot without access to the original large data."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from market_levels.charts.io.rendering import render_window
from market_levels.charts.domain.validation import validate_window
from market_levels.data_processing.io.candles import read_candles_csv
from market_levels.core.ohlc.identity import canonical_hash


def child(root: Path, name: str) -> Path:
    path = (root/name).resolve()
    if root.resolve() not in path.parents:
        raise ValueError('Pilot path escapes its directory')
    return path


def main():
    from PIL import Image
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pilot',type=Path)
    parser.add_argument('--re-render',action='store_true',help='Compare PNG bytes in the same rendering environment')
    args = parser.parse_args()
    manifest = json.loads((args.pilot/'manifest.json').read_text(encoding='utf8'))
    if manifest['actual_count'] != len(manifest['images']):
        raise ValueError('Invalid image count')
    with tempfile.TemporaryDirectory(prefix='chart-verify-') as temporary:
        for index,record in enumerate(manifest['images']):
            png = child(args.pilot,record['png'])
            csv = child(args.pilot,record['window_csv'])
            sidecar = png.with_suffix('.json')
            if json.loads(sidecar.read_text(encoding='utf8')) != record:
                raise ValueError(f'Sidecar mismatch: {png}')
            for path,key in ((png,'png_sha256'),(csv,'window_csv_sha256')):
                if hashlib.sha256(path.read_bytes()).hexdigest() != record[key]:
                    raise ValueError(f'Hash mismatch: {path}')
            candles = read_candles_csv(csv,source='portable-pilot')
            validate_window(candles)
            if canonical_hash(candles) != record['ohlc_sha256']:
                raise ValueError(f'OHLC mismatch: {csv}')
            with Image.open(png) as image:
                if image.size != (1024,768) or image.format != 'PNG':
                    raise ValueError(f'Invalid PNG: {png}')
            if args.re_render:
                rendered = render_window(candles,Path(temporary)/f'{index:03d}.png')
                if rendered['png_sha256'] != record['png_sha256']:
                    raise ValueError(f'Render differs; check renderer, Matplotlib, fonts and platform: {png}')
    print(f"OK: {manifest['actual_count']} PNG, 120 candles each, hashes and sidecars" + ('; identical re-render' if args.re_render else ''))


if __name__ == '__main__':
    main()
