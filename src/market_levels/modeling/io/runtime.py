"""Lazy ML imports, GPU-only loading and separately timed measurements."""
from __future__ import annotations

import importlib.metadata
import os
import platform
import subprocess
import threading
import time


def setup(seed: int):
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'
    import torch
    torch.set_num_threads(6)
    torch.manual_seed(seed)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA niedostępna w PyTorch; brak automatycznego fallbacku CPU')
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    return torch


def environment() -> dict:
    packages = {}
    for name in ('torch', 'torchvision', 'transformers', 'peft', 'accelerate', 'bitsandbytes', 'pillow', 'psutil', 'numpy', 'huggingface-hub', 'safetensors', 'tokenizers'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {'python': platform.python_version(), 'platform': platform.platform(), 'packages': packages}


def gpu_snapshot(torch) -> dict:
    import psutil
    free, total = torch.cuda.mem_get_info()
    return {'allocated_bytes': torch.cuda.memory_allocated(), 'reserved_bytes': torch.cuda.memory_reserved(),
            'cuda_free_bytes': free, 'cuda_total_bytes': total, 'process_rss_bytes': psutil.Process().memory_info().rss,
            'system_available_ram_bytes': psutil.virtual_memory().available}


class Monitor:
    """Sample global nvidia-smi VRAM and process RSS; PyTorch tracks allocator peaks."""
    def __init__(self, torch):
        self.torch = torch
        self.stop = threading.Event()
        self.samples = []

    def _sample(self):
        import psutil
        process = psutil.Process()
        while not self.stop.is_set():
            row = {'seconds': time.perf_counter() - self.start, 'rss_bytes': process.memory_info().rss}
            try:
                output = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used,memory.free,utilization.gpu',
                                                   '--format=csv,noheader,nounits'], text=True, timeout=5)
                used, free, util = [int(s.strip()) for s in output.splitlines()[0].split(',')]
                row.update(vram_used_mib=used, vram_free_mib=free, utilization_percent=util)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                row['sampling_error'] = str(error)
            self.samples.append(row)
            self.stop.wait(0.4)

    def __enter__(self):
        self.torch.cuda.synchronize()
        self.torch.cuda.reset_peak_memory_stats()
        self.before = gpu_snapshot(self.torch)
        self.start = time.perf_counter()
        self.thread = threading.Thread(target=self._sample, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.torch.cuda.synchronize()
        self.elapsed = time.perf_counter() - self.start
        self.stop.set()
        self.thread.join(timeout=6)
        self.result = {'seconds': self.elapsed, 'before': self.before, 'after': gpu_snapshot(self.torch),
                       'peak_allocated_bytes': self.torch.cuda.max_memory_allocated(),
                       'peak_reserved_bytes': self.torch.cuda.max_memory_reserved(), 'samples': self.samples}


def load_model(config: dict, key: str, path, *, quantized: bool = False):
    import transformers
    torch = setup(config['seed'])
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported(including_emulation=False) else torch.float16
    options = {'local_files_only': True, 'trust_remote_code': False, 'dtype': dtype,
               'device_map': {'': 'cuda:0'}, 'attn_implementation': 'sdpa'}
    if quantized:
        options['quantization_config'] = transformers.BitsAndBytesConfig(load_in_4bit=True,
            bnb_4bit_quant_type='nf4', bnb_4bit_compute_dtype=dtype, bnb_4bit_use_double_quant=True,
            llm_int8_skip_modules=['model.visual', 'lm_head'])
    with Monitor(torch) as loading:
        model = getattr(transformers, config['models'][key]['architecture']).from_pretrained(path, **options)
    processor_start = time.perf_counter()
    processor = transformers.AutoProcessor.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    devices = sorted({str(p.device) for p in model.parameters()})
    device_map = {str(k): str(v) for k, v in getattr(model, 'hf_device_map', {'all_parameters': ','.join(devices)}).items()}
    details = {'model_load': loading.result, 'processor_load_seconds': time.perf_counter() - processor_start,
               'dtype': str(dtype), 'quantized_nf4': quantized,
               'device_map': device_map, 'parameter_devices': devices,
               'processor_class': type(processor).__name__, 'image_processor_class': type(processor.image_processor).__name__,
               'processor': processor.to_dict(), 'image_processor': processor.image_processor.to_dict(),
               'checkpoint_config': model.config.to_dict()}
    if devices != ['cuda:0']:
        raise RuntimeError('Pilot nie dopuszcza niejawnego CPU/disk offload')
    return torch, model, processor, details


def set_resolution(processor, minimum: int, maximum: int) -> dict:
    # These are pixel budgets, despite the API names "edge" (official Qwen processor).
    processor.image_processor.size = {'shortest_edge': minimum, 'longest_edge': maximum}
    return processor.image_processor.to_dict()


def prepare_input(processor, messages: list[dict], spec: dict, *, generation: bool = True):
    options = {} if spec['enable_thinking'] is None else {'enable_thinking': spec['enable_thinking']}
    start = time.perf_counter()
    batch = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=generation,
                                          return_dict=True, return_tensors='pt', **options)
    grid = batch['image_grid_thw'][0].tolist()
    patch = processor.image_processor.patch_size
    merge = processor.image_processor.merge_size
    tokens = grid[0] * grid[1] * grid[2] // merge ** 2
    token_id = processor.tokenizer.convert_tokens_to_ids('<|image_pad|>')
    actual_tokens = int((batch['input_ids'] == token_id).sum())
    if tokens != actual_tokens or batch['pixel_values'].numel() == 0:
        raise ValueError('Tokeny obrazu nie odpowiadają przetworzonym pikselom')
    info = {'image_grid_thw': grid, 'processed_width': grid[2] * patch, 'processed_height': grid[1] * patch,
            'image_tokens': tokens, 'image_token_count_in_input': actual_tokens,
            'pixel_values_shape': list(batch['pixel_values'].shape),
            'input_tokens': batch['input_ids'].shape[-1], 'preprocess_seconds': time.perf_counter() - start}
    return batch, info


def error_details(error: Exception, torch) -> dict:
    return {'type': type(error).__name__, 'message': str(error),
            'cuda_oom': isinstance(error, torch.cuda.OutOfMemoryError), 'memory': gpu_snapshot(torch)}
