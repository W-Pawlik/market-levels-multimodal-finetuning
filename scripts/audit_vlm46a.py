"""Verify stage 4.6A protected bytes and package code/documentation, never run Qwen."""
import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

from market_levels.shared.integrity import sha256_file
from market_levels.shared.manifests import verify_files
from market_levels.inference.final_config import load_plan

OUT=Path('results/vlm46a-preparation-20261112-a')
NEW=[
    'src/market_levels/inference/final_config.py',
    'src/market_levels/inference/io/final_inputs.py',
    'src/market_levels/inference/io/final_state.py',
    'src/market_levels/inference/io/final_model.py',
    'src/market_levels/inference/workflows/final_test.py',
    'src/market_levels/inference/workflows/final_scoring.py',
    'src/market_levels/cli/final_test.py',
    'configs/vlm/final-test.json',
    'scripts/run_vlm_final_test.ps1',
    'scripts/package_vlm46_results.py',
    'scripts/audit_vlm46a.py',
    'tests/unit/modeling/test_final_test.py',
    'tests/integration/evaluation/test_final_test_fixture.py',
    'tests/checks/check_vlm46_backend.py',
    'docs/vlm/INSTRUKCJA_POWERSHELL_4_6.md',
    'docs/vlm/RAPORT_4_6A_PRZYGOTOWANIE_TESTU.md',
    'docs/vlm/SZABLON_RAPORTU_4_6B.md',
]


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))


