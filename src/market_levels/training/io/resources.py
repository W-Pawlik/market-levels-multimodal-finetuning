"""Host commit counters and bounded resource guards; no system mutations."""
from __future__ import annotations

import ctypes
import os
import subprocess
import threading
import time


class ResourceMonitor:
    """Sample host/global GPU during a step without CUDA calls in the thread."""
    def __enter__(self):
        self.samples = []
        self.stopping = threading.Event()
        self.started = time.perf_counter()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return self

    def _run(self):
        while not self.stopping.is_set():
            row = snapshot()
            row['seconds'] = time.perf_counter() - self.started
            self.samples.append(row)
            self.stopping.wait(0.5)

    def __exit__(self, *args):
        self.stopping.set()
        self.thread.join(timeout=6)


def snapshot(torch=None):
    import psutil
    process = psutil.Process()
    row = {'rss_mib': process.memory_info().rss / 2**20,
           'available_ram_mib': psutil.virtual_memory().available / 2**20,
           'cpu_percent': psutil.cpu_percent(interval=None),
           'process_cpu_seconds': sum(process.cpu_times()[:2]),
           'commit_mib': None, 'commit_limit_mib': None, 'commit_headroom_mib': None}
    if os.name == 'nt':
        from ctypes import wintypes
        class PerformanceInfo(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in
                ('CommitTotal', 'CommitLimit', 'CommitPeak', 'PhysicalTotal', 'PhysicalAvailable',
                 'SystemCache', 'KernelTotal', 'KernelPaged', 'KernelNonpaged', 'PageSize')] + [
                (name, wintypes.DWORD) for name in ('HandleCount', 'ProcessCount', 'ThreadCount')]
        info = PerformanceInfo()
        info.cb = ctypes.sizeof(info)
        if ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(info), info.cb):
            row.update(commit_mib=info.CommitTotal * info.PageSize / 2**20,
                       commit_limit_mib=info.CommitLimit * info.PageSize / 2**20,
                       commit_headroom_mib=(info.CommitLimit-info.CommitTotal) * info.PageSize / 2**20)
        else:
            row['commit_error'] = 'GetPerformanceInfo failed'
    try:
        output = subprocess.check_output(['nvidia-smi', '--id=0', '--query-gpu=name,memory.total,memory.used,memory.free',
            '--format=csv,noheader,nounits'], text=True, timeout=5)
        name, total, used, free = [v.strip() for v in output.strip().split(',')]
        row.update(gpu=name, total_vram_mib=int(total), used_vram_mib=int(used), free_vram_mib=int(free))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        row['nvidia_error'] = str(error)
    if torch is not None:
        row.update(allocated_mib=torch.cuda.memory_allocated()/2**20,
                   reserved_mib=torch.cuda.memory_reserved()/2**20,
                   peak_allocated_mib=torch.cuda.max_memory_allocated()/2**20,
                   peak_reserved_mib=torch.cuda.max_memory_reserved()/2**20)
    return row


def pressure(row, settings):
    reasons = []
    if row.get('minimum_available_ram_mib', row['available_ram_mib']) < settings['minimum_ram_mib']:
        reasons.append('critical available physical RAM')
    commit = row.get('minimum_commit_headroom_mib', row['commit_headroom_mib'])
    if commit is not None and commit < settings['minimum_commit_headroom_mib']:
        reasons.append('critical system commit headroom')
    return reasons


def guard(settings):
    row = snapshot()
    if row.get('gpu') != settings['required_gpu'] or row.get('total_vram_mib') != 8192:
        raise RuntimeError(f'Wrong/unreadable GPU: {row}')
    if row['used_vram_mib'] > settings['maximum_idle_vram_mib']:
        raise RuntimeError(f"GPU busy: {row['used_vram_mib']} MiB > {settings['maximum_idle_vram_mib']} MiB")
    if pressure(row, settings):
        raise RuntimeError(f'Host memory guard: {row}')
    if os.name == 'nt' and row['commit_headroom_mib'] is None:
        raise RuntimeError('Cannot read Windows commit headroom')
    return row
