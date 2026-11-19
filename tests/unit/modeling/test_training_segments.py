"""CPU-free checks of the approved experiment's process boundaries."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from market_levels.cli.train_vlm import main
from market_levels.shared.configuration import read_configuration
from market_levels.training.config import load_config
from market_levels.training.domain.schedule import initial_state, total_steps, lr_multiplier
from market_levels.training.io.events import Events
from market_levels.training.workflows.pipeline import train_loop
from unit.modeling.test_training_pipeline import FakeBackend


class TrainingSegmentTests(unittest.TestCase):
    def test_approved_copy_changes_only_approval(self):
        original = read_configuration(Path('configs/vlm/training.json'))
        self.assertFalse(original['pipeline']['full_approved'])
        original['pipeline']['full_approved'] = True
        approved = read_configuration(Path('configs/vlm/training-approved-local.json'))
        self.assertEqual(original, approved)
        self.assertNotIn('$file', json.dumps(approved))

    def test_25_then_175_then_350_preserves_order_and_plan(self):
        settings = load_config(Path('configs/vlm/training-approved-local.json'))['pipeline']
        ids = [str(i) for i in range(698)]
        before = copy.deepcopy(settings)
        state = initial_state(ids, settings)
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            events = Events(Path(temp) / 'events.jsonl')
            self.assertEqual(train_loop(settings, ids, state, backend, events, lambda: False, 25), 'stopped')
            self.assertEqual((state['global_step'], state['processed_examples']), (25, 100))
            self.assertEqual(len(backend.groups), 25)
            self.assertEqual(backend.saved[-1], state)
            restored = json.loads(json.dumps(backend.saved[-1]))
            # One resumed process step is global step 26, not a replay of 25.
            self.assertEqual(train_loop(settings, ids, restored, backend, events, lambda: False, 1), 'stopped')
            self.assertEqual((restored['global_step'], restored['processed_examples']), (26, 104))
            self.assertEqual(train_loop(settings, ids, restored, backend, events, lambda: False), 'validation_due')
            self.assertEqual((restored['global_step'], restored['processed_examples']), (175, 698))
            self.assertEqual(train_loop(settings, ids, restored, backend, events, lambda: False), 'complete')
            self.assertEqual((restored['global_step'], restored['processed_examples']), (350, 1396))
            reference = FakeBackend()
            continuous = initial_state(ids, settings)
            while continuous['global_step'] < 350:
                train_loop(settings, ids, continuous, reference, events, lambda: False)
            self.assertEqual(backend.groups, reference.groups)
            steps = [json.loads(s)['step'] for s in events.path.read_text().splitlines()]
            self.assertEqual(steps[:26], list(range(1, 27)))
        self.assertEqual(settings, before)
        self.assertEqual(total_steps(698, settings), 350)
        self.assertAlmostEqual(lr_multiplier(25, 350, 18, 'linear'), 325 / 332)

    def test_cli_returns_actual_workflow_exit_codes_without_training(self):
        for code in (0, 1, 3):
            with self.subTest(code=code), patch('market_levels.cli.train_vlm.run_training', return_value=code) as run:
                self.assertEqual(main(['full', '--config', 'configs/vlm/training-approved-local.json',
                                       '--output', 'unused', '--approve-full-training', '--stop-after', '25']), code)
                self.assertEqual(run.call_args.args[-1], 25)

    def test_approved_copy_still_requires_explicit_flag(self):
        with patch('market_levels.cli.train_vlm.run_training') as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['full', '--config', 'configs/vlm/training-approved-local.json',
                                   '--output', 'unused', '--stop-after', '25']), 1)
            run.assert_not_called()

    def test_step_terminal_and_json_include_required_measurements(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()) as terminal:
            events = Events(Path(temp) / 'events.jsonl')
            events.emit('step', epoch=1, step=25, total_steps=350, processed_examples=100,
                        seconds=1.2, elapsed_seconds=50, loss=1.0, learning_rate=.0001,
                        memory={'used_vram_mib':7000, 'allocated_mib':5000, 'reserved_mib':7500,
                                'rss_mib':2000, 'available_ram_mib':5000, 'commit_headroom_mib':10000})
            self.assertEqual(json.loads(events.path.read_text())['processed_examples'], 100)
            for label in ('epoch=1', 'step=25/350', 'examples=100', 'loss=', 'lr=', 'step_s=',
                          'elapsed_s=', 'VRAM=', 'alloc/res=', 'RSS=', 'RAM_free=', 'commit_free='):
                self.assertIn(label, terminal.getvalue())
