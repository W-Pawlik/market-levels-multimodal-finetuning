"""Explicit CPU autograd checks for the production microbatch accumulation path."""
import contextlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch

from market_levels.training.workflows.pipeline import TorchBackend
from market_levels.training.io.events import Events


class Batch(dict):
    def to(self, device):
        return self


class Model(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.tensor(.25))

    def forward(self, x, target, use_cache=False):
        return SimpleNamespace(loss=((self.weight * x - target) ** 2).mean())


class AccumulationTests(unittest.TestCase):
    def run_group(self, lengths):
        with tempfile.TemporaryDirectory() as temp:
            model, expected = Model(), Model()
            optimizer = torch.optim.AdamW(model.parameters(), lr=.01)
            opt_expected = torch.optim.AdamW(expected.parameters(), lr=.01)
            scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda _: 1.0)
            fake_torch = SimpleNamespace(autocast=lambda *a, **k: contextlib.nullcontext(), bfloat16=torch.bfloat16,
                isfinite=torch.isfinite, nn=torch.nn, cuda=SimpleNamespace(synchronize=lambda: None,
                                                                          memory_reserved=lambda: 0))
            tensors = {str(i): (torch.arange(1,n+1).float() / 10, torch.ones(n)/10) for i,n in enumerate(lengths)}
            rows = {k: {'id': k} for k in tensors}
            def batch(row, *args):
                x,y = tensors[row['id']]
                return Batch(x=x,target=y), {'input_tokens':len(x), 'supervised_tokens':len(y)}
            backend = TorchBackend(fake_torch,model,None,optimizer,scheduler,rows,
                {'runtime':{'dataset':'unused'},'pipeline':{'max_sequence_tokens':2048,'empty_cache_reserved_mib':0}},
                {},Path(temp),Events(Path(temp)/'events.jsonl'))
            with patch('market_levels.training.workflows.pipeline.make_batch',side_effect=batch):
                stats = backend._step(list(rows))
            expected_loss = torch.stack([expected(x=x,target=y).loss for x,y in tensors.values()]).mean()
            expected_loss.backward()
            torch.nn.utils.clip_grad_norm_(expected.parameters(),1.0,error_if_nonfinite=True)
            opt_expected.step()
            self.assertTrue(torch.equal(model.weight,expected.weight))
            self.assertAlmostEqual(stats['loss'],float(expected_loss.detach()),places=7)
            self.assertTrue(all(p.grad is None for p in model.parameters()))

    def test_four_examples_have_equal_weight_despite_different_token_counts(self):
        self.run_group([1,2,4,7])

    def test_singleton_tail_uses_full_loss(self):
        self.run_group([3])

    def test_two_example_tail_is_not_divided_by_four(self):
        self.run_group([2,7])

    def test_nonfinite_loss_does_not_update_weights(self):
        with tempfile.TemporaryDirectory() as temp:
            model = Model()
            optimizer = torch.optim.AdamW(model.parameters(),lr=.01)
            fake_torch = SimpleNamespace(autocast=lambda *a, **k: contextlib.nullcontext(),
                bfloat16=torch.bfloat16,isfinite=torch.isfinite)
            backend = TorchBackend(fake_torch,model,None,optimizer,None,{'a':{}},
                {'runtime':{'dataset':'unused'},'pipeline':{'max_sequence_tokens':2048}},
                {},Path(temp),None)
            with patch('market_levels.training.workflows.pipeline.make_batch',return_value=(
                    Batch(x=torch.tensor(float('nan')),target=torch.tensor(1)),{})):
                with self.assertRaisesRegex(ValueError,'NaN/Inf'):
                    backend._step(['a'])
            self.assertEqual(float(model.weight.detach()),.25)
            self.assertFalse(optimizer.state)


if __name__ == '__main__':
    unittest.main()
