"""Compare trusted local optimizer/scheduler/RNG checkpoint states on CPU only.

Uses the existing VLM Python environment. Does not load Qwen or initialize CUDA.
"""
import json
import os
from pathlib import Path

os.environ['CUDA_VISIBLE_DEVICES'] = ''
import torch
import numpy as np


def equal(a, b):
    if isinstance(a, torch.Tensor):
        return isinstance(b, torch.Tensor) and a.dtype == b.dtype and a.shape == b.shape and torch.equal(a,b)
    if isinstance(a, np.ndarray):
        return isinstance(b,np.ndarray) and np.array_equal(a,b)
    if isinstance(a, dict):
        return isinstance(b,dict) and a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple)):
        return type(a)==type(b) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    return type(a)==type(b) and a==b


def main():
    pairs=[('vlm43-part1-14789-1679','vlm43-part2-17032-13034',25),
           ('vlm43-part2-17032-13034','vlm43-part3-2708-16743',175),
           ('vlm44-part1-24755-21138','vlm44-part2-17554-5354',25)]
    results=[]
    for before,after,step in pairs:
        a=Path('results')/before/f'checkpoints/step-{step:06d}/state.pt'
        b=Path('results')/after/f'checkpoints/step-{step:06d}/state.pt'
        # Only the author's local, manifest-verified checkpoints are deserialized.
        x=torch.load(a,map_location='cpu',weights_only=False)
        y=torch.load(b,map_location='cpu',weights_only=False)
        elapsed={'source':x['sampler']['elapsed_seconds'],'restored':y['sampler']['elapsed_seconds']}
        assert elapsed['restored']>=elapsed['source']
        x['sampler'].pop('elapsed_seconds');y['sampler'].pop('elapsed_seconds')
        checks={k:equal(x[k],y[k]) for k in x}
        assert x.keys()==y.keys() and all(checks.values()),checks
        results.append({'source':a.as_posix(),'restored':b.as_posix(),'exact_except_elapsed_setup_time':checks,
                        'elapsed_setup_time':elapsed})
    assert not torch.cuda.is_initialized()
    initial=torch.load('results/vlm44-part1-24755-21138/checkpoints/step-000000/state.pt',map_location='cpu',weights_only=False)
    parent=torch.load('results/vlm43-part3-2708-16743/checkpoints/step-000350/state.pt',map_location='cpu',weights_only=False)
    assert not initial['optimizer']['state'] and parent['optimizer']['state']
    assert initial['sampler']['global_step']==0 and initial['sampler']['processed_examples']==0
    assert initial['scheduler']['last_epoch']==0
    assert not equal(initial['rng'],parent['rng'])
    output={'pairs':results,'cuda_initialized':False,'qwen_loaded':False,
            'extra_stage_initial_optimizer_empty':True,'extra_stage_initial_scheduler_last_epoch':0,
            'extra_stage_rng_differs_from_parent':True,'extra_stage_initial_step':0}
    Path('results/vlm45-final-audit-20261111-a/cpu-states.json').write_text(
        json.dumps(output,indent=2)+'\n',encoding='utf-8')
    print('CPU: all optimizer/scheduler/RNG states exactly equal at 3 resume boundaries; CUDA not initialized')


if __name__=='__main__':
    main()
