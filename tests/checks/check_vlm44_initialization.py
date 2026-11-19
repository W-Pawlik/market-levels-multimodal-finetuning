"""Explicit PEFT CPU tests for new-weight initialization and exact local resume."""
import contextlib
import copy
import io
import json
import random
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch
from peft import LoraConfig, get_peft_model
from safetensors.torch import load_file, save_file

from market_levels.modeling.io.adapter_check import adapter_state
from market_levels.shared.integrity import sha256_file
from market_levels.shared.manifests import seal
from market_levels.training.config import load_config
from market_levels.training.domain.schedule import initial_state, lr_multiplier
from market_levels.training.io.checkpoints import save_checkpoint, load_checkpoint, export_adapter, checkpoint_metadata
from market_levels.training.io.events import Events
from market_levels.training.io.initialization import load_initial_adapter, verify_parent
from market_levels.training.workflows.pipeline import train_loop


class Tiny(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.q_proj = torch.nn.Linear(2, 2)

    def forward(self, x):
        return self.q_proj(x)


def build():
    torch.manual_seed(123)
    return get_peft_model(Tiny(), LoraConfig(r=1, lora_alpha=2, target_modules=['q_proj']))


class CPUBackend:
    def __init__(self, model, optimizer, scheduler, root, identity):
        self.model, self.optimizer, self.scheduler = model, optimizer, scheduler
        self.root, self.identity = root, identity
        self.groups = []

    def step(self, group):
        self.groups.append(list(group))
        losses=[]
        for _ in group:
            x=torch.rand(2,2)+random.random()+float(np.random.random())
            loss=self.model(x).square().mean()
            losses.append(float(loss.detach()))
            (loss/len(group)).backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(),1.0,error_if_nonfinite=True)
        lr=self.optimizer.param_groups[0]['lr']
        self.optimizer.step(); self.scheduler.step(); self.optimizer.zero_grad(set_to_none=True)
        return {'loss':sum(losses)/len(losses),'learning_rate':lr,'input_tokens':len(group)*2,'supervised_tokens':len(group)}

    def memory(self):
        return {'available_ram_mib':10000,'commit_headroom_mib':20000,'rss_mib':100}

    def save(self,state):
        self.latest=save_checkpoint(torch,self.model,self.optimizer,self.scheduler,state,self.identity,self.root)


class InitializationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.cuda=patch.object(torch.cuda,'is_available',return_value=False)
        self.cuda.start(); self.addCleanup(self.cuda.stop)
        torch.set_num_threads(1)

    def equal(self,a,b):
        if isinstance(a,torch.Tensor): self.assertTrue(torch.equal(a,b))
        elif isinstance(a,dict):
            self.assertEqual(a.keys(),b.keys())
            for k in a: self.equal(a[k],b[k])
        elif isinstance(a,(list,tuple)):
            self.assertEqual(len(a),len(b))
            for x,y in zip(a,b): self.equal(x,y)
        else: self.assertEqual(a,b)

    def test_real_parent_112_tensors_verified_without_reading_state_pt(self):
        config=load_config(Path('configs/vlm/extra-epoch-approved-local.json'))
        with patch.object(torch,'load',side_effect=AssertionError('parent state.pt must never be loaded')):
            result=verify_parent(config)
        self.assertEqual(result['tensor_count'],112)
        self.assertEqual(result['trainable_parameters'],1605632)
        self.assertTrue(result['parent_tensor_values_exact'])

    def test_resealed_parent_tensor_change_rejected(self):
        config=load_config(Path('configs/vlm/extra-epoch-approved-local.json'))
        copied=self.root/'parent-checkpoint'
        shutil.copytree(config['extra_epoch']['parent_checkpoint'],copied)
        file=copied/'adapter/adapter_model.safetensors'
        values=load_file(str(file)); values[next(iter(values))].view(-1)[0]+=1
        save_file(values,str(file))
        # Only temporary copied manifests are removed and rebuilt for tampering tests.
        (copied/'manifest.json').unlink(); (copied/'manifest.sha256').unlink()
        seal(copied,{'kind':'vlm_training_checkpoint','schema':1,'status':'complete'})
        config['extra_epoch']['parent_checkpoint']=str(copied)
        config['extra_epoch']['parent_checkpoint_manifest_sha256']=sha256_file(copied/'manifest.json')
        with self.assertRaisesRegex(ValueError,'tensor values differ'): verify_parent(config)

    def test_new_optimizer_and_exact_resume25_to175(self):
        source=build()
        old_optimizer=torch.optim.AdamW([p for p in source.parameters() if p.requires_grad],lr=.01)
        source(torch.ones(2,2)).square().mean().backward()
        old_optimizer.step(); old_optimizer.zero_grad(set_to_none=True)
        self.assertTrue(old_optimizer.state)
        export_adapter(source,self.root/'source',{'test':'parent-weights-only'})
        original_hash=sha256_file(self.root/'source/adapter_model.safetensors')
        settings=load_config(Path('configs/vlm/extra-epoch-approved-local.json'))['pipeline']
        ids=[str(i) for i in range(698)]
        identity={'provenance':{'parent_checkpoint_step':350,'parent_adapter_sha256':original_hash,
                               'optimizer_state':'new','scheduler_state':'new','additional_epochs':1}}

        def fresh(name):
            model=build()
            base_before={k:v.detach().clone() for k,v in model.named_parameters() if 'lora_' not in k}
            info=load_initial_adapter(torch,model,self.root/'source',original_hash)
            self.assertTrue(info['tensor_values_exact'])
            self.equal(adapter_state(source),adapter_state(model))
            self.equal(base_before,{k:v.detach() for k,v in model.named_parameters() if 'lora_' not in k})
            opt=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=.00005)
            sched=torch.optim.lr_scheduler.LambdaLR(opt,lambda n:lr_multiplier(n,175,9,'linear'))
            self.assertFalse(opt.state)
            self.assertEqual(sched.last_epoch,0)
            random.seed(20261112); np.random.seed(20261112); torch.manual_seed(20261112)
            backend=CPUBackend(model,opt,sched,self.root/name,identity)
            state=initial_state(ids,settings)
            backend.save(state)
            return backend,state

        with contextlib.redirect_stdout(io.StringIO()):
            a,sa=fresh('continuous')
            self.assertEqual(train_loop(settings,ids,sa,a,Events(self.root/'a.jsonl'),lambda:False),'complete')
            expected_rng=(random.random(),float(np.random.random()),torch.rand(3))
            b,sb=fresh('part1')
            self.assertEqual(train_loop(settings,ids,sb,b,Events(self.root/'b.jsonl'),lambda:False,25),'stopped')
            meta=checkpoint_metadata(b.latest)
            self.assertEqual(meta['additional_optimizer_steps'],25)
            self.assertEqual(meta['total_training_examples_seen_in_new_stage'],100)
            saved_opt=copy.deepcopy(b.optimizer.state_dict())
            saved_sched=copy.deepcopy(b.scheduler.state_dict())
            # Fresh process analogue: a new model, optimizer and scheduler. Only
            # the local checkpoint is read; the source initializer must not run.
            model=build()
            opt=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=.00005)
            sched=torch.optim.lr_scheduler.LambdaLR(opt,lambda n:lr_multiplier(n,175,9,'linear'))
            with patch('market_levels.training.io.initialization.load_initial_adapter',side_effect=AssertionError('must not reinitialize')):
                restored=load_checkpoint(torch,b.latest,identity,model,opt,sched)
            self.equal(saved_opt,opt.state_dict()); self.equal(saved_sched,sched.state_dict())
            c=CPUBackend(model,opt,sched,self.root/'part2',identity)
            self.assertEqual(train_loop(settings,ids,restored,c,Events(self.root/'c.jsonl'),lambda:False),'complete')
            self.assertEqual((restored['global_step'],restored['processed_examples']),(175,698))
            self.equal(adapter_state(a.model),adapter_state(c.model))
            self.equal(a.optimizer.state_dict(),c.optimizer.state_dict())
            self.equal(a.scheduler.state_dict(),c.scheduler.state_dict())
            self.equal(expected_rng,(random.random(),float(np.random.random()),torch.rand(3)))
            self.assertEqual(a.groups,b.groups+c.groups)
            self.assertEqual(len(c.groups[-1]),2)
            self.assertEqual(c.scheduler.get_last_lr(),[0.0])
        self.assertEqual(sha256_file(self.root/'source/adapter_model.safetensors'),original_hash)

    def test_model_tensor_mismatch_and_changed_hash_rejected(self):
        model=build(); source=self.root/'source'; export_adapter(model,source,{})
        sha=sha256_file(source/'adapter_model.safetensors')
        with self.assertRaisesRegex(ValueError,'changed'): load_initial_adapter(torch,model,source,'0'*64)
        values=load_file(str(source/'adapter_model.safetensors'))
        values.pop(next(iter(values)))
        save_file(values,str(source/'adapter_model.safetensors'))
        with self.assertRaisesRegex(ValueError,'keys/shapes'): load_initial_adapter(torch,model,source,sha256_file(source/'adapter_model.safetensors'))


if __name__=='__main__':
    unittest.main()
