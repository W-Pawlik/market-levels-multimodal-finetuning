"""experiments / refinement / workflows / runner."""
from __future__ import annotations

import json
import traceback
import uuid
from pathlib import Path
from argparse import Namespace

from ..config import SYMBOLS, FRESH_SEEDS, FRESH_EXPERIMENT, SELECTION_SEED
from ..paths import validate_output_paths
from ....shared.json_io import read_json
from ....shared.integrity import sha256_file as sha
from ..io import (
    checked_report,
    cli,
    exclusive_json,
    unique_file,
    incomplete_stage,
    resolve,
    run_lock,
)
from ..domain.plan import experiment_tasks
from ..reporting import fresh_summary_markdown
from .preflight import preflight


def execute(project: Path, plan: dict, mode: str, root: Path) -> None:
    """Etapy są atomowymi partiami CLI; punkty kontrolne są tylko indeksem."""
    fresh = plan.get('experiment') == FRESH_EXPERIMENT
    validate_output_paths(root, mode, fresh=fresh)
    from ....data_processing.synthetic.io.batches import load_synthetic_windows
    from ....data_processing.io.chronology import load_chronological_split
    from ....data_processing.synthetic.domain.profiles.v1 import profile_hash
    from ....data_processing.synthetic.io.profiles import load_profile
    from ....data_processing.synthetic.config.generation import load_synthetic_settings
    from ....data_processing.synthetic.workflows.comparison import build_comparison
    from ....data_processing.synthetic.workflows.summary import build_variant_summary
    from ....data_processing.synthetic.reporting.variants import variant_summary_markdown
    split = load_chronological_split(Path(plan['config']))
    start, end = split.periods['train']
    tasks = experiment_tasks(mode,fresh=fresh)
    count = tasks[0]['count']
    seeds = tuple(dict.fromkeys(t['seed'] for t in tasks))
    experiment_id = ('refinement-fresh-seeds-'+mode) if fresh else 'refinement-comparison'
    stages = root / 'completed'; stages.mkdir(exist_ok=True)
    logs = root / 'logs'; logs.mkdir(exist_ok=True)

    def invoke(name, args, stage):
        print(f'Etap: {stage}', flush=True)
        cli(name, args, project, logs / (stage+'-'+uuid.uuid4().hex+'.log'))

    def complete(stage, files):
        marker = stages / (stage+'.json')
        value = {str(p.relative_to(root)): sha(p) for p in files}
        if marker.exists():
            if read_json(marker) != value:
                raise ValueError(f'Zmiana ukończonego etapu: {stage}')
        else:
            exclusive_json(marker, value)

    def verify_marker(stage):
        marker = stages / (stage+'.json')
        if marker.exists():
            for name, digest in read_json(marker).items():
                path = (root / name).resolve()
                if not path.is_relative_to(root) or not path.is_file() or sha(path) != digest:
                    raise ValueError(f'Brak lub zmiana ukończonego pliku: {path}')

    new_reports = {s: [] for s in SYMBOLS}
    for seed in seeds:
        for task in (t for t in tasks if t['seed']==seed):
            family, version, variant = task['family'], task['version'], task['variant']
            stage = f'{family}-{seed}'
            verify_marker(stage)
            output = root / stage
            manifest = unique_file(output/'diagnostics', 'manifest.json')
            if manifest is None:
                if output.exists() and any(output.rglob('*')):
                    raise incomplete_stage(output)
                args = ['--config', plan['config'], '--diagnostic', '--generator-version', version,
                    '--seed', str(seed), '--count', str(count), '--symbols', *SYMBOLS,
                    '--output', str(output)]
                if version=='v2':
                    args += ['--v2-variant',variant,'--experiment-id',experiment_id]
                for symbol in SYMBOLS:
                    args += ['--profile', symbol+'='+plan['profiles'][symbol+'|'+family]]
                invoke('generate_synthetic', args, stage)
                manifest = unique_file(output/'diagnostics', 'manifest.json')
            if manifest is None:
                raise ValueError(f'Generator nie opublikował manifestu: {stage}')
            doc = read_json(manifest); config = doc['identity']['configuration']
            # Porównaj całą konfigurację, łącznie z konfiguracją reżimów i ścieżkami profili.
            expected_config = load_synthetic_settings(Path(plan['config']), generator_version=version, diagnostic=True,
                v2_variant=variant, seed=seed, count=count, symbols=SYMBOLS, experiment_id=experiment_id,
                output=output, profiles={s:plan['profiles'][s+'|'+family] for s in SYMBOLS}).document()
            expected_config.pop('output')
            expected_config = json.loads(json.dumps(expected_config))
            expected_version = '2.0.0' if version=='v2' else '1.0.0'
            if (manifest.parent.name != doc['run_id'] or config != expected_config
                    or doc['status'] != 'diagnostic' or doc['identity']['generator_version'] != expected_version
                    or len(doc['examples']) != count*2 or doc['accepted_count'] != count*2):
                raise ValueError(f'Niezgodna konfiguracja/seed/liczność: {manifest}')
            for symbol in SYMBOLS:
                _, metadata = load_synthetic_windows(manifest, symbol=symbol, count=count, split=split)
                if metadata['profile_sha256'] != profile_hash(load_profile(Path(plan['profiles'][symbol+'|'+family]), symbol=symbol)):
                    raise ValueError(f'Inny profil w partii: {manifest}')
            complete(stage, [p for p in manifest.parent.rglob('*') if p.is_file()])
            for symbol in SYMBOLS:
                report_stage = f'{stage}-{symbol}'
                verify_marker(report_stage)
                report_root = root / 'comparisons' / report_stage
                report = unique_file(report_root, '*_comparison.json')
                if report is None:
                    if report_root.exists() and any(report_root.rglob('*')):
                        raise incomplete_stage(report_root)
                    invoke('compare_synthetic', ['--config', plan['config'], '--symbol', symbol,
                        '--real-csv', plan['real_csv'][symbol], '--synthetic-manifest', str(manifest),
                        '--start', plan['start'], '--end', plan['end'], '--window-count', str(count),
                        '--selection-seed', str(SELECTION_SEED), '--output', str(report_root)], report_stage)
                    report = unique_file(report_root, '*_comparison.json')
                if report is None:
                    raise ValueError(f'Brak raportu: {report_stage}')
                expected_report = build_comparison(symbol=symbol, real_csv=Path(plan['real_csv'][symbol]),
                    synthetic_manifest=manifest, start=start, end=end, count=count, selection_seed=SELECTION_SEED, split=split)
                if checked_report(report) != expected_report:
                    raise ValueError(f'Niezgodny raport: {report}')
                markdown = report.with_name(symbol+'_summary.md')
                if not markdown.is_file():
                    raise ValueError(f'Brak podsumowania: {markdown}')
                complete(report_stage, [report, markdown])
                new_reports[symbol].append(str(report))
    if mode == 'full' or fresh:
        for symbol in SYMBOLS:
            stage = 'summary-'+symbol
            verify_marker(stage)
            paths = new_reports[symbol] if fresh else [p for key,p in plan['old_reports'].items() if key.startswith(symbol+'|')] + new_reports[symbol]
            expected = build_variant_summary(list(map(Path, paths)), symbol=symbol)
            if fresh and (len(paths)!=8 or any(r['master_seed'] not in FRESH_SEEDS for r in expected['reports'])
                          or any(v['run_count']!=2 for v in expected['variants'].values())):
                raise ValueError('Nowa tabela wymaga tylko obu nowych seedów i czterech grup')
            directory = root / 'summary' / symbol
            report = unique_file(directory, '*_comparison.json')
            if report is None:
                if directory.exists() and any(directory.rglob('*')):
                        raise incomplete_stage(directory)
                invoke('compare_synthetic', ['--symbol', symbol, '--reports', *paths, '--output', str(directory)], stage)
                report = unique_file(directory, '*_comparison.json')
            if report is None or checked_report(report) != expected:
                raise ValueError(f'Niezgodny raport zbiorczy: {symbol}')
            markdown = report.with_name(symbol+'_summary.md')
            if markdown.read_text(encoding='utf-8') != variant_summary_markdown(expected):
                raise ValueError(f'Niezgodne podsumowanie: {markdown}')
            files = [report,markdown]
            if fresh:
                focus = directory/'STABILITY.md'
                text = fresh_summary_markdown(expected,mode)
                if focus.exists():
                    if focus.read_text(encoding='utf-8') != text:
                        raise ValueError(f'Zmodyfikowano raport stabilności: {focus}')
                else:
                    with focus.open('x',encoding='utf-8') as stream:
                        stream.write(text)
                files.append(focus)
            complete(stage, files)
    complete('finished', [p for p in stages.glob('*.json') if p.name != 'finished.json'])
    print(f'OK: {sum(t["count"]*len(SYMBOLS) for t in tasks)} nowych serii; wyniki: {root}', flush=True)


