"""Explicit VLM-environment CPU state/RNG integration and GPU checkpoint comparison."""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path


def compare(left, right, atol=0.0, rtol=0.0):
    import numpy as np
    import torch
    if isinstance(left, torch.Tensor):
        return left.shape == right.shape and bool(torch.allclose(left, right, atol=atol, rtol=rtol))
    if isinstance(left, np.ndarray):
        return bool(np.array_equal(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(compare(left[k], right[k], atol, rtol) for k in left)
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(compare(a,b,atol,rtol) for a,b in zip(left,right))
    return left == right


def compare_checkpoints(a: Path, b: Path, output: Path):
    import torch
    from safetensors.torch import load_file
    from market_levels.training.io.checkpoints import checkpoint_metadata
    checkpoint_metadata(a)
    checkpoint_metadata(b)
    x, y = (torch.load(p / 'state.pt', map_location='cpu', weights_only=False) for p in (a,b))
    left, right = (load_file(str(p / 'adapter/adapter_model.safetensors')) for p in (a,b))
    cursor = ('epoch', 'position', 'order', 'global_step', 'processed_examples', 'input_tokens', 'supervised_tokens')
    atol, rtol = 1e-6, 1e-5
    report = {'adapter_exact': compare(left,right), 'adapter_allclose': compare(left,right,atol,rtol),
        'adapter_max_abs_diff': max(float((left[k]-right[k]).abs().max()) for k in left),
        'optimizer_exact': compare(x['optimizer'],y['optimizer']),
        'optimizer_allclose': compare(x['optimizer'],y['optimizer'],atol,rtol),
        'scheduler_exact': compare(x['scheduler'],y['scheduler']),
        'sampler_exact': all(compare(x['sampler'][k],y['sampler'][k]) for k in cursor),
        'rng_exact': compare(x['rng'], y['rng']), 'atol': atol, 'rtol': rtol,
        'left': str(a), 'right': str(b)}
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    if not all(report[k] for k in ('adapter_allclose', 'optimizer_allclose', 'scheduler_exact', 'sampler_exact', 'rng_exact')):
        raise ValueError('Resume comparison outside declared tolerance')


def cpu_worker(output, resume=None, limit=3):
    import numpy as np
    import torch
    from transformers import LlamaConfig, LlamaForCausalLM
    from peft import LoraConfig, get_peft_model
    from market_levels.training.io.checkpoints import save_checkpoint, load_checkpoint
    from market_levels.training.domain.schedule import initial_state, next_group, advance
    torch.set_num_threads(1)
    torch.manual_seed(17)
    random.seed(17)
    np.random.seed(17)
    model = get_peft_model(LlamaForCausalLM(LlamaConfig(vocab_size=32, hidden_size=16, intermediate_size=24,
        num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=2, attention_dropout=0.1)),
        LoraConfig(r=2, lora_alpha=4, lora_dropout=0.1, target_modules=['q_proj','v_proj'], task_type='CAUSAL_LM'))
    model.train()
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=.001)
    scheduler = torch.optim.lr_scheduler.LinearLR(optimizer, start_factor=1, end_factor=.1, total_iters=3)
    ids = ['a','b','c','d','e']
    settings = {'seed':17, 'gradient_accumulation':2}
    state = initial_state(ids, settings)
    identity = {'test': 'CPU tiny Llama PEFT; not Qwen/GPU', 'seed':17}
    if resume:
        state = load_checkpoint(torch, resume, identity, model, optimizer, scheduler)
    order = []
    for _ in range(limit):
        group = next_group(state, settings)
        optimizer.zero_grad(set_to_none=True)
        for name in group:
            offset = (int(random.random()*5) + int(np.random.randint(5))) % 10
            tokens = torch.randint(0, 20, (1,6)) + offset
            loss = model(input_ids=tokens, labels=tokens).loss
            (loss / len(group)).backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(),1,error_if_nonfinite=True)
        optimizer.step()
        scheduler.step()
        optimizer.zero_grad(set_to_none=True)
        advance(state,ids,settings,len(group))
        order.extend(group)
    output.mkdir(parents=True,exist_ok=False)
    save_checkpoint(torch,model,optimizer,scheduler,state,identity,output/'checkpoints')
    (output/'order.json').write_text(json.dumps(order),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('cpu','worker','compare'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resume',type=Path)
    parser.add_argument('--limit',type=int,default=3)
    parser.add_argument('--left',type=Path)
    parser.add_argument('--right',type=Path)
    args=parser.parse_args()
    if args.command=='worker':
        cpu_worker(args.output,args.resume,args.limit)
    elif args.command=='compare':
        compare_checkpoints(args.left,args.right,args.output)
    else:
        args.output.mkdir(parents=True,exist_ok=False)
        for name,limit,resume in [('a',3,None),('b1',1,None),('b2',2,args.output/'b1/checkpoints/step-000001')]:
            command=[sys.executable,'-X','utf8',__file__,'worker','--output',str(args.output/name),'--limit',str(limit)]
            if resume:
                command+=['--resume',str(resume)]
            subprocess.run(command,check=True)
        compare_checkpoints(args.output/'a/checkpoints/step-000003',args.output/'b2/checkpoints/step-000003',args.output/'comparison.json')
        a=json.loads((args.output/'a/order.json').read_text())
        b=json.loads((args.output/'b1/order.json').read_text())+json.loads((args.output/'b2/order.json').read_text())
        if a!=b:
            raise ValueError('Different example order')


if __name__=='__main__':
    main()
