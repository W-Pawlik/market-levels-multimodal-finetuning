"""Explicit CPU-only full-checkpoint test; no Qwen, datasets or GPU context."""
import copy
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch
from peft import LoraConfig, get_peft_model

from market_levels.modeling.io.adapter_check import adapter_state
from market_levels.training.domain.schedule import initial_state, advance, lr_multiplier
from market_levels.training.io.checkpoints import save_checkpoint, load_checkpoint, checkpoint_metadata


class Tiny(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.q_proj = torch.nn.Linear(2, 2)

    def forward(self, x):
        return self.q_proj(x)


class ResumeTests(unittest.TestCase):
    def test_checkpoint25_restores_adam_scheduler_rng_and_step26_exactly(self):
        def build():
            torch.manual_seed(123)
            model = get_peft_model(Tiny(), LoraConfig(r=1, lora_alpha=2, target_modules=['q_proj']))
            opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=.0002)
            sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: lr_multiplier(s,350,18,'linear'))
            return model, opt, sched

        def step(model, opt, sched):
            x = torch.rand(2,2) + random.random() + float(np.random.random())
            model(x).square().mean().backward()
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)

        def equal(a,b):
            if isinstance(a,torch.Tensor):
                self.assertTrue(torch.equal(a,b))
            elif isinstance(a,dict):
                self.assertEqual(a.keys(),b.keys())
                for k in a: equal(a[k],b[k])
            elif isinstance(a,(list,tuple)):
                self.assertEqual(len(a),len(b))
                for x,y in zip(a,b): equal(x,y)
            else: self.assertEqual(a,b)

        random.seed(20261110)
        np.random.seed(20261110)
        a,oa,sa = build()
        settings={'seed':20261110,'gradient_accumulation':4}
        ids=[str(i) for i in range(698)]
        state=initial_state(ids,settings)
        for _ in range(25):
            step(a,oa,sa)
            advance(state,ids,settings,4)
        with tempfile.TemporaryDirectory() as temp, patch.object(torch.cuda,'is_available',return_value=False):
            ckpt=save_checkpoint(torch,a,oa,sa,state,{'cpu_test':True},Path(temp))
            self.assertEqual(ckpt.name,'step-000025')
            self.assertEqual(checkpoint_metadata(ckpt)['sampler']['processed_examples'],100)
            saved_opt=copy.deepcopy(oa.state_dict())
            saved_sched=copy.deepcopy(sa.state_dict())
            step(a,oa,sa)
            expected_rng=(random.random(),float(np.random.random()),torch.rand(2))
            b,ob,sb=build()
            restored=load_checkpoint(torch,ckpt,{'cpu_test':True},b,ob,sb)
            equal(ob.state_dict(),saved_opt)
            equal(sb.state_dict(),saved_sched)
            self.assertEqual(sb.last_epoch,25)
            step(b,ob,sb)
            advance(restored,ids,settings,4)
            self.assertEqual((restored['global_step'],restored['processed_examples']),(26,104))
            equal(adapter_state(a),adapter_state(b))
            equal(oa.state_dict(),ob.state_dict())
            equal(sa.state_dict(),sb.state_dict())
            equal(expected_rng,(random.random(),float(np.random.random()),torch.rand(2)))


if __name__ == '__main__':
    unittest.main()
