"""Read-only stage 4.5 evidence audit; never imports model or GPU libraries.

Run from repository root: .venv/Scripts/python.exe scripts/audit_vlm45.py before|analyze|after
Outputs only to results/vlm45-final-audit-20261111-a and new docs/vlm artifacts.
"""
import argparse
import csv
import hashlib
import json
import math
import struct
import subprocess
from collections import Counter
from pathlib import Path

from market_levels.shared.integrity import sha256_file
from market_levels.shared.manifests import verify_files
from market_levels.evaluation.workflows.verification import read_evaluation
from market_levels.evaluation.protocol import dumps
from market_levels.evaluation.domain.models import Reference
from market_levels.evaluation.domain.responses import parse_response
from market_levels.inference.domain.price_diagnostics import diagnostic_scores
from decimal import Decimal

OUT = Path('results/vlm45-final-audit-20261111-a')
DATA = Path('data/datasets/ds35-800-20261107-a')
RUNS = ['vlm43-part1-14789-1679', 'vlm43-part2-17032-13034',
        'vlm43-part3-2708-16743', 'vlm44-part1-24755-21138', 'vlm44-part2-17554-5354']
EVALS = ['vlm41-cz2-20261110-1840-nf4', 'vlm41-cz2-20261110-1840-bf16',
         'vlm42-price-baseline-20261110-a-nf4', 'vlm42-price-baseline-20261110-a-bf16',
         'vlm43-validation-step175-26351-3437', 'vlm43-validation-step350-9320-26567',
         'vlm44-validation-4184-25636']


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def write(p, value):
    Path(p).write_text(dumps(value)+'\n', encoding='utf-8')


def inventory():
    paths = [p for root in ('data', 'results', 'src', 'configs', 'docs')
             for p in Path(root).rglob('*') if p.is_file()
             and OUT not in p.parents and '__pycache__' not in p.parts]
    return {p.as_posix(): {'sha256': sha256_file(p), 'bytes': p.stat().st_size}
            for p in sorted(paths)}


def tensor_header(p):
    with p.open('rb') as f:
        size = struct.unpack('<Q', f.read(8))[0]
        header = json.loads(f.read(size))
    tensors = [x for k, x in header.items() if k != '__metadata__']
    return {'tensor_count': len(tensors), 'parameters': sum(math.prod(x['shape']) for x in tensors)}


def tensor_payload(p):
    with p.open('rb') as f:
        size=struct.unpack('<Q',f.read(8))[0]
        header=json.loads(f.read(size)); payload=f.read()
    return {k:(v['dtype'],v['shape'],payload[v['data_offsets'][0]:v['data_offsets'][1]])
            for k,v in header.items() if k!='__metadata__'}


