"""Render the 4.6B document from audited artifacts; package only small evidence."""
from pathlib import Path
from decimal import Decimal
import hashlib
import zipfile

from market_levels.evaluation.protocol import loads, dumps
from market_levels.shared.integrity import sha256_file


ROOT = Path('docs/vlm')
OUT = ROOT/'final46b'
REPORT = ROOT/'RAPORT_4_6B_KONCOWA_EWALUACJA_TESTOWA.md'


def read(path):
    return loads(path.read_text(encoding='utf-8-sig'))


def f(value):
    return 'null' if value is None else f'{value:.10f}'


def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |', '|'+ '|'.join('---' for _ in headers)+'|',
                      *('| '+' | '.join(str(x) for x in row)+' |' for row in rows)])


def main():
    metrics = read(OUT/'verified_metrics.json')
    diag = read(OUT/'diagnostic_base_summary.json')
    val = read(OUT/'validation_metrics.json')
    audit = read(OUT/'execution_audit.json')
    integrity = read(OUT/'integrity.json')
    selection = read(ROOT/'FINAL_MODEL_SELECTION.json')
    ft = metrics['finetuned-nf4']['tolerances']['0.5']
    sections = ['''# Etap 4.6B — końcowa ewaluacja testowa Qwen3-VL

Data dokumentacji: 2026-11-12 (Europe/Warsaw). Status: końcowa ewaluacja
zakończona; raport opracowany offline na podstawie istniejących artefaktów.
W tabelach zastosowano kropkę dziesiętną i zaokrąglenie do 10 miejsc;
załączniki JSON zachowują precyzję ewaluatora.

## 1. Cel i zakres

Przedmiotem badania jest odtwarzanie algorytmicznie wyznaczonych poziomów
wsparcia i oporu na podstawie obrazu wykresu. Jednorazowo porównano bazowy
Qwen3-VL-2B-Instruct w NF4 z tym samym modelem i adapterem wybranym przed
testem. Ocena obejmuje 66 zamrożonych wykresów, główne micro-F1 przy 0.5 ATR
oraz pomocnicze tolerancje 0.25 i 1.0 ATR.

Etap dokumentacyjny obejmował odczyt i kontrolę sum plików, odtworzenie ocen,
agregację przekrojów oraz historyczną diagnostykę zdejmowania zewnętrznego
Markdown. Nie uruchomiono Qwen, treningu, nowej inferencji, CUDA ani nowych
eksperymentów. Oficjalne pliki wynikowe pozostały niezmienione.

## 2. Zamrożenie konfiguracji

Wybór z 2026-11-11 utrwala `FINAL_MODEL_SELECTION.json`. Wybrano adapter
`results/vlm44-part2-17554-5354/adapter`, lokalny krok 175 dodatkowego
eksperymentu po głównych 350 aktualizacjach. Dodatkowy eksperyment miał nowy
AdamW, scheduler i RNG; nie był prostym przedłużeniem jednego harmonogramu.
Test nie uczestniczył w wyborze checkpointu. Nie dokonano ponownego wyboru
po poznaniu wyników testowych.

| Element | Wartość zamrożona |
|---|---|
| Model bazowy | `Qwen/Qwen3-VL-2B-Instruct` |
| Rewizja | `89644892e4d85e24eaac8bacfd4f463576704203` |
| SHA-256 wag adaptera | `20cbbb8e39ca636108d9533e8e8cc4543371b48eb322fff97999a9b8454ebdf6` |
| SHA-256 manifestu adaptera | `cc11b18830876107d075b560d8abe37b718c46f22725e2d0cbf430b73bae1c83` |
| SHA-256 pliku wyboru | `287e45bd688de30293b129a536086133be380116202ca74a0fe69c6ab9bd921e` |
| SHA-256 efektywnej konfiguracji treningu | `b5c69a9a4820b892af669feca6b6f1090b431c8d8bd2861829148f924896f2ef` |
| Protokół / instrukcja | `sr-eval-v1` / `pl-sr-v1` |

Hash pliku wyboru jest zgodny z planem zapisanym w sesji testowej i raportem
4.6A. Historyczne pole `test_evaluation_run=false` w pliku wyboru opisuje
moment zamrożenia w etapie 4.5; zachowano je jako dowód pierwotnej decyzji.
Bieżący status zakończenia testu dokumentuje niniejszy raport.

## 3. Charakterystyka zbioru testowego

Źródło: `data/datasets/ds35-800-20261107-a`. Zbiór produkcyjny ma
698 train, 36 validation i 66 test. Test zawiera wyłącznie realne okna
Binance spot, po 33 BTCUSDT i ETHUSDT; syntetyki występują jedynie w train.
Każdy obraz ma 1024×768 pikseli i przedstawia 120 świec 4h bez linii
referencyjnych. Zatwierdzony podział `chronological_v1` obejmuje train
2020–2023, validation 2024 i test 2025–2026-10. Metadane faktycznie
wybranych testowych okien potwierdzają zakres od 2025-01-01 00:00 do
2026-10-22 20:00 UTC. Okna validation/test mają krok 120 świec i nie
przekraczają granic splitów; test jest prefiksem kandydatów.
''']
    sections.append(table(['Instrument','Wykresy','Wsparcia referencyjne','Opory referencyjne','Poziomy razem'],
        [[symbol,33,ft['by_symbol_side'][symbol]['supports']['reference_levels'],
          ft['by_symbol_side'][symbol]['resistances']['reference_levels'],ft['by_symbol'][symbol]['reference_levels']]
         for symbol in ('BTCUSDT','ETHUSDT')]+[['Razem',66,139,118,257]]))
    sections.append('''
Referencje wytworzono metodą `sr-extreme-first-1.0.0`: ścisłe ekstrema 3+3,
Wilder ATR(14), grupowanie w rozpiętości 0.5 końcowego ATR, minimum dwie
reakcje oddalone o co najmniej pięć świec, podział względem ostatniego Close
i maksymalnie trzy poziomy na stronę. Etykiety reprezentują operacyjną definicję
S/R, nie niezależny konsensus ekspertów ani obiektywną prawdę rynkową.

## 4. Warunki inferencji

Oba warianty wykonano w osobnych wywołaniach procesu Pythona, kolejno baza,
a następnie model dostrojony. Potwierdzają to dwa logi inferencji z kodem 0,
osobne zdarzenia ładowania i zakończenia oraz sposób uruchomienia w
`scripts/run_vlm_final_test.ps1`. Baza została wznowiona po blokadzie zasobów
przy `committed_answers=0`. Nie ma ponownego generowania zatwierdzonych ID.
Nie zachowano niezależnego rejestru PID; wniosek o oddzielnych procesach opiera
się na zapisanych wykonaniach i runnerze.

| Parametr | Oba warianty |
|---|---|
| Kwantyzacja | NF4, double quantization |
| Typ obliczeń / wizja | BF16 / BF16 |
| Inne zamrożone części niekwantyzowane | przygotowanie PEFT, FP32 |
| Attention / urządzenie | SDPA / cuda:0, bez CPU/disk offload |
| Obraz / budżet / minimum | 1024×768 / 786432 / 65536 pikseli |
| Tokeny obrazu / wejścia | 768 / 845 dla każdego z 132 rekordów |
| Generowanie | `do_sample=false`, `num_beams=1`, `max_new_tokens=256`, `use_cache=true` |
| Seed inferencji | 20261109 |
| Instrukcja | pl-sr-v1; bez few-shot |
| Dekodowanie | skip_special_tokens=True, clean_up_tokenization_spaces=False |

Sprawdzono identyczność zapisanych konfiguracji generowania, procesora,
tokenizera, środowiska oraz kolejności ID. Przy `do_sample=false` zapisane
domyślne temperature=0.7, top_k=20 i top_p=0.8 nie oznaczają próbkowania.
Model otrzymywał obraz i instrukcję; ID, symbol, OHLC i etykiety nie stanowiły
dodatkowego promptu. Inferencja nie parsowała referencji przed ukończeniem
obu wariantów.

Środowisko historyczne: Windows 10/19045, Python 3.12.12, RTX 3060 Ti
8192 MiB; torch 2.10.0+cu128, torchvision 0.25.0+cu128, transformers 5.3.0,
peft 0.18.1, bitsandbytes 0.49.2, accelerate 1.12.0, pillow 12.1.1.
Pełny wykaz wersji znajduje się w `final46b/execution_audit.json`.

Finetuned ładował adapter jako `is_trainable=False`, bez merge. Zapisana
kontrola potwierdza dokładną równość wszystkich 112 tensorów z eksportem.
Kod wykonania wymusza `requires_grad=False`, brak gradientów, `eval()`
i `torch.inference_mode()`; nie tworzy optymalizatora. Oba `result.json`
i zdarzenia ładowania potwierdzają `no_optimizer_updates=true`.

Poniższe maksima dotyczą zapisanych pomiarów **generowania odpowiedzi**;
nie obejmują całego czasu ładowania modelu.
''')
    sections.append(table(['Wariant','Peak próbek VRAM [MiB]','Peak próbek RSS [MiB]','Peak allocated [MiB]','Peak reserved [MiB]'],
        [[v,*[f"{audit['execution'][v][k]:.2f}" for k in ('sample_peak_vram_mib','sample_peak_rss_mib','peak_allocated_mib','peak_reserved_mib')]] for v in metrics]))
    sections.append(f'''
Próbkowanie może pominąć krótkie piki. RSS nie jest całkowitym RAM systemu;
reserved to rezerwacja alokatora, której nie sumuje się z globalnym VRAM.
Nie wykonano nowych pomiarów sprzętowych.

## 5. Kontrola integralności i audyt wykonania

Sesja: `adc19862-27f6-4327-a478-1554818da3f3`; dwa różne run_id z sufiksami
`-base-nf4` i `-finetuned-nf4`. Oba warianty zawierają 66 rekordów i 66
surowych odpowiedzi. Zweryfikowano manifesty, łańcuchy hashy rekordów,
zgodność `predictions.jsonl` z rekordami oraz zgodność wejść ocen z surowymi
przebiegami. Brakujące, powtórzone i obce ID nie występują.

Ponowne wywołanie wyłącznie kontrolnego `verify_pair` offline zakończyło się
poprawnie. `read_evaluation` odtworzył dokładnie `per_example.jsonl`,
`summary.json` i raporty tekstowe obu wariantów, a `read_comparison` sprawdził
porównanie wraz z kopiami obu ocen. Sprawdzono także historyczną validation,
wzory metryk i sumy przekrojów. Oficjalny fingerprint referencji testowych:
`{audit['binding_fingerprint']}`.
Jest wspólny dla obu ocen. Fingerprint wejść obrazowych inferencji:
`086698fa04fff5b8466e1cfc2f8e4986dced0dc18692722d23ad86085988a06d`.
Są to dwa różne zakresy identyfikacji.

Kontrola przed/po dokumentacji objęła **{integrity['protected_files']} plików**,
w tym wszystkie **3212 plików datasetu**: brak zmian, usunięć i dodanych
plików w kontrolowanych źródłach. Sprawdzono aktualne bajty bazy i procesora
według 11 zapisanych pozycji tożsamości, wybrany adapter, efektywną konfigurację,
manifesty, protokół, kod sesji i wybór modelu. `final46b/SOURCES.json` określa
dokładny zakres i SHA-256 każdego chronionego pliku. Wynik nie jest podpisem
autentyczności ani dowodem nieistnienia zewnętrznych uruchomień.

Audyt zachowuje wszystkie 20 dostępnych rekordów zakończenia 4.6.
Poniżej podano identyfikatory plików `results/vlm46-<tryb>-<ID>.exit.json`;
pełne ścieżki, czasy UTC i końcówki konsoli są w `execution_audit.json`.
''')
    sections.append(table(['Tryb','ID logu','Kod'], [[e['mode'],e['source'].split('/')[-1].removesuffix('.exit.json').removeprefix('vlm46-'+e['mode']+'-'),e['exit_code']]
        for e in sorted(audit['exit_codes'], key=lambda e:e['utc'])]))
    sections.append('''
Niezerowe kody obejmują brak jawnej zgody, niedozwolony dataset, zajętość GPU
453>450 MiB, próby kontroli/oceny i uruchomienia wariantu dostrojonego przed
powstaniem manifestu bazy oraz próbę utworzenia istniejącego wariantu bez resume.
Pierwsza baza zakończyła się przed generowaniem; wznowienie z zera ukończyło 66
odpowiedzi. Końcowe `verify-pair` (dwukrotnie) i `score-pair` mają kod 0;
istnieją trzy kompletne oficjalne raporty. Baza zakończyła generowanie
o 21:02:38 UTC, finetuned rozpoczął o 21:06:56 i zakończył o 21:12:55 UTC.
Ocenę zakończono o 21:14:15 UTC, po obu przebiegach.

Odmowa `Variant already complete; rerun/resume is forbidden` z kodem 1
po zakończeniu inferencji była **oczekiwanym działaniem zabezpieczenia**
jednorazowości. Nie stanowi niekompletności wyników ani powodu do powtarzania
inferencji. W obu plikach events zapisano po 14 ostrzeżeń DeprecationWarning
dotyczących `torch.jit.script_method`; zachowano także oryginalne logi konsoli
z komunikatami bibliotek i miejscowymi zniekształceniami kodowania tekstu.

## 6. Oficjalne wyniki

Micro-precision=TP/(TP+FP), micro-recall=TP/(TP+FN),
micro-F1=2TP/(2TP+FP+FN). Liczności sumuje się po stronach i wykresach.
Wsparcia i opory dopasowuje się osobno, jeden do jednego, przy
|pred−ref|≤k·ATR; maksymalizuje się liczbę TP, następnie minimalizuje błąd,
a remisy rozstrzyga leksykograficznie indeksami. Nie zmieniono progów ani
metody. Wartość `null` oznacza niezdefiniowany iloraz, a nie zero.
''')
    rows=[]
    for v,s in metrics.items():
        for k,c in s['tolerances'].items():
            g=c['overall']; rows.append([v,k,g['tp'],g['fp'],g['fn'],f(g['micro_precision']),f(g['micro_recall']),f(g['micro_f1']),f"{g['valid_json_count']}/66",f(g['price_error']['mae_atr'])])
    sections.append(table(['Wariant','ATR','TP','FP','FN','Precision','Recall','Micro-F1','JSON','MAE/ATR'],rows))
    sections.append('''
Wszystkie 66 odpowiedzi bazowych narusza ścisły kontrakt JSON przez zewnętrzne
ogrodzenie Markdown (`invalid_json: 66`). Protokół przypisuje takim odpowiedziom
TP=FP=0 i FN równe wszystkim 257 referencjom. Oficjalnie liczba odczytanych
poziomów wynosi 0; precision i MAE są niezdefiniowane. Nie oznacza to braku
cen w surowym tekście. F1=0 jest wynikiem całego zadania wraz z formatem.

Model dostrojony zwrócił 66/66 odpowiedzi spełniających pełny schemat, 277
poziomów wobec 257 referencji i zero duplikatów. Przy 0.5 ATR uzyskał 109 TP,
168 FP i 148 FN. MAE/ATR=0.2402191219 dotyczy wyłącznie 109 dopasowanych
par (109 z poprawną normalizacją; brak par wyłączonych przez ATR=0).
Brak pełnych zestawów: 0/66; bez TP pozostaje 9/66 wykresów.
Przy 0.25 ATR pełnych zestawów jest 0/66, bez TP 27/66; przy 1.0 ATR
odpowiednio 5/66 i 4/66. Wzrost F1 z tolerancją nie jest poprawą samych cen.

## 7. Analiza diagnostyczna modelu bazowego

**Poniższa tabela jest analizą diagnostyczną, odrębną od oficjalnego testu.**
Zastosowano istniejącą funkcję `inference.domain.price_diagnostics.unwrap_fence`,
realizującą historyczną regułę usuwania wyłącznie zewnętrznego ogrodzenia
Markdown. Reguła pochodzi z analiz etapów 4.1–4.2 i była udokumentowana
przed testem. Wszystkie 66 odpowiedzi miały zewnętrzne znaczniki otwierające
<code>```json</code> i zamykające <code>```</code>; po ich zdjęciu wszystkie spełniły ścisły schemat.
Nie zmieniano cen, list, kolejności, liczby poziomów ani innych fragmentów tekstu.

Wynik przeliczono offline z zapisanych referencji i odpowiedzi przez te same
`parse_response`, `score_example` i `aggregate` protokołu sr-eval-v1.
Nie dodano reguł naprawy ani filtrów. Pliki `diagnostic_base_*` przechowują
przekształcone teksty, wyniki jednostkowe i agregaty, bez nadpisania oryginałów.
''')
    sections.append(table(['Analiza diagnostyczna: ATR','TP','FP','FN','Precision','Recall','F1','MAE/ATR'],
        [[k,g['tp'],g['fp'],g['fn'],f(g['micro_precision']),f(g['micro_recall']),f(g['micro_f1']),f(g['price_error']['mae_atr'])]
         for k,c in diag['tolerances'].items() for g in [c['overall']]]))
    sections.append('''
Potwierdzono wstępne niezależne przeliczenie: F1 0.1470137825, 0.2235834609
i 0.3307810107. Przy 0.5 ATR baza diagnostycznie ma 396 przewidzianych
poziomów, 257 referencji oraz TP/FP/FN=73/323/184. Liczba 396=66×6 wskazuje
na maksymalną liczbę poziomów w każdym odczytanym zestawie. Te wartości
nie zastępują oficjalnego F1=0 i nie uczestniczą w wyborze modelu.

## 8. Porównanie modelu bazowego i dostrojonego

Oficjalne sparowane porównanie obejmuje identyczny fingerprint referencji,
model bazowy, rewizję, instrukcję i ustawienia inferencji. Poniższe różnice
candidate−baseline odczytano z odtworzonego `comparison.json`.
''')
    comp=read(OUT/'official_comparison.json')
    delta=comp['delta_candidate_minus_baseline']
    # The comparison tree mirrors the summary tolerances.
    sections.append(table(['ATR','ΔTP','ΔFP','ΔFN','ΔPrecision','ΔRecall','ΔF1','ΔJSON [p.p.]'],
        [[k,g['tp'],g['fp'],g['fn'],f(g['micro_precision']),f(g['micro_recall']),f(g['micro_f1']),g['valid_json_percent']]
         for k,c in delta['tolerances'].items() for g in [c['overall']]]))
    sections.append(f'''
Oficjalny przyrost F1 przy 0.5 ATR wynosi 0.4082397004, a poprawności JSON
100 punktów procentowych. Wzrost oficjalnego FP z 0 do 168 nie oznacza
pogorszenia lokalizacji: baza z błędnym formatem nie dostarczała ewaluatorowi
odczytanych predykcji. Różnica precision jest niezdefiniowana, ponieważ
bazowe precision ma zerowy mianownik. Na poziomie wykresów F1 wzrosło
w 57 przypadkach, pozostało równe w 9, nie spadło w żadnym.

Pomocnicze zestawienie lokalizacji po zdjęciu Markdown z bazy wskazuje
F1 0.2235834609 wobec oficjalnego 0.4082397004 finetuned, różnicę
{f(ft['overall']['micro_f1']-diag['tolerances']['0.5']['overall']['micro_f1'])},
TP 73→109, FP 323→168 i FN 184→148. Stanowi to opisową przesłankę poprawy
zgodności poziomów poza samym formatem. Porównanie korzysta z różnych
warunków przetwarzania odpowiedzi, dlatego zachowuje status diagnostyczny;
bez ablacji nie rozdziela przyczyn poprawy.

## 9. Porównanie validation i test

Wybrany model i próg 0.5 ATR pozostają te same; porównywane zbiory mają
różne liczebności i okresy, dlatego nie jest to porównanie sparowane.
''')
    sections.append(table(['Split','Okres','Wykresy','TP/FP/FN','Precision','Recall','F1','JSON','MAE/ATR'],
        [[name,period,g['examples'],f"{g['tp']}/{g['fp']}/{g['fn']}",f(g['micro_precision']),f(g['micro_recall']),f(g['micro_f1']),f"{g['valid_json_count']}/{g['examples']}",f(g['price_error']['mae_atr'])]
         for name,period,g in [('Validation','2024',val['tolerances']['0.5']['overall']),('Test','2025–2026-10',ft['overall'])]]))
    sections.append(f'''
Spadek F1 wynosi {f(-audit['validation_test_f1_delta'])}, czyli około 0.059988
(około 6.00 punktów procentowych skali F1). Pomocniczo F1 przy 0.25 ATR
zmienia się 0.2876254181→0.2247191011, a przy 1.0 ATR
0.6688963211→0.5955056180. Zachowana poprawność JSON przy niższych P/R
wskazuje na ograniczenie zgodności lokalizacji i liczby poziomów w późniejszym
okresie, a nie na ponowne załamanie formatu odpowiedzi.

Możliwe wyjaśnienia obejmują zmianę warunków rynkowych, skali cen,
charakterystyk okien i składu referencji oraz ograniczoną reprezentatywność
train/validation. Wielokrotna analiza 36 validation i decyzja o dodatkowej
epoce po obejrzeniu walidacji mogły sprzyjać dopasowaniu wyboru do tego zbioru.
Sam spadek nie stanowi dowodu przeuczenia. Nie wykonano testu istotności,
bootstrapu ani przedziałów ufności; nie deklaruje się istotności statystycznej.

## 10. Analiza jakości i błędów

Poniższe przekroje przedstawiają model dostrojony przy głównym 0.5 ATR.
W pełnym `final46b/metrics.csv` zapisano oba modele, diagnostykę oraz wszystkie
przekroje dla trzech tolerancji. Oficjalna baza ma F1=0 w każdym z tych
przekrojów wskutek błędnego formatu wszystkich odpowiedzi.
''')
    group_rows=[]
    for label,g in [*ft['by_symbol'].items(),*ft['by_side'].items(),
                    *[(symbol+'/'+side,g) for symbol,sides in ft['by_symbol_side'].items() for side,g in sides.items()]]:
        group_rows.append([label,g['examples'],g['tp'],g['fp'],g['fn'],f(g['micro_precision']),f(g['micro_recall']),f(g['micro_f1']),f(g['price_error']['mae_atr'])])
    sections.append(table(['Przekrój','N','TP','FP','FN','Precision','Recall','F1','MAE/ATR'],group_rows))
    sections.append('''
BTCUSDT uzyskuje F1=0.3220973783 wobec ETHUSDT=0.4943820225.
Wsparcia (0.4406779661) są odtwarzane skuteczniej niż opory (0.3682008368),
a najniższe F1 w kombinacjach instrument×strona mają opory BTC
(0.2586206897). W BTC bez TP pozostaje 7/33 wykresów, w ETH 2/33.
MAE dopasowanych par w USDT wynosi 293.2881395349 dla BTC (43 pary)
i 12.3077272727 dla ETH (66 par); nie należy uśredniać tych skal dolarowych
jako głównego globalnego błędu. Porównywalniejszy MAE/ATR wynosi odpowiednio
0.2598578932 i 0.2274241648.

Poziomy referencyjne to 139 wsparć i 118 oporów; model zwrócił 156 i 121.
Poprawnie puste wsparcia występują w 12/14 przypadków pustej referencji
(85.71%), a opory w 7/18 (38.89%). Mianowniki obejmują wyłącznie puste
referencje danej strony. Nie ma referencji pustych po obu stronach ani
poprawnych odpowiedzi modelu pustych po obu stronach. Medianowe F1 wykresu
wynosi 0.4, kwartyle 0.25 i 0.5928571429, maksimum 0.8571428571;
średnie F1 wykresów 0.4048428003 jest odrębne od głównego micro-F1.

Trzy poniższe przypadki wskazał autor jako błędy skali; nie stanowią losowej
próby ani rankingu wszystkich błędów. Zachowano oryginalne ceny, bez mnożenia
przez dziesięć i bez dodatkowego przeliczania jakości po korekcie.
''')
    def prices(levels):
        return '; '.join(side+': ['+', '.join(f'{x:.2f}' for x in values)+']' for side,values in levels.items())
    cases=read(OUT/'error_cases.json')
    sections.append(table(['ID (BTCUSDT)','Predykcja [USDT]','Referencja [USDT]','TP/FP/FN (0.5 ATR)'],
        [[f"`{r['id']}`",prices(r['predicted']),prices(r['reference']),'/'.join(str(r['scores']['0.5'][k]) for k in ('tp','fp','fn'))] for r in cases]))
    sections.append('''
Predykcje są około dziesięciokrotnie niższe od referencji. Wszystkie trzy
odpowiedzi są poprawnym JSON, ale nie mają TP także przy 1.0 ATR.
Łącznie dają 14 FP i 13 FN przy głównym progu. Jest to zgodne z hipotezą
błędu odczytu osi lub pominięcia cyfry w generowaniu, lecz same artefakty
nie pozwalają rozstrzygnąć mechanizmu. Poprawny format nie gwarantuje
poprawności skali ceny.

FP i FN nie są rozłącznymi przyczynami błędu: przesunięta cena może jednocześnie
pozostać niedopasowaną predykcją i pozostawić referencję bez trafienia.
Nie każde FP oznacza ekonomicznie bezsensowny poziom; oznacza brak zgodności
z przyjętą referencją i tolerancją. Nie stosowano filtrów względem Close,
korekt skali ani dodatkowej kary poza zamrożonym protokołem.

## 11. Interpretacja i ograniczenia

Uzyskany wynik potwierdza poprawę realizacji kontraktu wyjściowego i częściowe
odtwarzanie referencji na późniejszym okresie. Nadal 168/277 przewidzianych
poziomów pozostaje niedopasowanych, 148/257 referencji nie zostaje odnalezionych,
a pełny zestaw przy 0.5 ATR nie został odtworzony na żadnym wykresie.
Niski MAE dopasowanych par nie opisuje błędu wszystkich predykcji i nie
kompensuje licznych FP/FN. Różnice MAE między wariantami lub tolerancjami
dotyczą różnych zbiorów par.

Badanie ograniczają 66 wykresów, dwa instrumenty, jeden interwał i styl
renderowania, prefiksowy wybór testu oraz współzależność warunków rynkowych
BTC i ETH. Nie należy traktować 66 okien jako 66 niezależnych sytuacji
rynkowych. Train ma 440/698 syntetyków (63.04%), podczas gdy test jest realny.
Zamrożony enkoder wizualny, LoRA q_proj/v_proj i budżet 8 GB ograniczają
adaptację. SFT optymalizuje stratę tokenową, a nie bezpośrednio zbiór poziomów
lub micro-F1. Nie wykonano ablacji rozdzielającej te czynniki.

Jest to **odtwarzanie poziomów referencyjnych, a nie sprawdzian rentowności
handlu**. Nie przeprowadzono backtestu strategii, oceny zysków, kosztów,
ryzyka, wykonania zleceń ani prognozy przyszłych cen. Wyniki nie uzasadniają
twierdzeń o rentowności lub niezawodności inwestycyjnej.

## 12. Wnioski końcowe

Jednorazowa para ewaluacyjna została ukończona i zabezpieczona: po 66
odpowiedzi, zgodne warunki oraz trzy oficjalne raporty. Wybrany adapter
pozostał niezmieniony, bez aktualizacji wag w etapie testowym.

Model dostrojony osiągnął oficjalne micro-F1=0.4082397004 przy 0.5 ATR
i 66/66 poprawnych odpowiedzi JSON. Oficjalne F1 bazy wynosi 0 ze względu
na format, a osobna diagnostyka wykazuje częściowe rozpoznawanie poziomów
przez bazę (F1=0.2235834609). Dostrajanie wiąże się z poprawą formatu
i opisową poprawą zgodności cen, przy wciąż znacznej liczbie błędów.

Niższe F1 testowe niż validation wskazuje na ograniczenia generalizacji,
bez dowodu przeuczenia lub istotności statystycznej. Wynik testu nie zmienił
wyboru modelu, datasetu, protokołu ani tolerancji. Etap zamknięto dokumentacją;
nie uruchomiono kolejnych eksperymentów ani ponownej inferencji.

## 13. Wykaz źródłowych artefaktów i sum kontrolnych

Źródłami interpretacji są `FINAL_MODEL_SELECTION.json`,
`RAPORT_KONCOWY_DOSTRAJANIA_4_1_4_4.md`, `RAPORT_4_6A_PRZYGOTOWANIE_TESTU.md`,
`SZABLON_RAPORTU_4_6B.md` oraz `docs/evaluation/PROTOKOL_3_6.md`.
Opisy niewykorzystania testu w dokumentach 4.5 i 4.6A są historyczne.
Poniższa tabela podaje SHA-256 bajtów plików; hash reguł protokołu jest
osobnym identyfikatorem kanonicznej treści:
`dafd622fc17e78fe9e095d0849b4a4ae1f8a748d203a3b8fa48a373e4b3ccf58`.
''')
    sources=[ROOT/'FINAL_MODEL_SELECTION.json',ROOT/'RAPORT_KONCOWY_DOSTRAJANIA_4_1_4_4.md',ROOT/'RAPORT_4_6A_PRZYGOTOWANIE_TESTU.md',ROOT/'SZABLON_RAPORTU_4_6B.md',
             Path('docs/evaluation/PROTOKOL_3_6.md'),Path('data/datasets/ds35-800-20261107-a/manifest.json'),
             Path(selection['selected_adapter'])/'adapter_model.safetensors',Path(selection['effective_config_path']),
             Path('results/vlm46-final-test/session.json')]
    for v in ('base-nf4','finetuned-nf4'):
        sources += [Path('results/vlm46-final-test')/v/n for n in ('manifest.json','predictions.jsonl')]
        sources += [Path('results/evaluation')/f'vlm46-final-test-{v}'/n for n in ('manifest.json','summary.json','per_example.jsonl')]
    sources += [Path('results/evaluation/vlm46-final-test-comparison')/n for n in ('manifest.json','comparison.json')]
    sections.append(table(['Plik (ścieżka od katalogu projektu)','SHA-256'],[[f'`{p.as_posix()}`',f'`{sha256_file(p)}`'] for p in sources]))
    sections.append('''
Pełny wykaz chronionych plików i rozmiarów: [SOURCES.json](final46b/SOURCES.json).
Kontrola integralności: [integrity.json](final46b/integrity.json).
Audyt procesów, kodów i manifestów: [execution_audit.json](final46b/execution_audit.json).
Zweryfikowane oficjalne metryki: [verified_metrics.json](final46b/verified_metrics.json),
[metrics.csv](final46b/metrics.csv), [porównanie](final46b/official_comparison.json).
Diagnostyka: [diagnostic_base_summary.json](final46b/diagnostic_base_summary.json),
odrębne predictions/per_example w tym samym katalogu. Przypadki błędów:
[error_cases.json](final46b/error_cases.json). Historyczna validation:
[validation_metrics.json](final46b/validation_metrics.json).

Procedura odtworzenia audytu: `.venv/Scripts/python.exe scripts/audit_vlm46b.py`
z katalogu projektu, wyłącznie do nowego katalogu wyjściowego (skrypt odmawia
nadpisania `final46b`). Nie wymaga środowiska VLM; nie importuje torch ani
transformers. Dokument renderuje `scripts/build_vlm46b_report.py`.

Mała paczka `handoff/vlm46b-final-report-20261112.zip` zawiera raport,
zestawienia, skrypty dokumentacyjne, audyt, źródła metryk, logi i kody
zakończenia oraz manifest zawartości. Nie zawiera wag, adapterów, checkpointów,
obrazów, OHLC ani całego datasetu. Małe bindingi referencji są częścią
źródłowych raportów ewaluatora. SHA-256 ZIP zapisano obok archiwum;
wewnętrzny `PACKAGE_MANIFEST.json` umożliwia kontrolę każdego pliku.
''')
    REPORT.write_text('\n\n'.join(s.strip() for s in sections)+'\n',encoding='utf-8')
    # Explicit allowlist: no model/cache/dataset payloads.
    package=[REPORT, *[p for p in OUT.iterdir() if p.is_file() and p.name != 'test_metadata.json'],
             Path('scripts/audit_vlm46b.py'),Path('scripts/build_vlm46b_report.py'),
             ROOT/'FINAL_MODEL_SELECTION.json',ROOT/'RAPORT_4_6A_PRZYGOTOWANIE_TESTU.md',ROOT/'SZABLON_RAPORTU_4_6B.md',
             ROOT/'RAPORT_KONCOWY_DOSTRAJANIA_4_1_4_4.md',
             Path('docs/evaluation/PROTOKOL_3_6.md'),Path('configs/vlm/final-test.json')]
    package += [p for p in Path('results/evaluation').glob('vlm46-final-test-*/*') if p.is_file()]
    package += [p for p in Path(selection['validation_path']).iterdir() if p.is_file()]
    package += [p for p in Path('src/market_levels/evaluation').rglob('*.py')]
    package += [Path('src/market_levels/inference/domain/price_diagnostics.py')]
    package += sorted(Path('results').glob('vlm46-*.exit.json')) + sorted(Path('results').glob('vlm46-*.console.log'))
    package += [Path('results/vlm46-final-test')/v/n for v in ('base-nf4','finetuned-nf4')
                for n in ('manifest.json','manifest.sha256','predictions.jsonl','run.json','result.json','events.jsonl')]
    package += [Path('results/vlm46-final-test/session.json'),Path('results/vlm46-final-test/session.sha256')]
    manifest={p.as_posix():{'bytes':p.stat().st_size,'sha256':sha256_file(p)} for p in sorted(set(package))}
    archive=Path('handoff/vlm46b-final-report-20261112.zip')
    archive.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in manifest: z.write(name,name)
        z.writestr('PACKAGE_MANIFEST.json',dumps({'files':manifest,'note':'Evidence subset; original manifests reference some files kept only in the repository.'})+'\n')
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name,entry in manifest.items():
            data=z.read(name)
            assert len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256']
    Path(str(archive)+'.sha256').write_text(sha256_file(archive)+'  '+archive.name+'\n',encoding='ascii')
    print(dumps({'report':REPORT.as_posix(),'zip':archive.as_posix(),'bytes':archive.stat().st_size,'files':len(manifest)}))


if __name__ == '__main__':
    main()
