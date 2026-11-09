"""Run explicitly with the isolated VLM Python; no GPU or model download needed."""
import unittest

import torch

from market_levels.training.domain.masking import assistant_labels


class AssistantMaskingTests(unittest.TestCase):
    def test_image_instruction_and_roles_masked_answer_and_eos_retained(self):
        prompt = torch.tensor([[151644, 151655, 151655, 90, 91, 151645, 151644]])
        sequence = torch.cat((prompt, torch.tensor([[12, 13, 14, 151645]])), dim=-1)
        labels = assistant_labels(sequence, prompt)
        self.assertTrue(torch.all(labels[:, :prompt.shape[-1]] == -100))
        self.assertTrue(torch.equal(labels[:, prompt.shape[-1]:], sequence[:, prompt.shape[-1]:]))
        self.assertFalse(torch.any(labels == 151655))
        self.assertEqual(int(labels[0, -1]), 151645)
        self.assertTrue(torch.equal(sequence[:, :prompt.shape[-1]], prompt))

    def test_different_template_prefix_rejected(self):
        with self.assertRaises(ValueError):
            assistant_labels(torch.tensor([[1, 8, 3, 4]]), torch.tensor([[1, 2, 3]]))

    def test_missing_answer_refused(self):
        with self.assertRaises(ValueError):
            assistant_labels(torch.tensor([[1, 2, 3]]), torch.tensor([[1, 2, 3]]))


if __name__ == '__main__':
    unittest.main()