def write(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


def after():
    before=read(OUT/'inventory-before.json')
    changed=[];removed=[]
    for name,entry in before.items():
        p=Path(name)
        if not p.is_file():removed.append(name)
        elif p.stat().st_size!=entry['bytes'] or sha256_file(p)!=entry['sha256']:changed.append(name)
    assert not changed and not removed,{'changed':changed,'removed':removed}
    config,selection=load_plan(Path('configs/vlm/final-test.json'))
    dataset=verify_files(Path(config['dataset']))
    selected=verify_files(Path(selection['selected_adapter']))
    alternative=verify_files(Path(selection['preserved_alternative']['path']))
    for checkpoint in [selection['checkpoint_path'],'results/vlm43-part3-2708-16743/checkpoints/step-000350']:
        verify_files(Path(checkpoint))
    final=read(OUT/'tests-final-exit.json');cpu=read(OUT/'cpu46-final-exit.json')
    assert final['exit_code']==cpu['exit_code']==0
    log=(OUT/'tests-final.log').read_text(encoding='utf-8')
    assert 'Ran 407 tests' in log and '\nOK\n' in log
    assert not Path(config['output']).exists()
    assert not any(Path('results/evaluation').glob('vlm46-final-test-*'))
    summary={'protected_files':len(before),'changed':changed,'removed':removed,
             'dataset_files':len(dataset['files'])+2,'dataset_manifest_sha256':sha256_file(Path(config['dataset'])/'manifest.json'),
             'selection_sha256':sha256_file(Path(config['selection'])),
             'selected_adapter_sha256':sha256_file(Path(selection['selected_adapter'])/'adapter_model.safetensors'),
             'alternative_adapter_sha256':sha256_file(Path(selection['preserved_alternative']['path'])/'adapter_model.safetensors'),
             'production_session_created':False,'production_test_inference_run':False,
             'production_test_evaluation_run':False,'test_reference_values_analyzed':False,
             'initial_lightweight_cpu_check_initialized_cuda':True,
             'final_cpu_checks_block_cuda_initialization':True,
             'full_unittest_count':407,'full_unittest_exit':0,'separate_cpu_test_count':2,'separate_cpu_exit':0,
             'scope':'data/results/handoff/configs/src/scripts and historical docs/vlm, docs/evaluation before/after; active .ai/README/architecture updated separately'}
    write(OUT/'integrity-summary.json',summary)
    write(Path('docs/vlm/INTEGRITY_4_6A.json'),summary)
    critical={p:entry for p,entry in before.items() if p.startswith(('src/market_levels/evaluation/',
        'src/market_levels/datasets/domain/examples.py','configs/vlm/','docs/vlm/FINAL_MODEL_SELECTION.json',
        'docs/vlm/RAPORT_KONCOWY_DOSTRAJANIA_4_1_4_4.md','results/evaluation/')) or
        p in [str(Path(config['dataset'])/'manifest.json').replace('\\','/')]}
    write(OUT/'critical-sources.json',critical)
    checks=[]
    for name in NEW:
        if name.endswith('.md'):
            p=Path(name)
            targets=re.findall(r'!?\[[^\]]+\]\(([^)]+)\)',p.read_text(encoding='utf-8'))
            missing=[t for t in targets if not (p.parent/t.split('#')[0]).exists()]
            assert not missing,(p,missing)
            checks.append({'path':name,'links':len(targets),'missing':missing})
    write(OUT/'documentation-checks.json',checks)
    (OUT/'git-after.txt').write_bytes(subprocess.check_output(['git','status','--porcelain=v1']))
    print(json.dumps(summary,ensure_ascii=False))


def package():
    integrity=read(OUT/'integrity-summary.json')
    assert not integrity['changed'] and not integrity['removed']
    paths=[Path(n) for n in NEW]+[Path(n) for n in ['AGENTS.md','.ai/README.md','.ai/RULES.md',
        '.ai/CURRENT_STATE.md','.ai/WORKFLOW.md','README.md','docs/ARCHITECTURE.md',
        'docs/vlm/FINAL_MODEL_SELECTION.json','docs/vlm/INTEGRITY_4_6A.json']]
    paths.extend(p for p in OUT.iterdir() if p.is_file() and p.name!='inventory-before.json')
    # Include actual wrapper logs and exit records generated by the preparation checks.
    paths.extend(p for pattern in ['vlm46-*.console.log','vlm46-*.exit.json'] for p in Path('results').glob(pattern))
    assert all(p.suffix.lower() not in ['.pt','.safetensors','.png','.csv','.zip'] for p in paths)
    assert all(not p.as_posix().startswith('data/') for p in paths)
    payload={p.as_posix():{'sha256':sha256_file(p),'bytes':p.stat().st_size} for p in sorted(set(paths))}
    readme=('Etap 4.6A: przygotowanie bez produkcyjnej inferencji/ewaluacji testu.\n'
            'Raport: docs/vlm/RAPORT_4_6A_PRZYGOTOWANIE_TESTU.md.\n'
            'Instrukcja autora: docs/vlm/INSTRUKCJA_POWERSHELL_4_6.md.\n'
            'Paczka jest dodatkiem do bieżącego repozytorium. Nie uruchamiaj części wykonawczej bez audytu.\n'
            'Manifest SHA-256 obejmuje wszystkie załączniki poza sobą samym; SHA ZIP jest w osobnym sidecar.\n'
            'Nie zawiera wag, adapterów, checkpointów, produkcyjnych danych, cache ani środowisk.\n').encode('utf-8')
    payload['README_HANDOFF.txt']={'sha256':hashlib.sha256(readme).hexdigest(),'bytes':len(readme)}
    manifest=(json.dumps({'kind':'vlm46a_test_preparation','files':payload},indent=2,ensure_ascii=False)+'\n').encode('utf-8')
    output=Path('handoff/vlm46a-test-preparation-20261112-a.zip')
    if output.exists():raise FileExistsError(output)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(set(paths)):z.write(p,p.as_posix())
        z.writestr('README_HANDOFF.txt',readme)
        z.writestr('MANIFEST_SHA256.json',manifest)
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
        for name,entry in payload.items():
            assert hashlib.sha256(z.read(name)).hexdigest()==entry['sha256']
    checksum=sha256_file(output)
    output.with_suffix('.manifest.json').write_bytes(manifest)
    output.with_suffix('.zip.sha256').write_text(checksum+'  '+output.name+'\n',encoding='ascii')
    print(json.dumps({'path':output.as_posix(),'sha256':checksum,'bytes':output.stat().st_size,'files':len(payload)}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['after','package'])
    args=p.parse_args()
    after() if args.command=='after' else package()
