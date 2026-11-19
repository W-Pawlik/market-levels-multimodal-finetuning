"""Package a completed, verified final pair without weights or production data.

For the author's later execution; stage 4.6A does not produce real test results.
"""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from market_levels.inference.workflows.final_test import verify_pair
from market_levels.inference.io.final_state import read
from market_levels.evaluation.workflows.verification import read_evaluation, read_comparison
from market_levels.shared.integrity import sha256_file


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    verify_pair(Path('configs/vlm/final-test.json'),args.session)
    outputs=[Path('results/evaluation')/f'vlm46-final-test-{v}' for v in ['base-nf4','finetuned-nf4']]
    for variant,output in zip(['base-nf4','finetuned-nf4'],outputs):
        report=read_evaluation(output)
        if (report['run']!=read(args.session/variant/'run.json')
                or sha256_file(output/'predictions.jsonl')!=sha256_file(args.session/variant/'predictions.jsonl')):
            raise ValueError('Official report differs from frozen raw inference')
    comparison=Path('results/evaluation/vlm46-final-test-comparison')
    paired=read_comparison(comparison)
    if (paired['baseline_run']!=read(args.session/'base-nf4/run.json') or
            paired['candidate_run']!=read(args.session/'finetuned-nf4/run.json')):
        raise ValueError('Wrong final comparison')
    if args.output.suffix.lower()!='.zip' or args.output.exists():
        raise ValueError('New ZIP path required')
    files=[p for root in [args.session,*outputs,comparison] for p in root.rglob('*')
           if p.is_file() and p.name!='execution.lock']
    files.extend(p for pattern in ['vlm46-*.console.log','vlm46-*.exit.json'] for p in Path('results').glob(pattern))
    allowed={'.json','.jsonl','.sha256','.md','.log'}
    if any(p.suffix.lower() not in allowed for p in files):
        raise ValueError('Unexpected artifact; refusing to package weights/data/pending writes')
    manifest={p.as_posix():sha256_file(p) for p in sorted(set(files))}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(set(files)):z.write(p,p.as_posix())
        z.writestr('MANIFEST_SHA256.json',json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(args.output) as z:
        assert z.testzip() is None
        for name,expected in manifest.items():
            assert hashlib.sha256(z.read(name)).hexdigest()==expected
    checksum=sha256_file(args.output)
    args.output.with_suffix('.zip.sha256').write_text(checksum+'  '+args.output.name+'\n',encoding='ascii')
    print(json.dumps({'zip':str(args.output),'sha256':checksum,'files':len(manifest)}))


if __name__=='__main__':main()
