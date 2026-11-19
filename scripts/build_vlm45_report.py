"""Build stage 4.5 documentation/figures from audited local evidence, without ML inference.

Run after audit_vlm45.py analyze. Does not modify existing experimental artifacts.
"""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from market_levels.shared.integrity import sha256_file
from market_levels.evaluation.protocol import loads, dumps, PROTOCOL_SHA256

AUDIT=Path('results/vlm45-final-audit-20261111-a')
DOC=Path('docs/vlm')
ASSETS=DOC/'final45'
DATA=Path('data/datasets/ds35-800-20261107-a')
NAMES=['vlm43-validation-step175-26351-3437','vlm43-validation-step350-9320-26567','vlm44-validation-4184-25636']
RUNS=['vlm43-part1-14789-1679','vlm43-part2-17032-13034','vlm43-part3-2708-16743','vlm44-part1-24755-21138','vlm44-part2-17554-5354']


def read(p):
    return loads(Path(p).read_text(encoding='utf-8'))


def write(p,v):
    Path(p).write_text(dumps(v)+'\n',encoding='utf-8')


def fmt(x):
    return '—' if x is None else f'{x:.10f}' if not isinstance(x,(int,str)) else str(x)


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|',
                      *['| '+' | '.join(fmt(x) for x in row)+' |' for row in rows]])


def savefig(name):
    plt.savefig(ASSETS/name,dpi=160,bbox_inches='tight'); plt.close()


