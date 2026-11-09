"""Shared setup for the existing small refinement runner fixtures."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from market_levels.experiments.refinement.workflows import runner
from market_levels.cli import refinement_comparison as runner_cli
from market_levels.experiments.refinement.workflows import preflight as runner_preflight
from market_levels.experiments.refinement import config as runner_config, paths as runner_paths, io as runner_io
from market_levels.experiments.refinement.domain import plan as runner_plan
from market_levels.data_processing.synthetic.workflows.calibration import calibrate_csv
from market_levels.data_processing.synthetic.io.profiles import save_profile
from market_levels.data_processing.synthetic.workflows.calibration import calibrate_v2_csv
from market_levels.data_processing.synthetic.config.refinement import RefinementSettings
from market_levels.data_processing.synthetic.workflows.refinement import refine_v2_volatility
from market_levels.data_processing.synthetic.config.generation import SyntheticSettings
from market_levels.data_processing.io.chronology import load_chronological_split
from market_levels.data_processing.io.candles import write_candles_csv
from market_levels.data_processing.synthetic.workflows.generation import run
from market_levels.data_processing.synthetic.workflows.comparison import build_comparison
from market_levels.data_processing.synthetic.domain.diagnostics import aggregate_windows
from market_levels.data_processing.synthetic.io.batches import load_synthetic_windows
from market_levels.data_processing.windows.domain.selection import select_real_windows
from market_levels.data_processing.synthetic.domain.generation.seeds import example_seed
from support.calibration import small_search
from support.comparison import real_fixture, CONFIG

def write_report(path, report):
    report = deepcopy(report);report.pop('comparison_id', None)
    report['comparison_id'] = hashlib.sha256(json.dumps(report,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()[:24]
    path.write_text(json.dumps(report),encoding='utf-8')

def prepare_runner_fixture(cls):

    cls.temp = tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)

    cls.root = Path(cls.temp.name);cls.project = CONFIG.parents[1]

    cls.split = load_chronological_split(CONFIG);cls.start,cls.end = cls.split.periods['train']

    cls.options = {'config':str(CONFIG),'profiles':{},'real_csv':{},'historical_reports':[]}

    settings = SyntheticSettings(generator_version='v2',diagnostic=True,count=2,symbols=runner_config.SYMBOLS)

    search = RefinementSettings(volatility_phi=[.7],volatility_stationary_std=[.2],

        simulation_seeds=[101,102,103],diagnostic_seeds=[500,501],examples_per_seed=1)

    originals, old_paths = {}, {}

    for symbol in runner_config.SYMBOLS:

        csv = cls.root/(symbol+'.csv');write_candles_csv(csv,real_fixture(7400))

        cls.options['real_csv'][symbol] = str(csv)

        original = calibrate_v2_csv(csv,symbol,start=cls.start,end=cls.end,split=cls.split,settings=settings,search=small_search())

        source = cls.root/(symbol+'-original.json');save_profile(source,original)

        originals[symbol] = source

        v1 = cls.root/(symbol+'-v1.json');save_profile(v1,calibrate_csv(csv,symbol,allowed_start=cls.start,allowed_end=cls.end))

        old_paths[symbol] = v1

        for variant in runner_config.VARIANTS:

            profile = refine_v2_volatility(csv,source,symbol=symbol,variant=variant,start=cls.start,end=cls.end,

                split=cls.split,settings=settings,search=search)

            path = cls.root/(symbol+'-'+variant+'.json');save_profile(path,profile)

            cls.options['profiles'][symbol+'|'+variant] = str(path)

    # Małe prawdziwe partie; historyczne JSON fixture opisują powtórzone okna

    # jako kontrolowaną referencję 60. Nie generujemy 720 serii na potrzeby testu.

    for version, profiles in (('v1',old_paths),('v2',originals)):

        manifest = run(replace(settings,generator_version=version,profiles={s:str(p) for s,p in profiles.items()},

            output=cls.root/version))/'manifest.json'

        for symbol in runner_config.SYMBOLS:

            csv = Path(cls.options['real_csv'][symbol])

            report = build_comparison(symbol=symbol,real_csv=csv,synthetic_manifest=manifest,start=cls.start,end=cls.end,

                count=2,selection_seed=runner_config.SELECTION_SEED,split=cls.split)

            windows,selection = select_real_windows(real_fixture(7400),symbol=symbol,start=cls.start,end=cls.end,

                count=60,seed=runner_config.SELECTION_SEED,split=cls.split)

            synthetic,_ = load_synthetic_windows(manifest,symbol=symbol,count=2,split=cls.split)

            report.update(selection=selection,real=aggregate_windows(windows),synthetic=aggregate_windows(synthetic*30))

            for seed in runner_config.SEEDS:

                fixture = deepcopy(report);source = fixture['synthetic_source']

                source['master_seed'] = seed;source['run_id'] = f'fixture-{version}-{symbol}-{seed}'

                source['examples'] = [dict(source['examples'][i%2],seed=example_seed(seed,symbol,i)) for i in range(60)]

                path = cls.root/f'{version}-{symbol}-{seed}.json';write_report(path,fixture)

                cls.options['historical_reports'].append(str(path))

    cls.inputs = cls.root/'inputs.json';cls.inputs.write_text(json.dumps(cls.options),encoding='utf-8')