def run_comparison(args: Namespace) -> None:
    """Start, check or resume the existing refinement workflow."""
    project = args.project.resolve()
    options = {'fresh':True} if args.fresh_seeds else {}
    plan = preflight(project, resolve(project,args.inputs) if args.inputs else None,**options)
    print('OK: sprawdzono importy, dwa CLI, 12 starych raportow i 4 profile refinement.', flush=True)
    prefix = 'rf-' if args.fresh_seeds else 'rc-'
    if args.fresh_seeds:
        print('NOWA PROBA: cztery grupy, seedy 20261201/20261211; stare raporty tylko do kontroli pochodzenia.',flush=True)
    if args.mode == 'check':
        if args.resume:
            raise ValueError('CheckOnly nie przyjmuje katalogu wznowienia')
        candidate = resolve(project, args.output or ('data/synthetic/'+prefix+'000000000000'))
        length = validate_output_paths(candidate, 'full', fresh=args.fresh_seeds)
        print(f'OK: najdłuższa przewidywana ścieżka Windows: {length}/259 (oba warianty).', flush=True)
        return
    if args.output and args.resume:
        raise ValueError('Wybierz nowy output albo resume')
    run_id = uuid.uuid4().hex
    root = resolve(project, args.resume or args.output or ('data/synthetic/'+prefix+run_id[:12]))
    if root == project or root.is_relative_to(project/'src') or root.is_relative_to(project/'data/processed'):
        raise ValueError('Niedozwolony katalog wynikowy')
    identity = dict(mode=args.mode, plan=plan)
    length = validate_output_paths(root, args.mode, fresh=args.fresh_seeds)
    print(f'OK: najdłuższa przewidywana ścieżka Windows: {length}/259.', flush=True)
    if args.resume:
        saved = read_json(root/'run.json')
        if 'run_id' in saved:
            saved_id = saved['run_id']
            if (not isinstance(saved_id, str) or len(saved_id) != 32
                    or any(c not in '0123456789abcdef' for c in saved_id)):
                raise ValueError('Niepoprawny pełny run_id w run.json')
            identity['run_id'] = saved_id
        if saved != identity:
            raise ValueError('Wznowienie: zmieniono tryb, wejścia, profile, raporty, kod lub interpreter')
    else:
        root.mkdir(parents=True, exist_ok=False)
        identity['run_id'] = run_id
        exclusive_json(root/'run.json', identity)
    print(f'Katalog przebiegu (użyj -ResumeDirectory): {root}', flush=True)
    with run_lock(root/'running.lock'):
        try:
            execute(project, plan, args.mode, root)
        except BaseException:
            with (root/('error-'+uuid.uuid4().hex+'.log')).open('x',encoding='utf-8') as stream:
                traceback.print_exc(file=stream)
            raise
