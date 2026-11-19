"""Validate documentation links, catalogue original evidence and package stage 4.5.

No model/data mutation, training or inference. Run from the repository root.
"""
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from collections import Counter
from pathlib import Path

from market_levels.shared.integrity import sha256_file

AUDIT=Path('results/vlm45-final-audit-20261111-a')
ASSETS=Path('docs/vlm/final45')
REPORT=Path('docs/vlm/RAPORT_KONCOWY_DOSTRAJANIA_4_1_4_4.md')


def write(p,v):
    Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def main():
    integrity=read(AUDIT/'integrity-summary.json')
    assert not integrity['changed'] and not integrity['removed']
    checks=read(AUDIT/'checks.json');assert all(r['passed'] for r in checks)
    cpu=read(AUDIT/'cpu-states.json');assert cpu['cuda_initialized'] is False
    # Catalogue every available VLM result/config/identity/events/checkpoint manifest,
    # including preparatory and technical runs, without treating them as new training.
    original=read(AUDIT/'inventory-before.json')
    sources={}
    for name,entry in original.items():
        p=Path(name)
        include=(name.startswith(('configs/','docs/vlm/','docs/evaluation/','docs/datasets/','docs/labeling/',
                                 'src/market_levels/evaluation/','src/market_levels/training/',
                                 'src/market_levels/inference/','src/market_levels/modeling/'))
                 or name in ['docs/ARCHITECTURE.md','docs/DECYZJE_3_3.md']
                 or name.startswith('results/vlm') and p.suffix in ('.json','.jsonl','.log','.sha256')
                 or name.startswith('results/evaluation/')
                 or name.startswith('data/datasets/ds35-800-20261107-a/') and p.name in
                    ['manifest.json','manifest.sha256','config.json','plan.json','run.json','SOURCE_INTEGRITY.json'])
        if include and p.suffix not in ('.safetensors','.pt','.png'):
            assert sha256_file(p)==entry['sha256']
            sources[name]=entry
    for p in [Path('AGENTS.md'),*Path('.ai').glob('*.md'),Path('README.md')]:
        sources[p.as_posix()]={'sha256':sha256_file(p),'bytes':p.stat().st_size,'scope':'current documentation'}
    catalogue=[]
    for name in sources:
        p=Path(name)
        if not name.startswith('results/vlm'):continue
        if p.name=='result.json':
            d=read(p); sampler=d.get('sampler',{})
            catalogue.append({'path':name,'status':d.get('status'),'global_step':sampler.get('global_step'),
                'processed_examples':sampler.get('processed_examples'),'kind':'recorded result'})
        elif p.name=='events.jsonl':
            records=[json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
            catalogue.append({'path':name,'events':dict(Counter(r.get('event') for r in records)),
                              'kind':'event catalogue; detailed 525-step audit separate'})
        elif p.name in ('identity.json','effective-config.json'):
            d=read(p)
            catalogue.append({'path':name,'top_level_fields':list(d),'kind':'parsed metadata'})
    write(ASSETS/'SOURCES.json',{'hash_algorithm':'SHA-256','files':sources,
          'note':'Historical entries are pre/post verified; active instructions labelled separately. No dataset test labels parsed.'})
    write(ASSETS/'source_catalogue.json',catalogue)
    for name in ['checks.json','cpu-states.json','integrity-summary.json','dataset.json']:
        shutil.copyfile(AUDIT/name,ASSETS/name)
    text=REPORT.read_text(encoding='utf-8')
    assert len(re.findall(r'^## \d+\.',text,re.M))==20
    links=re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',text)
    # The integrity report is written below, before the final link assertion.
    assert all((REPORT.parent/target.split('#')[0]).exists() or target=='final45/INTEGRITY_REPORT.md' for target in links)
    selection=read('docs/vlm/FINAL_MODEL_SELECTION.json')
    assert sha256_file(Path(selection['selected_adapter'])/'adapter_model.safetensors')==selection['adapter_sha256']
    assert sha256_file(Path(selection['preserved_alternative']['path'])/'adapter_model.safetensors')==selection['preserved_alternative']['adapter_sha256']
    assert not selection['test_evaluation_run'] and not selection['test_used_for_selection']
    # The exact tabulated numbers are generated directly from verified evaluator output.
    validation={'report_sections':20,'local_links':len(links),'missing_links':[],
                'historical_files_unchanged':integrity['historical_files'],
                'dataset_files_unchanged':integrity['dataset_files'],
                'source_files_hashed':len(sources),'audit_checks':len(checks),
                'cpu_checkpoint_pairs':len(cpu['pairs']),'application_tests_run':False,
                'validation_basis':'exact offline evaluator replay, arithmetic/group checks, state comparison, SHA-256 and document validation'}
    write(ASSETS/'document_validation.json',validation)
    (ASSETS/'INTEGRITY_REPORT.md').write_text(f'''# Kontrola integralności etapu 4.5

Data: 2026-11-11. Wynik: zaliczono kontrole offline.

- {integrity['historical_files']} historycznych plików: brak zmian bajtów i usunięć.
- {integrity['dataset_files']} plików datasetu: identyczny inwentarz i SHA-256.
- Kod ewaluatora, konfiguracje, dawne raporty, adaptery i checkpointy bez zmian.
- Pięć oficjalnych ocen: dokładne odtworzenie zapisanych predykcji i referencji
  przez istniejący `read_evaluation`; manifesty i reguły zgodne z sr-eval-v1.
- Dwa bazowe raporty diagnostyczne sprawdzono osobno; diagnostyki Markdown/Close
  obu baz oraz dwóch końcowych adapterów odtworzono istniejącymi funkcjami.
- Formuły precision/recall/F1, sumy TP/FP/FN i poziomów według instrumentu i strony
  sprawdzone dla wszystkich tolerancji; oficjalny verifier wymaga dokładnego Decimal.
- Wszystkie 525 kroków i deterministyczne kolejności 698 train/epokę zgodne;
  brak luk, duplikatów kroków, NaN/Inf, zdarzeń failed lub memory_pressure w pięciu segmentach.
- Efektywne konfiguracje zgodne z identity i między segmentami swoich eksperymentów;
  rewizja, LoRA, LR/warmup, batch i kwantyzacja zgodne z raportem.
- Wszystkie manifesty checkpointów pięciu segmentów i eksportów sprawdzone.
  112 tensorów / 1 605 632 parametrów potwierdzone nagłówkami safetensors.
- Początkowe wagi dodatkowego eksperymentu dokładnie równe rodzicowi;
  eksporty zgodne z końcowymi checkpointami i identyfikatorami walidacji.
- CPU: dokładna zgodność AdamW, schedulera, RNG i samplera na trzech granicach
  wznowienia, poza jawnie wyłączonym elapsed_seconds ładowania/setupu.
  Początkowy AdamW 4.4 nie ma momentów, scheduler zaczyna w 0, RNG różni się od rodzica.
- Adapter wybrany i alternatywny zachowane, hashe w FINAL_MODEL_SELECTION.json.
- Nie uruchomiono Qwen, treningu, inferencji GPU ani testu. CPU nie inicjalizowało CUDA.
  Test był odczytywany tylko jako bajty do SHA-256; nie analizowano jego etykiet/OHLC.
- Brak niezależnie zapisanego liczbowego kodu wyjścia historycznych treningów;
  status stopped, ukończone kroki i manifesty nie zastępują tego dowodu.
- Bieżące .ai i README uzupełniono o zamknięcie; wcześniejsze zmiany autora zachowano.
  Historyczne raporty i aktywny kod produkcyjny nie były zmieniane w 4.5.
- Nie wykonywano commit/push/reset/clean/stash. Nie dodawano testów aplikacji:
  zmiana dotyczy dokumentacji i analizy istniejących dowodów.

Dowody: checks.json, cpu-states.json, integrity-summary.json, document_validation.json,
SOURCES.json, CSV i verified_metrics.json. Pełny inventory-before.json i zapis
git-before.txt pozostają lokalnie w results/vlm45-final-audit-20261111-a.
Hashy nie należy traktować jako podpisu autentyczności. Audyt nie może wykluczyć
zewnętrznych uruchomień; niewykorzystanie testu jest deklaracją autora wspartą
dostępnymi artefaktami i zakresem wykonanych tutaj działań.
''',encoding='utf-8')
    assert all((REPORT.parent/target.split('#')[0]).exists() for target in links)
    output=Path('handoff/vlm45-final-report-20261111-a.zip')
    assert not output.exists(),f'Refusing to overwrite {output}'
    paths=[REPORT,Path('docs/vlm/FINAL_MODEL_SELECTION.json'),*[p for p in ASSETS.iterdir() if p.is_file()],
           *[Path('scripts')/n for n in ['audit_vlm45.py','check_vlm45_states_cpu.py','build_vlm45_report.py','package_vlm45.py']]]
    # Small original reports allow an independent numerical audit without shipping weights/dataset.
    for name in ['vlm41-cz2-20261110-1840-nf4','vlm41-cz2-20261110-1840-bf16',
                 'vlm42-price-baseline-20261110-a-nf4','vlm42-price-baseline-20261110-a-bf16',
                 'vlm43-validation-step175-26351-3437','vlm43-validation-step350-9320-26567','vlm44-validation-4184-25636']:
        paths.extend(p for p in (Path('results/evaluation')/name).iterdir() if p.is_file())
    for name in ['checks.json','cpu-states.json']:
        assert (ASSETS/name).exists()
    payload={p.as_posix():{'sha256':sha256_file(p),'bytes':p.stat().st_size} for p in sorted(set(paths))}
    readme=(
        'Etap 4.5: raport docs/vlm/RAPORT_KONCOWY_DOSTRAJANIA_4_1_4_4.md.\n'
        'Manifest obejmuje bajty wszystkich załączonych plików poza nim samym.\n'
        'Oryginalne małe raporty ewaluacji dołączono w results/evaluation.\n'
        'Skrypty wymagają istniejącego repozytorium/pakietu market_levels; audit/build wymagają lokalnych artefaktów.\n'
        'CPU state checker wymaga istniejącego środowiska VLM oraz zaufanych checkpointów.\n'
        'Brak wag, adapterów, state.pt, datasetu, środowiska i cache.\n'
        'Test nie został uruchomiony; osobna decyzja autora po audycie.\n').encode('utf-8')
    payload['README_HANDOFF.txt']={'sha256':hashlib.sha256(readme).hexdigest(),'bytes':len(readme)}
    manifest_bytes=(json.dumps({'kind':'vlm45_documentation_handoff','files':payload},ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(set(paths)):
            assert p.suffix not in ('.pt','.safetensors','.zip')
            z.write(p,p.as_posix())
        z.writestr('MANIFEST_SHA256.json',manifest_bytes)
        z.writestr('README_HANDOFF.txt',readme)
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
        for name,entry in payload.items():
            assert hashlib.sha256(z.read(name)).hexdigest()==entry['sha256']
    digest=sha256_file(output)
    output.with_suffix('.zip.sha256').write_text(digest+'  '+output.name+'\n',encoding='ascii')
    output.with_suffix('.manifest.json').write_bytes(manifest_bytes)
    write(AUDIT/'handoff.json',{'path':output.as_posix(),'sha256':digest,'bytes':output.stat().st_size,'files':len(payload)})
    print(json.dumps({'path':output.as_posix(),'sha256':digest,'bytes':output.stat().st_size,'files':len(payload)}))


if __name__=='__main__':
    main()
