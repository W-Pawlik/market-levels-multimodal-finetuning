"""Real torch/PEFT CPU checks for final runtime; no Qwen, CUDA or production inputs."""
import os
os.environ['CUDA_VISIBLE_DEVICES']=''
os.environ['HF_HUB_OFFLINE']='1'
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch
_cpu_available = patch.object(torch.cuda,'is_available',return_value=False)
_cpu_init = patch.object(torch.cuda,'_lazy_init',side_effect=AssertionError('CPU fixture must not initialize CUDA'))
_cpu_available.start()
_cpu_init.start()
from peft import LoraConfig, get_peft_model
from safetensors.torch import load_file
from PIL import Image

from market_levels.inference.io.final_model import FinalModel, attach_adapter
from market_levels.inference.domain.inputs import ImageInput


class SmallBase(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.layers=torch.nn.ModuleList([torch.nn.ModuleDict({'q_proj':torch.nn.Linear(4,4),'v_proj':torch.nn.Linear(4,4)}) for _ in range(28)])


class CpuRuntimeTests(unittest.TestCase):
    def test_actual_peft_readonly_reload_matches_112_tensors(self):
        torch.manual_seed(12)
        model=get_peft_model(SmallBase(),LoraConfig(r=2,lora_alpha=4,target_modules=['q_proj','v_proj']))
        with torch.no_grad():
            for n,p in model.named_parameters():
                if 'lora_' in n:p.add_(.125)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'adapter';model.save_pretrained(folder)
            reloaded,report=attach_adapter(SmallBase(),folder,torch)
            self.assertTrue(report['tensor_values_exact']);self.assertEqual(report['tensor_count'],112)
            self.assertFalse(any(p.requires_grad for p in reloaded.parameters()))
            self.assertEqual(len(load_file(str(folder/'adapter_model.safetensors'))),112)

    def test_eval_no_gradient_no_base_adapter_historical_decoding(self):
        class Model(torch.nn.Module):
            def __init__(self):
                super().__init__();self.weight=torch.nn.Parameter(torch.ones(1));self.config=SimpleNamespace(use_cache=False)
                self.generation_config=SimpleNamespace(to_dict=lambda:{})
            def generate(inner,**kwargs):
                self.assertFalse(torch.is_grad_enabled());self.assertTrue(torch.is_inference_mode_enabled())
                self.assertFalse(inner.training);self.assertFalse(inner.weight.requires_grad)
                self.assertEqual(kwargs['max_new_tokens'],256)
                return torch.tensor([[1,2,3]])
        class Monitor:
            result={'seconds':.01}
            def __init__(self,*args):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
        class Batch(dict):
            def to(inner,device):
                self.assertEqual(device,'cuda:0');return inner
        decoder=SimpleNamespace(batch_decode=lambda *a,**kw:[' \n```json\n{}\n```\t'])
        processor=SimpleNamespace(**vars(decoder),to_dict=lambda:{},image_processor=SimpleNamespace(to_dict=lambda:{}),tokenizer=SimpleNamespace(init_kwargs={}))
        cuda=SimpleNamespace(device_count=lambda:1,get_device_name=lambda n:'fixture-gpu',is_bf16_supported=lambda **kw:True)
        proxy=SimpleNamespace(cuda=cuda,inference_mode=torch.inference_mode)
        config={'runtime':{'seed':12,'generation':{'do_sample':False,'num_beams':1,'max_new_tokens':256,'use_cache':True},
            'min_pixels':65536,'image_budgets':{'native':786432},'models':{'qwen3-vl':{}}},'resources':{'required_gpu':'fixture-gpu',
            'minimum_ram_mib':4096,'minimum_commit_headroom_mib':8192}}
        memory={'available_ram_mib':8192,'commit_headroom_mib':16384}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'training-identity.json').write_text(json.dumps({'environment':{},'processor':{},'image_processor':{},'tokenizer':{}}))
            image=root/'image.png';Image.new('RGB',(1024,768)).save(image)
            selection={'selected_adapter':str(root)}
            target='market_levels.inference.io.final_model.'
            from contextlib import ExitStack
            with ExitStack() as stack:
                for name,value in [('guard',lambda c:{}),('environment',lambda:{}),('setup',lambda s:proxy),
                    ('local_checkpoint',lambda *a:root),('load_model',lambda *a,**kw:(proxy,Model(),processor,{})),
                    ('prepare_nf4',lambda m,t:m),('set_resolution',lambda *a:None),('snapshot',lambda *a:memory),('Monitor',Monitor),
                    ('prepare_input',lambda *a:(Batch(input_ids=torch.tensor([[1,2]])),{'processed_width':1024,'processed_height':768,'image_tokens':768}))]:
                    stack.enter_context(patch(target+name,value))
                adapter=stack.enter_context(patch(target+'attach_adapter'))
                with FinalModel(config,selection,'base-nf4') as backend:
                    response,info=backend.generate(ImageInput('synthetic',image,'instruction'))
                    self.assertEqual(response,' \n```json\n{}\n```\t')
                adapter.assert_not_called()
        self.assertFalse(torch.cuda.is_initialized())


if __name__=='__main__':unittest.main(verbosity=2)