def analyze():
    checks = []
    dataset = verify_files(DATA)
    checks.append({'check': 'dataset manifest and all file hashes', 'passed': True, 'count': len(dataset['files'])})
    entries = dataset['entries']
    counts = Counter((e['split'], e['source'], e['symbol']) for e in entries)
    # Test entries are counted from the manifest only; no test metadata/labels/OHLC parsed.
    ranges = {}
    for split in ('train', 'validation'):
        meta = [read(DATA/e['metadata']) for e in entries if e['split'] == split and e['source'] == 'real']
        ranges[split] = {'first_open': min(m['start_utc'] for m in meta),
                         'last_open': max(m['end_utc'] for m in meta)}
    write(OUT/'dataset.json', {'manifest_sha256': sha256_file(DATA/'manifest.json'),
          'counts': [{'split': k[0], 'source': k[1], 'symbol': k[2], 'count': v} for k,v in counts.items()],
          'observed_real_ranges': ranges, 'test_metadata_parsed': False})
    eval_results = {}
    for name in EVALS:
        p = Path('results/evaluation')/name
        if 'price-baseline' in name:
            verify_files(p)
            diagnostic = read(p/'diagnostics.json')
            eval_results[name] = diagnostic
            checks.append({'check':'auxiliary diagnostic manifest; excluded from official model selection',
                           'path':p.as_posix(),'passed':True})
            continue
        report = read_evaluation(p)
        assert report['binding']['split'] == 'validation'
        s = report['summary']
        for tolerance, content in s['tolerances'].items():
            overall = content['overall']
            for group in ('by_side', 'by_symbol'):
                for key in ('tp', 'fp', 'fn', 'predicted_levels', 'reference_levels'):
                    assert sum(g[key] for g in content[group].values()) == overall[key]
            for g in [overall, *content['by_side'].values(), *content['by_symbol'].values()]:
                tp,fp,fn = (g[k] for k in ('tp','fp','fn'))
                for key, a, b in [('micro_f1',2*tp,2*tp+fp+fn),('micro_precision',tp,tp+fp),('micro_recall',tp,tp+fn)]:
                    if b: assert math.isclose(float(g[key]), a/b, abs_tol=1e-14)
        eval_results[name] = {'summary': s, 'run': report['run'], 'fingerprint': report['binding']['fingerprint'],
                              'summary_sha256': sha256_file(p/'summary.json'), 'manifest_sha256': sha256_file(p/'manifest.json')}
        checks.append({'check': 'exact evaluator replay, manifest, formulas, group sums', 'path': p.as_posix(), 'passed': True})
    manifest_entries={e['id']:e for e in entries if e['split']=='validation'}
    closes={}
    for identity,entry in manifest_entries.items():
        with (DATA/entry['ohlc']).open(encoding='utf-8') as f:
            closes[identity]=Decimal(list(csv.DictReader(f))[-1]['close'])
    for evname,diagpath in [(EVALS[0],Path('results/evaluation')/EVALS[2]),
                             (EVALS[1],Path('results/evaluation')/EVALS[3]),
                             (EVALS[-2],Path('results')/EVALS[-2]/'price-diagnostics'),
                             (EVALS[-1],Path('results')/EVALS[-1]/'price-diagnostics')]:
        verify_files(diagpath)
        report=read_evaluation(Path('results/evaluation')/evname)
        refs=[Reference(r['id'],r['symbol'],'validation',parse_response(dumps(r['reference'])).levels,r['atr']) for r in report['rows']]
        diagnostics=diagnostic_scores(refs,{r['id']:r['raw_response'] for r in report['rows']},closes)
        from market_levels.evaluation.protocol import loads
        saved=loads((diagpath/'diagnostics.json').read_text(encoding='utf-8'))['price_diagnostics']
        for key in ('metrics','close_side_diagnostics','fence_removed_count'):
            assert dumps(diagnostics[key])==dumps(saved[key])
    checks.append({'check':'exact fence-only and Close-side diagnostics replay on validation only','passed':True})
    write(OUT/'evaluations.json', eval_results)
    steps_all = []
    run_results = []
    for name in RUNS:
        root = Path('results')/name
        config = read(root/'effective-config.json')
        identity = read(root/'identity.json')
        assert identity['config'] == config
        extra=name.startswith('vlm44-')
        assert config['runtime']['models']['qwen3-vl']['revision']=='89644892e4d85e24eaac8bacfd4f463576704203'
        assert config['runtime']['training']['rank']==8 and config['runtime']['training']['alpha']==16
        assert config['runtime']['training']['learning_rate']==(0.00005 if extra else 0.0002)
        for key,value in {'batch_size':1,'gradient_accumulation':4,'scheduler':'linear',
                          'save_every_steps':25,'epochs':1 if extra else 2,'warmup_steps':9 if extra else 18}.items():
            assert config['pipeline'][key]==value
        for key,value in {'quantization':'NF4','double_quantization':True,'compute_dtype':'bfloat16',
                          'lora_dropout':0,'optimizer':'AdamW','instruction_version':'pl-sr-v1'}.items():
            assert config['fixed'][key]==value
        assert len(identity['lora_targets'])==56 and all('.language_model.' in t and t.endswith(('.q_proj','.v_proj')) for t in identity['lora_targets'])
        assert identity['dataset']['manifest_sha256'] == sha256_file(DATA/'manifest.json')
        events = [json.loads(l) for l in (root/'events.jsonl').read_text(encoding='utf-8').splitlines()]
        steps = [e for e in events if e['event']=='step']
        result = read(root/'result.json')
        for step in steps:
            assert all(math.isfinite(step[k]) for k in ('loss','gradient_norm','learning_rate'))
            assert len(step['ids']) == len(step['losses']) == len(step['batches'])
            assert all(b['processed_width']==1024 and b['processed_height']==768 and b['image_tokens']==768 for b in step['batches'])
            steps_all.append(dict(run=name, **step))
        checkpoints=[]
        for p in sorted((root/'checkpoints').glob('step-*')):
            manifest = verify_files(p)
            checkpoints.append({'path':p.as_posix(), 'manifest_sha256':sha256_file(p/'manifest.json')})
        verify_files(root/'adapter')
        tensors=tensor_header(root/'adapter/adapter_model.safetensors')
        assert tensors == {'tensor_count':112,'parameters':1605632}
        resumed=[e for e in events if e['event']=='resumed']
        initialized=[e for e in events if e['event']=='initialized_from_adapter']
        assert not any(e['event'] in ('failed','memory_pressure') for e in events)
        if resumed:
            assert len(resumed)==1 and not initialized
            source=Path(resumed[0]['source'].replace('\\','/'))
            initial=root/'checkpoints'/f"step-{resumed[0]['step']:06d}"
            original=read(source/'metadata.json'); restored=read(initial/'metadata.json')
            # Reload/setup time is added before publishing the resumed initial checkpoint.
            assert restored['sampler']['elapsed_seconds'] >= original['sampler']['elapsed_seconds']
            original['sampler'].pop('elapsed_seconds'); restored['sampler'].pop('elapsed_seconds')
            assert original == restored
            assert tensor_payload(source/'adapter/adapter_model.safetensors') == tensor_payload(initial/'adapter/adapter_model.safetensors')
        assert result['sampler']==read(Path(result['latest_checkpoint'].replace('\\','/'))/'metadata.json')['sampler']
        run_results.append({'run':name,'status':result['status'],'steps':len(steps),'first':steps[0]['step'],
             'last':steps[-1]['step'],'processed_examples':result['sampler']['processed_examples'],
             'epoch':result['sampler']['epoch'],'position':result['sampler']['position'],
             'step_seconds_sum':sum(e['seconds'] for e in steps),
             'first_lr':steps[0]['learning_rate'],'last_lr':steps[-1]['learning_rate'],
             'loss_mean':sum(e['loss'] for e in steps)/len(steps),
             'resumed':resumed,'initialized_from_adapter':initialized,'checkpoints':checkpoints,
             'tensor_header':tensors,'provenance':identity.get('provenance'),
             'memory':{k:max(e['memory'][k] for e in steps if k in e['memory']) for k in
                       ['rss_mib','peak_rss_mib','used_vram_mib','peak_global_vram_mib','peak_allocated_mib','peak_reserved_mib']}})
    train_ids={e['id'] for e in entries if e['split']=='train'}
    for names,total,epochs,seed in [(RUNS[:3],350,2,read(Path('results')/RUNS[0]/'effective-config.json')['pipeline']['seed']),
                                  (RUNS[3:],175,1,20261112)]:
        assert all(read(Path('results')/name/'identity.json') == read(Path('results')/names[0]/'identity.json') for name in names)
        steps=[s for s in steps_all if s['run'] in names]
        assert [s['step'] for s in steps] == list(range(1,total+1))
        for epoch in range(1,epochs+1):
            ids=[i for s in steps if s['epoch']==epoch for i in s['ids']]
            assert len(ids)==698 and set(ids)==train_ids
            import random
            order=sorted(train_ids); random.Random(seed+epoch-1).shuffle(order)
            assert ids==order
        for s in steps:
            cfg=read(Path('results')/s['run']/'effective-config.json')
            n=s['step']-1; warm=cfg['pipeline']['warmup_steps']; peak=cfg['runtime']['training']['learning_rate']
            lr=peak*(n/warm if n<warm else max(0,(total-n)/(total-warm)))
            assert math.isclose(s['learning_rate'],lr,rel_tol=1e-12,abs_tol=1e-16)
    write(OUT/'training.json',run_results)
    write(OUT/'steps.json',steps_all)
    checks.append({'check':'525 step records, deterministic train orders, LR, finite loss, identity configs and checkpoint manifests','passed':True})
    before={r['id']:r for r in read_evaluation(Path('results/evaluation')/EVALS[-2])['rows']}
    after=read_evaluation(Path('results/evaluation')/EVALS[-1])['rows']
    paired=[]
    for r in after:
        a=before[r['id']]; b=r['scores']['0.5']; old=a['scores']['0.5']
        paired.append({'id':r['id'],'symbol':r['symbol'],'old_f1':old['example_f1'],'new_f1':b['example_f1'],
                       'delta_f1':b['example_f1']-old['example_f1'],'old_tp':old['tp'],'new_tp':b['tp'],
                       'old_fp':old['fp'],'new_fp':b['fp'],'old_fn':old['fn'],'new_fn':b['fn'],
                       'complete':b['complete_set_correct'],'zero_tp':b['tp']==0,
                       'reference':r['reference'],'old_predicted':a['predicted'],'new_predicted':r['predicted'],
                       'atr':r['atr']})
    write(OUT/'paired.json',paired)
    parent=Path('results')/RUNS[2]/'adapter/adapter_model.safetensors'
    initial=Path('results')/RUNS[3]/'checkpoints/step-000000/adapter/adapter_model.safetensors'
    assert tensor_payload(parent)==tensor_payload(initial)
    init=read(Path('results')/RUNS[3]/'initialization.json')
    assert init['tensor_values_exact'] and init['tensor_count']==112 and init['trainable_parameters']==1605632
    assert init['parent_adapter_sha256']==sha256_file(parent)
    for name,evname in [(RUNS[1],EVALS[-3]),(RUNS[2],EVALS[-2]),(RUNS[4],EVALS[-1])]:
        root=Path('results')/name
        assert sha256_file(root/'adapter/adapter_model.safetensors') == eval_results[evname]['run']['checkpoint_id']
        assert tensor_payload(root/'adapter/adapter_model.safetensors') == tensor_payload(Path(read(root/'result.json')['latest_checkpoint'].replace('\\','/'))/'adapter/adapter_model.safetensors')
    checks.append({'check':'parent tensor bytes, resumed metadata/tensor equality, final export/checkpoint/validation binding','passed':True})
    write(OUT/'checks.json',checks)
    print('Offline replay and training audit passed:',len(checks),'checks; 525 steps; 7 evaluation reports')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['before','analyze','after'])
    args=parser.parse_args()
    if args.command=='before':
        OUT.mkdir(exist_ok=False,parents=True)
        (OUT/'git-before.txt').write_bytes(subprocess.check_output(['git','status','--porcelain=v1']))
        write(OUT/'inventory-before.json',inventory())
        print('Saved baseline inventory')
    elif args.command=='analyze':
        analyze()
    else:
        before=read(OUT/'inventory-before.json'); after=inventory()
        changed=[p for p in before if p in after and before[p]!=after[p]]
        removed=sorted(before.keys()-after.keys())
        summary={'historical_files':len(before),'changed':changed,'removed':removed,
                 'new_files':sorted(after.keys()-before.keys()),
                 'dataset_files':sum(p.startswith(DATA.as_posix()+'/') for p in before),
                 'test_used_for_inference_or_selection':False,'gpu_or_training_started':False,
                 'scope':'SHA-256 bytes only for test; no test label/metadata/OHLC analysis'}
        write(OUT/'integrity-summary.json',summary)
        assert not changed and not removed, summary
        print(json.dumps(summary))


if __name__=='__main__':
    main()
