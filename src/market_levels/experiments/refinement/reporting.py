"""experiments / refinement / reporting."""
from __future__ import annotations


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
