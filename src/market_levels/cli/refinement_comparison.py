"""Bezpieczna koordynacja istniejących CLI; bez nowej matematyki OHLC."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path, PureWindowsPath
import platform
import subprocess
import sys
import traceback
import uuid

SYMBOLS = ('BTCUSDT', 'ETHUSDT')
VARIANTS = ('full', 'bridge_volatility')
SEEDS = (20261105, 20261115, 20261125)
FRESH_SEEDS = (20261201, 20261211)
FRESH_EXPERIMENT = 'refinement-fresh-seeds-v1'
SELECTION_SEED = 20261106
WINDOWS_MAX_PATH = 260  # Zawiera końcowy NUL; widoczna ścieżka musi mieć <260 jednostek UTF-16.


def longest_output_path(root: Path | PureWindowsPath, mode: str, *, fresh: bool = False) -> PureWindowsPath:
    """Przewidź pliki staging/final i raporty, bez generowania ani skracania ID.

    Aktualny tempfile używa 8 znaków losowych; identyfikatory partii/raportów
    mają 24 znaki, seedy przykładów 64 hex. Sprawdzamy oba warianty, ponieważ
    bridge_volatility ma dłuższy katalog niż full. Limit stosujemy przenośnie,
    bez polegania na ustawieniu LongPathsEnabled konkretnego Windows.
    """
    root = PureWindowsPath(root)
    seeds = FRESH_SEEDS if fresh else ((20261107,) if mode == 'smoke' else SEEDS)
    paths = [root/'run.json', root/('error-'+'f'*32+'.log')]
    for seed in seeds:
        for variant in (('v1','original',*VARIANTS) if fresh else VARIANTS):
            stage = f'{variant}-{seed}'
            batch = root/stage
            locations = (batch/('.synthetic-'+'x'*8)/'batch', batch/'diagnostics'/('f'*24))
            for location in locations:
                paths.append(location/'manifest.json')
                for symbol in SYMBOLS:
                    for suffix in ('.csv', '.json'):
                        paths.append(location/symbol/(symbol+'_000000_'+'f'*64+suffix))
            paths.append(root/'completed'/(stage+'.json'))
            for symbol in SYMBOLS:
                report_stage = stage+'-'+symbol
                paths.extend((root/'completed'/(report_stage+'.json'),
                              root/'logs'/(report_stage+'-'+'f'*32+'.log')))
                outputs = [root/'comparisons'/report_stage]
                if mode != 'smoke' or fresh:
                    outputs.append(root/'summary'/symbol)
                for output in outputs:
                    for location in (output/('.comparison-'+'x'*8)/'report', output/('f'*24)):
                        paths.extend((location/(symbol+'_comparison.json'), location/(symbol+'_summary.md')))
    return max(paths, key=lambda path: len(str(path).encode('utf-16-le'))//2)


def validate_output_paths(root: Path | PureWindowsPath, mode: str, *, fresh: bool = False) -> int:
    """Odmów przed tworzeniem katalogów i uruchamianiem generatora."""
    path = longest_output_path(root, mode, fresh=fresh)
    length = len(str(path).encode('utf-16-le'))//2
    if length >= WINDOWS_MAX_PATH:
        raise ValueError(f'Zbyt długa ścieżka Windows: {length} znaków UTF-16 (wymagane <260). '
                         f'Najdłuższa przewidywana ścieżka: {path}. '
                         'Użyj -OutputDirectory z krótszą ścieżką, np. D:\\rc\\nowy. '
                         'Nie przenoś ani nie nadpisuj wcześniejszych wyników.')
    return length


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError(f'Oczekiwano obiektu JSON: {path}')
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(project: Path, value: str | Path) -> Path:
    return (project / value).resolve()


def checked_report(path: Path) -> dict:
    report = read_json(path)
    payload = {k: v for k, v in report.items() if k != 'comparison_id'}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()[:24]
    if report.get('comparison_id') != digest:
        raise ValueError(f'Niezgodny hash raportu: {path}')
    return report


def cli(module: str, arguments: list[str], project: Path, log: Path | None = None) -> None:
    command = [sys.executable, '-I', '-X', 'utf8', '-m', 'market_levels.cli.' + module, *map(str, arguments)]
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    if log is not None:
        # Nowy log każdej próby, także przy wznowieniu; zachowuje pełny traceback.
        with log.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(command, ensure_ascii=False) + '\n'); stream.flush()
            process = subprocess.run(command, cwd=project, env=env, stdout=stream, stderr=subprocess.STDOUT)
    else:
        process = subprocess.run(command, cwd=project, env=env, capture_output=True, text=True,
                                 encoding='utf-8', errors='replace')
    if process.returncode:
        if log is None:
            sys.stderr.write(process.stderr)
        raise RuntimeError(f'CLI {module}: kod {process.returncode}; log: {log or "stderr"}')


def check_environment(project: Path) -> dict:
    modules = ('market_levels', 'market_levels.data_processing.synthetic',
               'market_levels.data_processing.synthetic.refinement',
               'market_levels.cli.generate_synthetic', 'market_levels.cli.compare_synthetic')
    origins = {}
    for name in modules:
        module = importlib.import_module(name)
        origin = Path(module.__file__).resolve()
        if not origin.is_relative_to(project / 'src'):
            raise ValueError(f'Konflikt instalacji: {name} pochodzi z {origin}, oczekiwano {project / "src"}')
        origins[name] = str(origin)
    distributions = [d for d in importlib.metadata.distributions()
                     if d.metadata.get('Name', '').lower().replace('_', '-') == 'market-levels']
    # Editable setuptools udostępnia jednocześnie src/*.egg-info i dist-info.
    # Lokalny egg-info nie jest drugą instalacją; obce katalogi nadal odrzucamy.
    installations = [d for d in distributions if d.read_text('direct_url.json')]
    for distribution in distributions:
        if not distribution.read_text('direct_url.json') and Path(distribution.locate_file('')).resolve() != project/'src':
            raise ValueError('Konflikt dodatkowej instalacji market-levels')
    if len(installations) != 1:
        raise ValueError(f'Oczekiwano jednej instalacji editable; znaleziono {len(installations)}')
    direct = json.loads(installations[0].read_text('direct_url.json'))
    if direct.get('dir_info', {}).get('editable') is not True:
        raise ValueError('Wymagana instalacja edytowalna: python -m pip install -e .')
    from ..data_processing.synthetic.generator import GENERATOR_VERSION
    from ..data_processing.synthetic.v2_parameters import V2_VERSION
    if (GENERATOR_VERSION, V2_VERSION) != ('1.0.0', '2.0.0'):
        raise ValueError('Niezgodne wersje generatorów')
    for name in ('generate_synthetic', 'compare_synthetic'):
        cli(name, ['--help'], project)
    return dict(python=sys.executable, version=platform.python_version(), modules=origins,
                generator_versions=[GENERATOR_VERSION, V2_VERSION])


def preflight(project: Path, inputs: Path | None = None, *, fresh: bool = False) -> dict:
    """Odczyt i kontrola wszystkich zależności przed utworzeniem wyników."""
    environment = check_environment(project)
    from ..data_processing.synthetic.calibration import load_profile, profile_hash, validate_generator_profile
    from ..data_processing.synthetic.settings import load_synthetic_settings
    from ..data_processing.synthetic.profile_v2 import regime_configuration
    from ..data_processing.synthetic.experiments import build_variant_summary
    from ..data_processing.synthetic.training_period import load_chronological_split
    from ..data_processing.synthetic.selection import select_real_windows
    from ..data_processing.storage import read_candles_csv
    options = read_json(inputs) if inputs else {}
    allowed = {'config', 'profiles', 'real_csv', 'historical_reports'}
    if fresh:
        allowed.add('baseline_profiles')
    if set(options) - allowed:
        raise ValueError('Nieznane pola pliku wejść')
    config = resolve(project, options.get('config', 'configs/experiment.json'))
    split = load_chronological_split(config)
    if split.split_id != 'chronological_v1':
        raise ValueError('Wymagany chronological_v1')
    start, end = split.periods['train']
    profiles, paths, digests, real_csv = {}, {}, {}, {}
    for symbol in SYMBOLS:
        real_csv[symbol] = str(resolve(project, options.get('real_csv', {}).get(symbol,
            f'data/processed/{symbol}_4h_2020-01_2026-10.csv')))
        digests[real_csv[symbol]] = sha(Path(real_csv[symbol]))
        for variant in VARIANTS:
            key = symbol + '|' + variant
            if 'profiles' in options:
                path = resolve(project, options['profiles'][key])
            else:
                candidates = list((project / 'data/synthetic').glob(f'*/profiles/{symbol}_{variant}_refined_unapproved.json'))
                if len(candidates) != 1:
                    raise ValueError(f'{key}: wymagany dokładnie jeden profil refinement; znaleziono {len(candidates)}. Podaj --inputs.')
                path = candidates[0].resolve()
            profile = load_profile(path, symbol=symbol)
            audit = profile.get('calibration', {})
            if (profile['status'] != 'unapproved' or profile.get('generator_version') != '2.0.0'
                    or audit.get('method') != 'volatility_refinement_v1' or audit.get('variant') != variant
                    or profile['source']['chronological_split'] != split.document()
                    or profile['source']['sha256'] != digests[real_csv[symbol]]):
                raise ValueError(f'Nieprawidłowe pochodzenie/status/wariant profilu: {path}')
            settings = load_synthetic_settings(config, generator_version='v2', diagnostic=True, v2_variant=variant)
            if profile['regime_configuration'] != regime_configuration(settings):
                raise ValueError(f'Reżimy konfiguracji różnią się od profilu: {path}')
            profiles[key], paths[key] = profile, str(path)
            digests[str(path)] = sha(path)
    report_paths = ([resolve(project, p) for p in options['historical_reports']] if 'historical_reports' in options
                    else sorted((project / 'data/synthetic/v2-evaluation/comparisons').rglob('*_comparison.json')))
    old, references = {}, {}
    for path in report_paths:
        report = read_json(path)
        source = report.get('synthetic_source', {})
        version, seed, symbol = source.get('generator_version'), source.get('master_seed'), report.get('symbol')
        family = 'V1' if version == '1.0.0' else ('V2-full' if version == '2.0.0' and source.get('variant') == 'full' else None)
        if symbol not in SYMBOLS or seed not in SEEDS or family is None:
            if 'historical_reports' in options:
                raise ValueError(f'Nieoczekiwany raport historyczny: {path}')
            continue
        report = checked_report(path)
        key = f'{symbol}|{family}|{seed}'
        if key in old:
            raise ValueError(f'Zduplikowany raport wariantu i seeda: {key}')
        validate_generator_profile(source['profile'], symbol=symbol, generator_version='v1' if family == 'V1' else 'v2')
        selection = report['selection']
        if (report['split'] != split.document() or selection['window_count'] != 60
                or selection['selection_seed'] != SELECTION_SEED or report['real']['window_count'] != 60
                or report['synthetic']['window_count'] != 60 or len(source['examples']) != 60
                or source['profile_sha256'] != profile_hash(source['profile'])
                or report['real_source']['sha256'] != digests[real_csv[symbol]]):
            raise ValueError(f'Niezgodna referencja/liczność/profil starego raportu: {path}')
        if family == 'V2-full' and any(profiles[symbol+'|'+v]['calibration']['source_profile_sha256'] != source['profile_sha256'] for v in VARIANTS):
            raise ValueError(f'Refinement nie pochodzi z full-original: {path}')
        if symbol not in references:
            _, expected_selection = select_real_windows(read_candles_csv(Path(real_csv[symbol]), source=real_csv[symbol]),
                symbol=symbol, start=start, end=end, count=60, seed=SELECTION_SEED, split=split)
            references[symbol] = dict(selection=expected_selection, real=report['real'])
        if selection != references[symbol]['selection'] or report['real'] != references[symbol]['real']:
            raise ValueError(f'Inne rzeczywiste okna/statystyki: {path}')
        old[key] = str(path)
        digests[str(path)] = sha(path)
    expected = {f'{s}|{f}|{seed}' for s in SYMBOLS for f in ('V1', 'V2-full') for seed in SEEDS}
    if set(old) != expected:
        raise ValueError(f'Brak raportów historycznych: {sorted(expected - set(old))}; wymagano 12')
    for symbol in SYMBOLS:
        build_variant_summary([Path(p) for key, p in old.items() if key.startswith(symbol+'|')], symbol=symbol)
    digests[str(config)] = sha(config)
    # Zmiana kodu lub wersji Pythona wymaga nowego przebiegu, nie cichego wznowienia.
    for path in (project / 'src/market_levels').rglob('*.py'):
        digests[str(path)] = sha(path)
    plan = dict(config=str(config), profiles=paths, old_reports=old, real_csv=real_csv,
                digests=digests, environment=environment, start=start.isoformat(), end=end.isoformat())
    if fresh:
        plan.update(experiment=FRESH_EXPERIMENT, seeds=list(FRESH_SEEDS), selection_seed=SELECTION_SEED)
        for symbol in SYMBOLS:
            for family, version, default in (
                ('v1','v1',f'data/synthetic/calibration/{symbol}_train_2020_2023_unapproved.json'),
                ('original','v2',f'data/synthetic/calibration/v2/{symbol}_train_2020_2023_v2_unapproved.json')):
                key = symbol+'|'+family
                path = resolve(project,options.get('baseline_profiles',{}).get(key,default))
                profile = load_profile(path,symbol=symbol)
                validate_generator_profile(profile,symbol=symbol,generator_version=version)
                label = 'V1' if family=='v1' else 'V2-full'
                expected_profile = read_json(Path(old[f'{symbol}|{label}|{SEEDS[0]}']))['synthetic_source']['profile']
                if (profile != expected_profile or profile['status'] != 'unapproved'
                        or profile['source']['sha256'] != digests[real_csv[symbol]]):
                    raise ValueError(f'Profil bazowy różni się od zamrożonego historycznego profilu: {path}')
                split.require_training(*(datetime.fromisoformat(profile['period'][k])
                                         for k in ('allowed_start','allowed_end')))
                if version=='v2' and profile['regime_configuration'] != regime_configuration(settings):
                    raise ValueError(f'Inne reżimy profilu original: {path}')
                paths[key] = str(path);digests[str(path)] = sha(path)
        for path in paths.values():
            calibration_seeds = read_json(Path(path)).get('calibration',{}).get('simulation_seeds',[])
            if set(FRESH_SEEDS).intersection(calibration_seeds):
                raise ValueError('Nowe seedy nie mogą być seedami kalibracji')
    return plan


def experiment_tasks(mode: str, *, fresh: bool = False) -> list[dict]:
    """Jawna lista partii: nowy eksperyment generuje również oba baseline."""
    seeds = FRESH_SEEDS if fresh else ((20261107,) if mode=='smoke' else SEEDS)
    count = 2 if mode=='smoke' else 60
    families = [('v1','v1','full'),('original','v2','full')] if fresh else []
    families += [('full','v2','full'),('bridge_volatility','v2','bridge_volatility')]
    return [dict(seed=seed, count=count, family=family, version=version, variant=variant)
            for seed in seeds for family,version,variant in families]


def fresh_summary_markdown(summary: dict, mode: str) -> str:
    """Wyłącznie prezentacja metryk istniejącego agregatora."""
    metrics = dict(abs_ac1='abs_ac1', window_std_mean='window_return_std_mean',
        window_std_std='window_return_std_std', abs_q99='abs_return_q0.99',
        body_fraction='body_fraction_mean', relative_range_mean='relative_range_mean')
    lines = [f"# {summary['symbol']}: stabilność na nowych seedach", '',
        'Seedy: 20261201, 20261211. Selection seed: 20261106.',
        'Kontrola na tych samych danych treningowych; nie jest niezależnym testem rynku.',
        'Mała próba techniczna: po 2 serie; bez oceny realizmu.' if mode=='smoke' else 'Po 60 serii na seed/instrument/grupę.',
        'Poprzednie trzy seedy nie są dołączane. Nie wybrano ani nie zatwierdzono generatora.', '',
        '| Metryka | Grupa | Realne | Syntetyczne | Średni błąd bezwzględny | Std między seedami |',
        '| --- | --- | ---: | ---: | ---: | ---: |']
    fmt = lambda value: 'undefined' if value is None else f'{value:.9g}'
    for alias, name in metrics.items():
        for label, group in summary['variants'].items():
            metric = group['metrics'][name]
            values = [summary['real_metrics'][name],metric.get('value'),metric.get('mean_absolute_error'),metric.get('std_between_seeds')]
            lines.append('| '+alias+' | '+label+' | '+' | '.join(map(fmt,values))+' |')
    return '\n'.join(lines)+'\n'


def exclusive_json(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def unique_file(root: Path, pattern: str) -> Path | None:
    # Tylko opublikowany katalog <id>/<plik>; staging ma dodatkowy poziom
    # .synthetic-*/batch lub .comparison-*/report i nie jest wynikiem.
    matches = list(root.glob('*/'+pattern)) if root.exists() else []
    if len(matches) > 1:
        raise ValueError(f'Niejednoznaczny wynik: {root}/{pattern}')
    return matches[0] if matches else None


def incomplete_stage(path: Path) -> ValueError:
    return ValueError(f'Niekompletny etap: {path.resolve()}. Ukończone etapy zostaną zachowane. '
        'Po zatrzymaniu procesu ręcznie przenieś CAŁY ten niekompletny katalog do nowego, '
        'nieistniejącego katalogu kopii poza przebiegiem (Move-Item -LiteralPath ... -Destination ...). '
        'Sprawdź ścieżki i zachowaj kopię; nie usuwaj checkpointów ani poprawnych partii. '
        'Następnie uruchom ten sam skrypt i tryb z -ResumeDirectory wskazującym katalog przebiegu. '
        'Jeśli zmieniono kod od utworzenia run.json, kontrola SHA wymaga nowego przebiegu.')


@contextmanager
def run_lock(path: Path):
    """Blokadę zwalnia system także po twardym przerwaniu procesu."""
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def execute(project: Path, plan: dict, mode: str, root: Path) -> None:
    """Etapy są atomowymi partiami CLI; punkty kontrolne są tylko indeksem."""
    fresh = plan.get('experiment') == FRESH_EXPERIMENT
    validate_output_paths(root, mode, fresh=fresh)
    from ..data_processing.synthetic.comparison import load_synthetic_windows
    from ..data_processing.synthetic.training_period import load_chronological_split
    from ..data_processing.synthetic.calibration import profile_hash, load_profile
    from ..data_processing.synthetic.settings import load_synthetic_settings
    from ..data_processing.pipelines.compare_synthetic import build_comparison
    from ..data_processing.synthetic.experiments import build_variant_summary, variant_summary_markdown
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', required=True, choices=('check', 'smoke', 'full'))
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--inputs', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', type=Path)
    parser.add_argument('--fresh-seeds', action='store_true', help='Oddzielna próba czterech grup: 20261201/20261211')
    args = parser.parse_args()
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


if __name__ == '__main__':
    main()
