"""Small durable JSONL events with a concise terminal view."""
import json
import time


class Events:
    def __init__(self, path):
        self.path = path

    def emit(self, event, **values):
        row = {'event': event, 'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), **values}
        with self.path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
            stream.flush()
        if event == 'step':
            m = row['memory']
            print(f"epoch={row['epoch']} step={row['step']}/{row['total_steps']} examples={row['processed_examples']} "
                  f"loss={row['loss']:.6f} lr={row['learning_rate']:.3g} step_s={row['seconds']:.2f} "
                  f"elapsed_s={row['elapsed_seconds']:.1f} VRAM={m.get('used_vram_mib')}MiB "
                  f"alloc/res={m.get('allocated_mib', 0):.0f}/{m.get('reserved_mib', 0):.0f}MiB "
                  f"RSS={m['rss_mib']:.0f}MiB RAM_free={m['available_ram_mib']:.0f}MiB "
                  f"commit_free={m['commit_headroom_mib']}", flush=True)
        else:
            visible = {key: value for key, value in row.items() if key != 'sampler'}
            if 'sampler' in row:
                visible['step'] = row['sampler']['global_step']
                visible['processed_examples'] = row['sampler']['processed_examples']
            print(json.dumps(visible, ensure_ascii=False), flush=True)
