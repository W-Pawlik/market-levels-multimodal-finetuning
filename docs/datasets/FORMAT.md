# Format neutralny VLM, wersja 1

W małej próbie `examples.jsonl`, a w produkcji `splits/train.jsonl`,
`splits/validation.jsonl` i `splits/test.jsonl` zawierają po jednym obiekcie na wiersz.
Każdy obiekt ma dokładnie
`id`, `split`, `image`, `instruction`, `answer`. `answer` jest obiektem JSON,
nie tekstem zawierającym JSON. Ceny są liczbami zapisanymi z dwoma miejscami
po przecinku; puste listy są poprawne, ranking pozostaje kolejnością list.
Schemat: [dataset_example.schema.json](../../configs/dataset_example.schema.json).
Nie dodano biblioteki JSON Schema; weryfikator sprawdza kontrakt przez ponowne
obliczenie i porównanie całego rekordu oraz jego dokładnej serializacji.

```json
{"id":"stabilne-id", "split":null, "image":"images/000.png", "instruction":"Przeanalizuj przedstawiony wykres świecowy. Wskaż maksymalnie trzy poziomy wsparcia i trzy poziomy oporu. Zwróć wyłącznie obiekt JSON z polami supports i resistances, zawierającymi listy wartości cenowych.", "answer":{"supports":[16732.31,16543.59], "resistances":[16869.26]}}
```

To ilustracja formatu, nie wynik etykietowania konkretnego obrazu. Jedyną wersją
instrukcji jest `pl-sr-v1` w `datasets/packaging.py`. Schemat utrwala jej treść.
W produkcji `split` jest `train`, `validation` albo `test`.
W historycznej małej próbie jest zawsze `null`, a manifest ma status
`diagnostic_only_not_final_splits`. Identyfikator jest skrótem SHA-256 symbolu,
źródła, ID pierwotnego okna i kanonicznego OHLC. Nie zależy od katalogu wyjścia.
Produkcja zachowuje realne ID z planu (`Window.document`). Syntetyczne ID
wiąże symbol, train, seed, OHLC i identyfikator zatwierdzonego profilu.

Model otrzyma obraz i instrukcję, a odpowiedź będzie celem uczenia. Pola ID,
split i ścieżka służą organizacji danych. **Metadanych nie należy dodawać do
wiadomości dla modelu.** Obecnie nie powstał adapter konkretnego dostawcy/modelu.

Każdy przykład ma osobno:

- `images/NNN.png`: oryginalny styl renderera, 1024 × 768, bez poziomów S/R.
- `ohlc/NNN.csv`: dokładnie te same 120 świec, ceny Decimal bez obniżania precyzji.
- `labels/NNN.json`: odpowiedź `LabelResult.target_json()`, bez pośredniej konwersji do float.
- `metadata/NNN.json`: symbol, źródło, zakres realnego okna, profil/seed syntetyka,
  skopiowany rekord źródłowego pilotażu (w tym indeksy i identyfikatory plików),
  wersje algorytmu i renderera, SHA-256 PNG/CSV/kanonicznego OHLC/etykiety,
  parametry odtworzenia i metryki audytowe. Daty indeksu syntetycznego nie są
  przedstawiane jako czas obserwacji rynku.

W produkcji zamiast `NNN` stosuje się stabilny 24-znakowy identyfikator.
Wspólne profile zapisano raz w `profiles/`, pełną konfigurację w `config.json`,
plan w `plan.json` i środowisko z UUID przebiegu w `run.json`.
Metadane syntetyczne zachowują reżimy, parametry, strumienie RNG i przebieg
zmienności, bez powielania całego profilu przy każdym przykładzie.

`manifest.json` wiąże rekordy i hashe wszystkich plików w katalogu. Jego własny
hash jest w `manifest.sha256`. To kontrola przypadkowych zmian, nie podpis
kryptograficzny ani ochrona przed napastnikiem podmieniającym wszystkie hashe.
`SOURCE_INTEGRITY.json` przypina wejścia przed i po pracy. Ścieżki względne są
kontrolowane po rozwiązaniu; wyjście poza katalog, w tym przez symlink, jest
odrzucane. Weryfikacja nie wymaga dużych oryginalnych CSV.

`summary.json` opisuje liczbę przykładów, źródła, instrumenty, lata rzeczywistych
okien, ruch netto, zmienność, liczby poziomów i braków oraz podobne charakterystyki.
Definicja podobieństwa jest jawna i opisowa: symbol, obserwowany kierunek,
std log-zwrotów zaokrąglone do 0.001, liczby wsparć i oporów. Nie steruje wyborem
okien. Syntetyczny rok 2000 nie trafia do rozkładu lat rzeczywistych.

Plan jest osobnym artefaktem: `plan.json` przechowuje zatwierdzone granice,
liczebności, kandydatów w ujęciu zbiorczym, wszystkie wybrane realne ID/indeksy,
niekwalifikujące się początki siatki, profile i zaplanowane seedy syntetyczne.
Status `plan_only_not_dataset` oznacza, że nie powstały finalne obrazy/etykiety.

Gotowy zbiór ma manifest `kind: production_dataset`, `status: complete`.
Powstaje przez atomową publikację dopiero po pełnym odczycie, ponownym
etykietowaniu, renderowaniu i regeneracji wszystkich syntetyków. Po publikacji
wykonuje się osobną kontrolę z dysku. Nakładanie realnych okien treningu
jest dozwolone; validation/test są rozłączne w obrębie instrumentu.
W plikach produkcji nie ma overlays. Oddzielna diagnostyka ma własny manifest
`production_review_samples` i jawne `overlay_is_vlm_input: false`.

Odtwarzanie bajtów PNG wymaga zgodnego Matplotlib, fontów i renderera. Algorytm
etykiet działa w swoim stałym kontekście Decimal, a pełna precyzja diagnostyki
pozostaje w module etykietowania. BTC i ETH z tego samego okresu są powiązane
rynkowo; nakładające się treningowe okna również nie są niezależnymi próbkami.
