"""experiments / refinement / workflows / preflight."""
from __future__ import annotations

import importlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path
from datetime import datetime

from ..io import cli, resolve, checked_report
from ..config import SYMBOLS, VARIANTS, SEEDS, FRESH_SEEDS, FRESH_EXPERIMENT, SELECTION_SEED
from ....shared.json_io import read_json
from ....shared.integrity import sha256_file as sha


def check_environment(project: Path) -> dict:
    modules = ('market_levels', 'market_levels.data_processing.synthetic',
               'market_levels.data_processing.synthetic.workflows.refinement',
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
    from ....data_processing.synthetic.domain.generation.models import GENERATOR_VERSION
    from ....data_processing.synthetic.domain.parameters import V2_VERSION
    if (GENERATOR_VERSION, V2_VERSION) != ('1.0.0', '2.0.0'):
        raise ValueError('Niezgodne wersje generatorów')
    for name in ('generate_synthetic', 'compare_synthetic'):
        cli(name, ['--help'], project)
    return dict(python=sys.executable, version=platform.python_version(), modules=origins,
                generator_versions=[GENERATOR_VERSION, V2_VERSION])


def preflight(project: Path, inputs: Path | None = None, *, fresh: bool = False) -> dict:
    """Odczyt i kontrola wszystkich zależności przed utworzeniem wyników."""
    environment = check_environment(project)
    from ....data_processing.synthetic.io.profiles import load_profile
    from ....data_processing.synthetic.domain.profiles.v1 import profile_hash
    from ....data_processing.synthetic.domain.profiles.validation import validate_generator_profile
    from ....data_processing.synthetic.config.generation import load_synthetic_settings
    from ....data_processing.synthetic.domain.profiles.v2 import regime_configuration
    from ....data_processing.synthetic.workflows.summary import build_variant_summary
    from ....data_processing.io.chronology import load_chronological_split
    from ....data_processing.windows.domain.selection import select_real_windows
    from ....data_processing.io.candles import read_candles_csv
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