def main():
    ASSETS.mkdir(exist_ok=True)
    ev=read(AUDIT/'evaluations.json'); steps=read(AUDIT/'steps.json'); training=read(AUDIT/'training.json'); pairs=read(AUDIT/'paired.json')
    summaries=[ev[n]['summary'] for n in NAMES]
    overall=[s['tolerances']['0.5']['overall'] for s in summaries]
    selected=Path('results')/RUNS[-1]/'adapter'; alternative=Path('results')/RUNS[2]/'adapter'
    selected_hash=sha256_file(selected/'adapter_model.safetensors')
    selection={
        'schema_version':1,'status':'frozen_local_artifacts_verified','selection_date':'2026-11-11',
        'selected_adapter':selected.as_posix(),'experiment_id':'vlm44-extra-epoch',
        'run_id':RUNS[-1],'experiment_segments':RUNS[3:],
        'base_model':'Qwen/Qwen3-VL-2B-Instruct','base_revision':'89644892e4d85e24eaac8bacfd4f463576704203',
        'dataset_id':DATA.name,'dataset_manifest':(DATA/'manifest.json').as_posix(),
        'dataset_manifest_sha256':sha256_file(DATA/'manifest.json'),
        'effective_config_path':f'results/{RUNS[-1]}/effective-config.json',
        'effective_config_sha256':sha256_file(Path('results')/RUNS[-1]/'effective-config.json'),
        'effective_config':read(Path('results')/RUNS[-1]/'effective-config.json'),
        'adapter_sha256':selected_hash,'adapter_manifest_sha256':sha256_file(selected/'manifest.json'),
        'adapter_files':{p.name:sha256_file(p) for p in selected.iterdir() if p.is_file()},
        'checkpoint_path':f'results/{RUNS[-1]}/checkpoints/step-000175',
        'checkpoint_manifest_sha256':sha256_file(Path('results')/RUNS[-1]/'checkpoints/step-000175/manifest.json'),
        'official_validation_id':NAMES[-1],'validation_path':f'results/evaluation/{NAMES[-1]}',
        'validation_summary_sha256':ev[NAMES[-1]]['summary_sha256'],
        'validation_manifest_sha256':ev[NAMES[-1]]['manifest_sha256'],
        'validation_predictions_sha256':sha256_file(Path('results/evaluation')/NAMES[-1]/'predictions.jsonl'),
        'validation_fingerprint':ev[NAMES[-1]]['fingerprint'],'evaluation_protocol':'sr-eval-v1',
        'evaluation_protocol_sha256':PROTOCOL_SHA256,'instruction_version':'pl-sr-v1',
        'selection_metric':{'name':'micro_f1','atr_tolerance':'0.5','value':overall[-1]['micro_f1'],
                            'tp':70,'fp':82,'fn':77,'valid_json_count':36,'examples':36},
        'selection_rule':'higher official validation micro-F1 at 0.5 ATR; ties: valid JSON share, then earlier step-350 adapter',
        'selection_rule_source':'docs/vlm/INSTRUKCJA_POWERSHELL_4_4.md#e-walidacja--po-zakończeniu-obu-odcinków',
        'extra_epoch_decided_after_validation_review':True,
        'preserved_alternative':{'path':alternative.as_posix(),'adapter_sha256':sha256_file(alternative/'adapter_model.safetensors'),
           'manifest_sha256':sha256_file(alternative/'manifest.json'),'validation_id':NAMES[1],'micro_f1':overall[1]['micro_f1']},
        'test_evaluation_run':False,'test_used_for_selection':False,
        'test_status_basis':'author declaration and available local artifacts; no test inference performed during stage 4.5',
        'further_training_authorized':False,'test_requires_separate_authorization':True,
        'freeze_scope':'local adapter/configuration/dataset/protocol/validation identities; hashes are not signatures or filesystem locks'}
    write(DOC/'FINAL_MODEL_SELECTION.json',selection)
    with (ASSETS/'training_steps.csv').open('w',newline='',encoding='utf-8') as f:
        keys=['run','epoch','step','processed_examples','loss','gradient_norm','learning_rate','seconds','rss_mib','used_vram_mib','peak_global_vram_mib','peak_allocated_mib','peak_reserved_mib']
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        for r in steps: w.writerow({k:r.get(k,r['memory'].get(k)) for k in keys})
    with (ASSETS/'paired_validation.csv').open('w',newline='',encoding='utf-8') as f:
        keys=['id','symbol','old_f1','new_f1','delta_f1','old_tp','new_tp','old_fp','new_fp','old_fn','new_fn','complete','zero_tp']
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in pairs)
    write(ASSETS/'verified_metrics.json',{n:ev[n] for n in ev})
    write(ASSETS/'training_audit.json',training)
    write(ASSETS/'dataset_audit.json',read(AUDIT/'dataset.json'))
    # Separate axes make the optimizer reset explicit. Raw points only, no smoothing.
    fig,axes=plt.subplots(2,2,figsize=(12,7))
    for j,(runs,title) in enumerate([(RUNS[:3],'Eksperyment główny'),(RUNS[3:],'Dodatkowy eksperyment')]):
        subset=[r for r in steps if r['run'] in runs]
        axes[0,j].scatter([r['step'] for r in subset],[float(r['loss']) for r in subset],s=5)
        axes[1,j].scatter([r['step'] for r in subset],[float(r['learning_rate']) for r in subset],s=5)
        axes[0,j].set_title(title); axes[0,j].set_ylabel('Loss SFT'); axes[1,j].set_ylabel('LR użyty do aktualizacji')
        for ax in axes[:,j]: ax.set_xlabel('Krok w eksperymencie');ax.grid(alpha=.2)
    fig.tight_layout();savefig('01_loss_lr.png')
    fig,axes=plt.subplots(2,2,figsize=(12,7))
    for j,runs in enumerate([RUNS[:3],RUNS[3:]]):
        subset=[r for r in steps if r['run'] in runs]
        for key,label in [('used_vram_mib','VRAM globalny po kroku'),('peak_global_vram_mib','Szczyt próbek VRAM')]:
            axes[0,j].scatter([r['step'] for r in subset],[float(r['memory'][key]) for r in subset],s=5,label=label)
        for key,label in [('rss_mib','RSS po kroku'),('peak_rss_mib','Szczyt próbek RSS')]:
            axes[1,j].scatter([r['step'] for r in subset],[float(r['memory'][key]) for r in subset],s=5,label=label)
        for ax in axes[:,j]: ax.set_xlabel('Krok w eksperymencie');ax.set_ylabel('MiB');ax.legend(fontsize=8);ax.grid(alpha=.2)
    axes[0,0].set_title('Eksperyment główny');axes[0,1].set_title('Dodatkowy eksperyment');fig.tight_layout();savefig('02_memory.png')
    fig,axes=plt.subplots(1,3,figsize=(13,4))
    labels=['175','350','Dodatkowe 175']
    axes[0].bar(['Baza NF4','Baza BF16']+labels,[0,0]+[float(r['micro_f1']) for r in overall]);axes[0].set_title('Oficjalne micro-F1, 0,5 ATR');axes[0].tick_params(axis='x',rotation=35)
    for i,k in enumerate(['micro_precision','micro_recall']): axes[1].bar([x+i*.27 for x in range(3)],[float(r[k]) for r in overall],width=.27,label=k.replace('micro_',''))
    axes[1].set_xticks([x+.135 for x in range(3)],labels);axes[1].legend();axes[1].set_title('Precision i recall, 0,5 ATR')
    for i,t in enumerate(['0.25','0.5','1.0']): axes[2].bar([x+i*.25 for x in range(3)],[float(s['tolerances'][t]['overall']['micro_f1']) for s in summaries],width=.25,label=t+' ATR')
    axes[2].set_xticks([x+.25 for x in range(3)],labels);axes[2].legend();axes[2].set_title('Wpływ tolerancji na F1')
    fig.tight_layout();savefig('03_official_metrics.png')
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    for ax,group in zip(axes,['by_symbol','by_side']):
        groups=list(summaries[1]['tolerances']['0.5'][group]);
        for j,i in enumerate([1,2]): ax.bar([x+j*.3 for x in range(2)],[float(summaries[i]['tolerances']['0.5'][group][g]['micro_f1']) for g in groups],width=.3,label=labels[i])
        ax.set_xticks([.15,1.15],groups);ax.set_ylabel('micro-F1, 0,5 ATR');ax.legend()
    fig.tight_layout();savefig('04_groups.png')
    chosen=[next(r for r in pairs if r['zero_tp']),next(r for r in pairs if r['complete']),
            max(pairs,key=lambda r:(r['delta_f1'],r['id'])),min(pairs,key=lambda r:(r['delta_f1'],r['id']))]
    manifest=read(DATA/'manifest.json'); entries={e['id']:e for e in manifest['entries'] if e['split']=='validation'}
    for i,r in enumerate(chosen,1):
        entry=entries[r['id']]
        with (DATA/entry['ohlc']).open(encoding='utf-8') as f: candles=list(csv.DictReader(f))
        fig,axes=plt.subplots(1,3,figsize=(15,4),sharey=True)
        for ax,key,title in zip(axes,['reference','old_predicted','new_predicted'],['Referencja','Adapter 350','Dodatkowe 175']):
            for j,c in enumerate(candles):
                o,h,l,cl=[float(c[k]) for k in ['open','high','low','close']]; color='#16806a' if cl>=o else '#c94c4c'
                ax.vlines(j,l,h,color=color,linewidth=.5);ax.add_patch(Rectangle((j-.32,min(o,cl)),.64,max(abs(cl-o),.00001),color=color,linewidth=.3))
            for side,color,style in [('supports','#1565c0','--'),('resistances','#ef6c00',':')]:
                for price in r[key][side]: ax.axhline(float(price),color=color,linestyle=style,linewidth=.9)
            ax.set_title(title);ax.set_xlabel('Pozycja świecy 0–119');ax.tick_params(labelsize=8)
        axes[0].set_ylabel('USDT');fig.suptitle(f"{r['symbol']} / {r['id']} — S: niebieski, R: pomarańczowy")
        fig.tight_layout();savefig(f'case_{i:02d}.png')
    # Tables are assembled from evaluator output, with no manually copied rounded inputs.
    main_table=table(['Metryka','Krok 175','Krok 350','Dodatkowe 175'],[[k,*[r[k] for r in overall]] for k in
        ['micro_f1','micro_precision','micro_recall','tp','fp','fn','predicted_levels','reference_levels','valid_json_count','complete_set_correct_count','zero_tp_examples']]+[['MAE/ATR (dopasowane)',*[r['price_error']['mae_atr'] for r in overall]]])
    tolerance_table=table(['Tolerancja ATR','175: TP/FP/FN','175: F1','350: TP/FP/FN','350: F1','Dodatkowe: TP/FP/FN','Dodatkowe: F1'],
        [[t,*[v for s in summaries for v in ['/'.join(str(s['tolerances'][t]['overall'][k]) for k in ['tp','fp','fn']),s['tolerances'][t]['overall']['micro_f1']]]] for t in ['0.25','0.5','1.0']])
    group_table=table(['Przekrój','175: TP/FP/FN','F1','350: TP/FP/FN','F1','Dodatkowe: TP/FP/FN','F1'],
        [[g,*[v for s in summaries for v in ['/'.join(str(s['tolerances']['0.5'][group][g][k]) for k in ['tp','fp','fn']),s['tolerances']['0.5'][group][g]['micro_f1']]]] for group in ['by_symbol','by_side'] for g in summaries[0]['tolerances']['0.5'][group]])
    segment_table=table(['Przebieg','Kroki','Nowe przykłady','Narastająco','Status','Suma czasów kroków [s]'],
        [[r['run'],f"{r['first']}–{r['last']}",sum(len(s['ids']) for s in steps if s['run']==r['run']),r['processed_examples'],r['status'],round(float(r['step_seconds_sum']),3)] for r in training])
    resource_table=table(['Przebieg','Peak próbek VRAM [MiB]','Peak próbek RSS [MiB]','Peak allocated [MiB]','Peak reserved [MiB]'],
        [[r['run'],*[round(float(r['memory'][k]),2) for k in ['peak_global_vram_mib','peak_rss_mib','peak_allocated_mib','peak_reserved_mib']]] for r in training])
    baseline=[]
    for precision in ['nf4','bf16']:
        official=ev[f'vlm41-cz2-20261110-1840-{precision}']['summary']['tolerances']['0.5']['overall']
        diag=ev[f'vlm42-price-baseline-20261110-a-{precision}']['price_diagnostics']['metrics']['tolerances']['0.5']['overall']
        baseline.append([precision.upper(),official['valid_json_count'],official['micro_f1'],f"{diag['tp']}/{diag['fp']}/{diag['fn']}",diag['micro_f1']])
    baseline_table=table(['Baza','Oficjalne JSON /36','Oficjalne F1','Diagnostyczne TP/FP/FN','Diagnostyczne F1'],baseline)
    error_table=table(['ID','Symbol','175 dodatkowych: TP/FP/FN','F1 przed → po'],[[r['id'],r['symbol'],f"{r['new_tp']}/{r['new_fp']}/{r['new_fn']}",f"{float(r['old_f1']):.6f} → {float(r['new_f1']):.6f}"] for r in pairs if r['zero_tp'] or r['complete']])
    illustrations='\n\n'.join(f"![Przykład {i}](final45/case_{i:02d}.png)\n\nRysunek {i+4}. ID `{r['id']}`; {r['symbol']}; F1 przy 0,5 ATR: {float(r['old_f1']):.6f} → {float(r['new_f1']):.6f}. Świece przerysowane wyłącznie z istniejącego CSV validation. Oryginalny obraz: `data/datasets/{DATA.name}/{entries[r['id']]['image']}`. Dobór: odpowiednio pierwszy brak trafień, pierwszy kompletny zestaw, największa poprawa i największe pogorszenie (remisy po ID)." for i,r in enumerate(chosen,1))
    cfg=read(Path('results')/RUNS[2]/'effective-config.json'); env=read(Path('results')/RUNS[-1]/'identity.json')['environment']
    environment_table=table(['Biblioteka','Wersja historycznego treningu'],list(env['packages'].items()))
    config_table=table(['Parametr','Eksperyment główny','Eksperyment dodatkowy'],[
        ['Kwantyzacja / compute','NF4 + double quantization / BF16','bez zmian'],['Wizja','zamrożona, BF16','bez zmian'],
        ['LoRA','q_proj/v_proj części językowej; r=8, alpha=16, dropout=0','bez zmian'],['Tensory / parametry LoRA','112 / 1 605 632','112 / 1 605 632'],
        ['AdamW','betas=(0.9,0.999), eps=1e-8, weight_decay=0.01','nowy stan; te same parametry'],
        ['Batch / akumulacja','1 / 4','1 / 4'],['Epoki / aktualizacje','2 / 350','1 / 175 lokalnych'],
        ['LR / warmup','0.0002 / 18','0.00005 / 9'],['Scheduler','linear, horyzont 350','nowy linear, horyzont 175'],
        ['Seed',cfg['pipeline']['seed'],20261112],['Checkpoint','co 25 kroków + początek/koniec odcinka','tak samo'],
        ['Gradient clipping / checkpointing','1.0 / use_reentrant=False','bez zmian'],['Sekwencja / obraz','limit 2048 / 1024×768, 768 tokenów obrazu','bez zmian'],
        ['Attention / urządzenie','SDPA / cuda:0; brak jawnego offloadu','bez zmian']])
    delta=overall[2]['micro_f1']-overall[1]['micro_f1']
    report=f'''# Raport końcowy dostrajania Qwen3-VL — etapy 4.1–4.4

Etap 4.5, data dokumentacji: 2026-11-11. Status: eksperymenty zamknięte,
wybór lokalnego adaptera utrwalony; końcowej oceny testowej nie wykonano.

## 1. Streszczenie

Dostrojono `Qwen/Qwen3-VL-2B-Instruct` do odtwarzania algorytmicznych poziomów
wsparcia i oporu z wykresów kryptowalutowych. Główny eksperyment QLoRA objął
dwie epoki, 350 aktualizacji i 1396 prezentacji przykładów. Po analizie validation
autor zlecił dodatkowy eksperyment jednej epoki: 175 aktualizacji od wyuczonych
wag, z nowym AdamW, schedulerem i RNG. Były to dwa harmonogramy optymalizacji.

Na tych samych 36 validation oficjalne micro-F1 przy 0,5 ATR wyniosło
0,3972125436 po pierwszej epoce, 0,4651162791 po drugiej i 0,4682274247 po
dodatkowej epoce. Wszystkie adaptery zwróciły 36/36 poprawnych odpowiedzi JSON.
Przyrost ostatniego F1 o {float(delta):.10f} wynika z FP 84→82 przy TP=70 i FN=77.
Nie wykazano istotności statystycznej ani poprawy wszystkich podgrup.
Wybrano `results/{RUNS[-1]}/adapter`; adapter 350 zachowano.

## 2. Cel i zakres eksperymentów

Celem jest zgodność cen i stron S/R z etykietami przygotowanymi algorytmicznie,
przy ścisłym kontrakcie wyjściowym. Nie badano rentowności ani prognozy przyszłej
ceny. Etap 4.1 obejmował wykonalność i bazowe BF16/NF4, 4.2 implementację pętli
i kontrolę wznowienia, 4.3 główny trening, 4.4 dalsze uczenie wag. Etap 4.5
obejmuje wyłącznie audyt plików, obliczenia offline, ilustracje i dokumentację.
Nie uruchamiano treningu, Qwen, inferencji GPU, nowych danych ani oceny testu.

## 3. Środowisko sprzętowe i programowe

Historyczny sprzęt: RTX 3060 Ti 8192 MiB, CC 8.6, Ryzen 5 3600X (6/12), około
16 GiB RAM, Windows 10/19045, WDDM. Źródło sprzętu: raport 4.1 część 1
i `results/vlm-feasibility-20261109-210209/`; wersje wykonania poniżej pochodzą
z `identity.json` końcowego przebiegu, Python {env['python']}.

{environment_table}

Środowisko treningowe: `D:/ml-envs/market-levels-vlm`; cache wag poza repozytorium.
Audyt 4.5 korzysta z istniejącego środowiska danych, Matplotlib/Agg oraz osobnego
porównania zaufanych stanów na CPU. Nie jest to nowy pomiar szybkości GPU.

## 4. Dane i ich przygotowanie

Dataset: `{DATA.name}`; katalog `data/datasets/{DATA.name}`.
SHA-256 manifestu: `{selection['dataset_manifest_sha256']}`.
Manifest i wszystkie jego pliki sprawdzono bez regeneracji zbioru.

| Split | BTC real | ETH real | BTC synthetic | ETH synthetic | Razem |
|---|---:|---:|---:|---:|---:|
| Train |129|129|220|220|698|
| Validation |18|18|0|0|36|
| Test (tylko inwentarz) |33|33|0|0|66|
| Razem |180|180|220|220|800|

Całość: 45% realnych / 55% syntetycznych; train: 258/698 = 36,96% realnych
i 440/698 = 63,04% syntetycznych. Obraz ma 1024×768, 120 świec 4h.
`chronological_v1` rozdziela train 2020–2023, validation 2024, test
2025–2026-10. Dokładne granice zatwierdzonych okresów zapisano w zamrożonym
`config.json`; ostatnie otwarcia okresów: 2023-12-31 20:00, 2024-12-31 20:00,
2026-10-31 20:00 UTC. Faktycznie wybrane realne train kończą się
2023-12-30 12:00, validation 2024-12-25 20:00 UTC; oba zaczynają się 1 stycznia
pierwszego roku o 00:00. Historyczny raport 3.5 podaje pokrycie testu
2025-01-01 00:00–2026-10-22 20:00 UTC; nie odczytywano ponownie jego metadanych.

Train: przesunięcie 60 świec (nakładanie wewnątrz treningu), validation/test:
120. Okna nie przekraczają granic splitów; luka 2020-02-19 12:00 UTC nie jest
interpolowana. Realny train wybrano warstwowo chronologicznie, seed 20261107;
validation/test to prefiksy kandydatów. Profile syntetyczne kalibrowano tylko
na treningu i zatwierdzono w kopiach 3.5; syntetyki występują wyłącznie w train.
Mała próba dwóch instrumentów, jednego interwału i jednego stylu wykresu,
dominacja syntetyków w train oraz prefiksowa selekcja ograniczają reprezentatywność.

## 5. Metoda wyznaczania etykiet S/R

Algorytm `sr-extreme-first-1.0.0`: ścisłe ekstrema 3+3, Wilder ATR(14),
delta=0,5 końcowego ATR; wspólne grupowanie H/L o pełnej rozpiętości ≤delta,
bez łączenia łańcuchowego. Cena grupy to mediana wszystkich jej ekstremów
przed filtrowaniem. Wybór reakcji zaczyna od najbardziej skrajnego ekstremum;
usuwa reakcje odległe o mniej niż 5 świec. Wymagane co najmniej dwie reakcje.
Odrzuca poziomy w odległości ≤delta od ostatniego Close. Pozostałe dzieli
względem Close i szereguje według liczby reakcji, ostatniej reakcji, odległości,
ceny i ID, maksymalnie trzy na stronę. Decimal 50 cyfr; ROUND_HALF_UP do centów
przy serializacji; kolizje rozstrzyga ranking. Nie jest to maksymalizacja liczby
reakcji. Nie używa przyszłości poza oknem ani metadanych generatora.

Instrukcja `pl-sr-v1` żąda maksymalnie trzech wsparć i oporów oraz wyłącznie
JSON z listami cen. Źródło: `src/market_levels/datasets/domain/examples.py`,
schemat i `docs/datasets/FORMAT.md`. Obrazy wejściowe nie mają linii referencyjnych;
model nie otrzymuje OHLC, etykiet ani metadanych jako dodatkowego promptu.

## 6. Architektura Qwen3-VL i zastosowanie QLoRA

Rewizja bazowa: `{selection['base_revision']}`;
klasa wykonawcza `Qwen3VLForConditionalGeneration`. Procesor przekształca
obraz w tokeny wizualne, a część językowa generuje autoregresyjnie odpowiedź.
Adaptery niskiego rzędu aktualizują wybrane projekcje uwagi językowej,
przy zamrożonych wagach bazowych. Nie dostrajano enkodera wizualnego.

{config_table}

QLoRA ogranicza pamięć zamrożonych wag dzięki NF4 i uczy mały adapter zamiast
pełnego modelu. Zamrożenie wizji zmniejsza liczbę parametrów objętych gradientami
i koszty stanów optymalizatora. Akumulacja pozwala uzyskać grupę czterech
przykładów przy mikrobatche 1; ostatnia grupa każdej epoki liczy dwa przykłady
(698 = 174×4+2). Jest to wybór wynikający z budżetu 8 GB, z ograniczoną
zdolnością adaptacji wizualnej. `model.visual` i `lm_head` pomijają kwantyzację;
wizja ma BF16, inne zamrożone niekwantyzowane parametry FP32 po PEFT.
Opis mechanizmu oparto na konfiguracji i kodzie projektu. Bibliografia pracy
powinna uzupełnić źródła pierwotne Qwen3-VL, LoRA i QLoRA; nie dodano fikcyjnych cytowań.

## 7. Model bazowy i wyniki przed dostrajaniem

{baseline_table}

Oficjalny `sr-eval-v1` odrzucił wszystkie odpowiedzi bazowe opakowane Markdownem:
TP=0, FP=0, FN=147 dla obu wariantów. To skutek niespełnienia pełnego kontraktu
odpowiedzi, a nie dowód braku rozpoznawania poziomów. Oddzielna diagnostyka 4.2
zdjęła wyłącznie zewnętrzne znaczniki Markdown i uzyskała częściową zgodność cen.
Jej wyniki nie są oficjalnymi wynikami i nie uczestniczą w wyborze checkpointu.
Nie mieszamy ich z oficjalną krzywą F1. Bazowe BF16/NF4 różnią się warunkami
precyzji; głównym punktem odniesienia dla adapterów NF4 jest baza NF4.

## 8. Implementacja pipeline'u treningowego

`training/workflows/pipeline.py` koordynuje istniejące ładowanie, SFT, sampler,
AdamW, scheduler, kontrolę pamięci i zapisy. Superwizja obejmuje tokeny odpowiedzi
i zakończenia; obraz, instrukcja i role prefiksu są maskowane. Loss to średnia
średnich po tokenach nadzorowanych dla przykładów w faktycznej grupie akumulacji.
Nie optymalizuje bezpośrednio micro-F1 ani błędu ATR. Zbyt długie sekwencje są
kontrolowane, a nie cicho obcinane. Gradient clipping = 1, gradient checkpointing
z `use_reentrant=False`, SDPA, TF32 wyłączone, deterministyczność `warn_only`.

Pełne checkpointy zawierają adapter, AdamW, scheduler, sampler i RNG.
Eksport `adapter/` służy inferencji i nie zastępuje pełnego checkpointu.
Tożsamość wiąże konfigurację, dataset, rewizję i środowisko. Wznowienie zapisuje
stan w nowym katalogu; STOP działa na granicy aktualizacji. Walidacja jest osobnym
procesem po treningu. Etap 4.2 obejmował sześć technicznych aktualizacji A=3,
B1=1, B2=2 oraz kontrolę odtworzenia; nie zaliczamy ich do 350+175 aktualizacji
eksperymentów jakości. Historyczna próba 4.1 miała osobny adapter techniczny.

## 9. Przebieg dwuepokowego treningu

{segment_table}

Pierwsze trzy wiersze to jeden eksperyment 1–350 z odtwarzaniem pełnego stanu.
Logi mają komplet kroków, bez duplikatów i luk; każda epoka prezentuje dokładnie
698 train w kolejności `Random(seed+epoch)` nad posortowanymi ID (epoka od zera).
Suma to 1396 przykładów. Resume 25→26 i 175→176 zachowuje sampler i stany;
nie ma ponownej inicjalizacji od rodzica. Ponowne ładowanie modelu w nowym procesie
jest oczekiwane. Jedyną różnicą metadanych początkowego checkpointu wznowienia
jest rosnący `elapsed_seconds` uwzględniający ładowanie; nie resetuje postępu.

Checkpointy: 0,25 w odcinku 1; 25,50,…,175 w odcinku 2; 175,200,…,350
w odcinku 3. Manifesty i wszystkie pliki checkpointów zweryfikowano.
Status końcowy `stopped` jest zgodny z granicami StopAfter/walidacji,
w tym końcem planu. Nie stwierdzono zdarzeń `failed` lub `memory_pressure`.
W dostępnych logach konsoli nie zapisano niezależnych liczbowych kodów wyjścia
procesów treningu; nie deklarujemy historycznego kodu 0 wyłącznie na podstawie statusu.

![Strata i LR](final45/01_loss_lr.png)

Rysunek 1. Surowe wartości loss i LR dla wszystkich 525 kroków; odrębne osie
dla dwóch harmonogramów. Źródło: pięć `events.jsonl`, tabela `training_steps.csv`.
Brak wygładzania i interpolacji. LR w rekordzie jest wartością używaną do danej
aktualizacji: pierwszy krok ma 0, szczyt przypada po warmup, ostatnia aktualizacja
ma jeszcze dodatni LR; scheduler osiąga 0 po niej. To konwencja istniejącej pętli.

## 10. Wyniki pierwszej i drugiej epoki

{main_table}

Wszystkie wartości z trzech oryginalnych `summary.json` odtworzono dokładnie
przez `read_evaluation`. Druga epoka zwiększyła TP 57→70, zmniejszyła FN 90→77,
przy FP 83→84 i F1 +{float(overall[1]['micro_f1']-overall[0]['micro_f1']):.10f}.
Wzrost zgodności obejmuje więc lokalizację względem referencji, nie tylko format.
Skuteczniejsze generowanie schematu po SFT jest zgodne z bezpośrednią superwizją
poprawnych odpowiedzi JSON; bez ablacji nie rozdzielamy przyczyn tego efektu.

Precision=TP/(TP+FP) opisuje udział trafień w przewidzianych poziomach,
recall=TP/(TP+FN) pokrycie referencji, a micro-F1=2TP/(2TP+FP+FN) kompromis
z sum liczności obu stron i wszystkich wykresów. MAE/ATR to średnia |pred−ref|/ATR
wyłącznie dopasowanych par; nie obejmuje wszystkich przewidzianych cen ani FN.
Lepsze MAE przy innym zbiorze par nie gwarantuje lepszego odtworzenia całego zestawu.

## 11. Motywacja dodatkowego eksperymentu

Autor zdecydował o dodatkowej epoce **po obejrzeniu wyników validation** 175/350.
Sprawdzał, czy dalsze uczenie wag poprawi lokalizację. Reguła przed startem 4.4:
wyższe oficjalne micro-F1 przy 0,5 ATR, potem udział JSON, potem wcześniejszy 350.
Źródło: sekcja E instrukcji 4.4 i raport przygotowania. Decyzja ta rozszerza
badanie po analizie walidacji; nie była z góry niezmiennym planem trzech epok.

## 12. Przebieg dodatkowej epoki

Punkt startowy: `results/{RUNS[2]}/adapter`.
Nowy AdamW, nowy linear na 175 lokalnych kroków, warmup 9, LR=0,00005;
nowy sampler/RNG z seed=20261112. Te same 698 obrazów i etykiet oraz ta sama LoRA.
Przebiegi 1–25 i 26–175 są segmentami tego jednego dodatkowego eksperymentu.
Wznowienie drugiego segmentu odtwarza już jego pełny stan, bez ponownego resetu.

`initialized_from_adapter` i `initialization.json`: `tensor_values_exact=true`,
`tensor_count=112`, `trainable_parameters=1605632`; rodzic ma krok 350 i SHA-256
`{selection['preserved_alternative']['adapter_sha256']}`.
`optimizer_state=new`, `scheduler_state=new`, `rng_state=new seed, not inherited`.
Bajty wszystkich tensorów początkowego adaptera są zgodne z rodzicem; sprawdzono
również powiązanie manifestu rodzica i checkpointu z konfiguracją.
Nowy stan nie oznacza resetu przy wznowieniu 26–175. Liczba 525 jest sumą
350+175 aktualizacji dwóch harmonogramów. W nowym etapie przetworzono 698 przykładów.

## 13. Końcowa walidacja i porównanie checkpointów

{tolerance_table}

{group_table}

Końcowe 36 odpowiedzi zawiera 152 poziomy przy 147 referencjach, 2/36 pełnych
zestawów i 3 wykresy bez TP. Nie występują duplikaty cen. Przy 0,5 ATR MAE/ATR
70 dopasowanych par wynosi 0,2212751625 (350: {float(overall[1]['price_error']['mae_atr']):.10f}).
Dokładne wartości i wszystkie przekroje: `final45/verified_metrics.json`.
Większa tolerancja dopuszcza więcej par, stąd wyższe F1 przy 1,0 niż 0,25 ATR;
nie oznacza to nowej predykcji ani bardziej dokładnych cen.

Ostatni przyrost to **dwa mniej FP**, bez wzrostu TP i recall. BTC i supports
poprawiły się, ETH i resistances pogorszyły się. Porównanie jest sparowane na
identycznym fingerprintcie, instrukcji, rewizji i ustawieniach inferencji:
NF4, `do_sample=false`, `num_beams=1`, `max_new_tokens=256`, `use_cache=true`,
budżet 786432 pikseli. Nie zmieniano ustawień generowania ani ewaluatora.

![Oficjalne metryki](final45/03_official_metrics.png)

Rysunek 2. Oficjalne F1/P/R i tolerancje ATR. Zerowa baza jest wynikiem rygoru
formatu; diagnostyki po zdjęciu Markdown nie pokazano jako oficjalnej serii.

![Przekroje](final45/04_groups.png)

Rysunek 3. Dwa ostatnie adaptery według instrumentu i strony, na tych samych validation.

## 14. Analiza błędów

FP=82 oznacza wskazania niedopasowane do algorytmicznej referencji przy 0,5 ATR;
FN=77 to pominięte poziomy referencyjne. Nie każde FP jest ekonomicznie bezsensowne.
Niedokładna cena może dać równocześnie FP i FN; matching nie rozdziela automatycznie
przyczyn wizualnych, semantycznych i błędnej liczby poziomów. Wsparcia i opory
dopasowuje się osobno, maksymalizując TP, następnie minimalizując błąd i remisy indeksów.

{error_table}

Pełne sparowane porównanie 36 przykładów: `final45/paired_validation.csv`.
F1 przykładów wzrosło w 6, spadło w 8, pozostało równe w 22. Równe F1
nie dowodzi identycznych cen. Zmiany są nierówne, mimo dodatniego micro-F1 ogółem.
Największa poprawa: `d6bf408fd0b0d23877ae60a0`; największy spadek (remis po ID):
`7c14d9de5f11728d769fb10d`. Tabele tolerancji pokazują, jak część wskazań
przechodzi z FP/FN do TP po rozszerzeniu progu; nie zmieniamy oficjalnego 0,5 ATR.

Istniejąca diagnostyka względem Close wykazała w końcowym adapterze 10/90
wsparć po niewłaściwej stronie Close i 1/62 oporów; po 6/36 pustych list obu stron.
Adapter 350 miał odpowiednio 14/93 i 1/61 wskazań po niewłaściwej stronie oraz
5/36 pustych list supports i 6/36 resistances. Nie przekłada się to bezpośrednio
na sumę FP, ponieważ dopasowanie cen i ta diagnostyka mają różne kryteria.
To osobne proxy, a nie dodatkowa kara w oficjalnym F1. Weryfikacja tych liczności
odtworzyła istniejącą diagnostykę wyłącznie na 36 CSV validation. Źródło:
`results/{NAMES[-1]}/price-diagnostics/diagnostics.json`.
Hipotezy obejmują zaokrąglanie cen do typowych wartości, trudność odczytu osi,
ograniczoną pojemność adaptera i niedopasowanie syntetyków do realnych wykresów;
nie przeprowadzono ablacji dowodzącej ich udziału.

{illustrations}

## 15. Analiza wykorzystania zasobów

{resource_table}

![Pamięć](final45/02_memory.png)

Rysunek 4. Próbki po krokach i skumulowane szczyty próbek w obrębie procesu,
nie ciągły zapis fizycznej pamięci. Reset licznika przy nowym procesie jest oczekiwany.
WDDM i cache alokatora powodują, że `reserved` może przekraczać fizyczne 8192 MiB;
nie należy go sumować z globalnym VRAM ani nazywać ilością fizycznego VRAM.
Nie zmierzono osobno stronicowania. Peak globalnych próbek osiągnął 7969 MiB
w treningu głównym i 7988 MiB w dodatkowym; próbkowanie może ominąć krótkie piki.
Pomiary RSS nie są całkowitym zajęciem RAM systemu. W logach są również dostępny
RAM i commit; sumy czasów kroków wykluczają przerwy między procesami i część
operacji ładowania/zapisu. Brak porównywalnego profilu wszystkich etapów 4.1/4.2
nie pozwala tworzyć wspólnego benchmarku. Nie przeprowadzono nowych pomiarów GPU.

## 16. Ograniczenia metodologiczne

698 train, 63,04% syntetyków, zamrożona wizja i LoRA wyłącznie q/v ograniczają
zakres uczenia. SFT minimalizuje loss tokenów, nie miarę zbioru poziomów ani błąd
ATR. Budżet 8 GB ogranicza konfigurację, a etykiety algorytmiczne nie zastępują
pełnej oceny eksperckiej. Nadal występuje wiele FP/FN; tylko 2/36 pełnych zestawów.

36 validation, po 18 na instrument, daje ograniczoną pewność wniosków.
Wielokrotna ocena i decyzja o dalszym eksperymencie na tym samym validation
zwiększają ryzyko dopasowania wyboru do walidacji. Nie liczono przedziałów ufności
ani testu istotności; niewielki przyrost F1 nie dowodzi istotnej poprawy.
Okna dwóch instrumentów mogą współdzielić warunki rynkowe, więc nie należy
zakładać niezależności wszystkich obserwacji. Wyniki validation z 2024 r. nie są
jeszcze oceną generalizacji na późniejszych okresach.

## 17. Wybór ostatecznego modelu

Wybrany adapter: `results/{RUNS[-1]}/adapter`, lokalny krok 175 nowego eksperymentu.
SHA-256 pliku wag: `{selected_hash}`.
SHA-256 manifestu adaptera: `{selection['adapter_manifest_sha256']}`.
Oficjalna walidacja: `{NAMES[-1]}`;
SHA-256 jej `summary.json`: `{selection['validation_summary_sha256']}`.
Pełne powiązanie konfiguracji, checkpointu, danych, rewizji i walidacji:
[FINAL_MODEL_SELECTION.json](FINAL_MODEL_SELECTION.json).

Reguła ustalona przed dodatkowym eksperymentem wybiera większe oficjalne F1
0,4682274247 zamiast 0,4651162791; remis nie wystąpił. Alternatywny adapter
`results/{RUNS[2]}/adapter` i jego checkpointy pozostają zachowane.
Zamrożenie oznacza zapis lokalnych tożsamości i kontrolę hashy, nie podpis
autentyczności ani blokadę zapisu w systemie plików. Dane wymagane do identyfikacji
są dostępne; kody wyjścia nie są wymaganym identyfikatorem wyboru i ich braku nie ukrywamy.

## 18. Wnioski z eksperymentów

Dostrajanie poprawiło realizację kontraktu JSON i zgodność poziomów z etykietami
algorytmicznymi na validation. Druga epoka zwiększyła liczbę trafień; dodatkowy
eksperyment dał niewielki zysk przez ograniczenie FP. Brak dużego zysku może być
zgodny z ograniczoną adaptacją, małą próbą lub plateau SFT, ale nie dowodzi żadnej
z tych przyczyn. Nie uzasadnia to twierdzeń o niezawodnej analizie technicznej
ani przydatności inwestycyjnej. Autor zamknął eksperymenty bez kolejnych epok,
nowych danych i zmian protokołu.

## 19. Przygotowanie do końcowej oceny na teście

Test 66 realnych wykresów pozostaje odłożony do osobnej decyzji po niezależnym
audycie. Nie generowano odpowiedzi testowych i nie analizowano jego etykiet
w celu wyboru modelu. Hashowanie bajtów całego datasetu służyło ochronie integralności.
Po osobnej autoryzacji należy zachować wybrany adapter, rewizję, prompt,
ustawienia inferencji, dataset i `sr-eval-v1`, opublikować komplet surowych odpowiedzi
i pełne metryki. Nie dostrajać po obejrzeniu testu. Niniejszy dokument nie uruchamia
ani nie zatwierdza ewaluacji testowej. Nie podaje wyników testowych.

## 20. Wykaz źródeł danych, konfiguracji, logów i załączników

- `AGENTS.md`, `.ai/`, `docs/ARCHITECTURE.md`; raporty 3.5 części 1/2,
  4.1 części 1/2, 4.2, przygotowania 4.3 i 4.4, instrukcje PowerShell 4.2–4.4.
- `docs/labeling/RAPORT_3_4.md`, `docs/datasets/FORMAT.md`,
  `docs/evaluation/PROTOKOL_3_6.md`, kod protokołu i instrukcji `pl-sr-v1`.
- `configs/vlm/` i zamrożony dataset (`manifest.json`, `config.json`, `plan.json`).
- Pięć przebiegów w tabeli 9: `result.json`, `identity.json`,
  `effective-config.json`, `events.jsonl`, `model.json`, `preflight.json`,
  manifesty/metadane checkpointów, eksporty adapterów i dostępne logi konsoli.
- Pięć oficjalnych ocen w `results/evaluation/` (dwie bazy i 175/350/dodatkowa),
  `summary.json`, `predictions.jsonl`, `per_example.jsonl`, binding i manifesty.
  Dwa osobne wyniki `vlm42-price-baseline-20261110-a-{{nf4,bf16}}` są diagnostyczne.
- `final45/SOURCES.json` zawiera ścieżki, rozmiary i SHA-256 źródeł;
  `final45/verified_metrics.json`, CSV, wykresy, audyt CPU i kontrola integralności
  stanowią załączniki. Pełny lokalny inwentarz przed pracą pozostaje poza małym ZIP.

Końcowa kontrola: 14 204 historyczne pliki bez zmiany SHA-256 i bez usunięć,
w tym 3212 plików datasetu; sprawdzono wszystkie manifesty checkpointów pięciu
segmentów. Dokładne stany optymalizacji/RNG porównano na trzech granicach CPU,
bez inicjalizacji CUDA. [Raport integralności](final45/INTEGRITY_REPORT.md),
[wykaz źródeł](final45/SOURCES.json), [kontrole](final45/checks.json)
oraz [dowód CPU](final45/cpu-states.json) utrwalają zakres i wynik audytu.

Nie znaleziono odrębnego dokumentu z formalnym tematem i wymaganiami uczelnianymi
pracy; nie rekonstruowano go. Nie ma osobnego raportu końca wykonania 4.3/4.4
poza oryginalnymi artefaktami i tym raportem; dokumenty przygotowania opisują
historyczny stan. Brak niezależnego zapisu kodów zakończenia wskazano w sekcji 9.
Status niewykorzystania testu opiera się na deklaracji autora, dostępnych artefaktach
i zakresie tej pracy; lokalny audyt nie dowodzi nieistnienia zewnętrznych uruchomień.
'''
    (DOC/'RAPORT_KONCOWY_DOSTRAJANIA_4_1_4_4.md').write_text(report,encoding='utf-8')
    (ASSETS/'tables.md').write_text('# Tabele źródłowe raportu 4.5\n\n'+ '\n\n'.join([config_table,segment_table,baseline_table,main_table,tolerance_table,group_table,resource_table,error_table])+'\n',encoding='utf-8')
    print('Report, frozen selection, tables, 8 figures and CSV written')


if __name__=='__main__':
    main()
