# Konfiguracja eksperymentu

Punktem wejścia pozostaje [experiment.json](experiment.json). CLI przyjmuje
dotychczasowe `--config`; jawne argumenty CLI nadal nadpisują ustawienia JSON.
Całość jest jedną konfiguracją logiczną, z parametrami zapisanymi w jednym miejscu.

| Plik | Odpowiedzialność |
| --- | --- |
| experiment.json | Rynek, instrumenty, pobieranie, wspólne rozmiary/przesunięcia i odwołania do sekcji |
| data/chronological_split.json | Zatwierdzone granice treningu, walidacji i testu |
| synthetic/generation.json | Ustawienia V1 i V2 oraz wspólne reżimy |
| synthetic/calibration.json | Seedy i siatki kalibracji V2 |
| synthetic/refinement.json | Kandydaci, tolerancje, wagi i limity refinement |
| datasets/build.json | Docelowe liczebności, profile, seed wyboru i master seed |
| dataset_example.schema.json | Schemat rekordu zbioru, nie schemat konfiguracji |

## Odwołania do plików

Wartość pola głównego może być jawnym odwołaniem:

```json
{
  "synthetic": {
    "$file": "synthetic/generation.json",
    "$section": "synthetic"
  }
}
```

`$file` jest względny wobec katalogu pliku wejściowego. `$section` wybiera
pole główne wskazanego JSON-a; bez niego używana jest cała zawartość pliku.
Fragmenty zawierają dane, bez łańcuchów kolejnych odwołań. Nie ma automatycznego
przeszukiwania katalogów, dziedziczenia, scalania ani dodatkowej warstwy nadpisywania.
Kolejność pól i list oraz wartości i typy parametrów pozostają zachowane.

Pozostałe ścieżki, np. output, profile i katalog historii, nadal są względne
wobec **CWD uruchomienia**, jak przed podziałem. Nie są przeliczane względem fragmentu.
Walidację parametrów wykonuje właściwy etap; pobieranie nie waliduje generatora.

## Pełne pliki i odtwarzalność

Dotychczasowe samodzielne JSON-y nadal działają. Do utworzenia własnej pełnej
konfiguracji w kodzie służy `market_levels.shared.configuration.read_configuration`.
Zwykłe `json.loads(experiment.json)` pokazuje teraz odwołania, nie złożony dokument.

Budowa zbioru zapisuje do wynikowego `config.json` samodzielną konfigurację
bez odwołań. Dla wejściowego pełnego JSON-a zachowuje jego oryginalne bajty.
Inwentarze źródeł i kontrola wznowienia obejmują plik wejściowy oraz wszystkie
referowane fragmenty. Zmiana fragmentu jest wykrywana tak samo jak zmiana wejścia.
Historyczne config.json, manifesty i checkpointy nie są przepisywane.

Przy `verify --check-sources` starego zbioru jego przypięty pełny plik
konfiguracji może być obecnie zapisany jako fragmenty tylko wtedy, gdy da się
z nich odtworzyć dokładnie bajty zachowanego config.json o przypiętym SHA-256.
Zmiana wartości lub typów nadal powoduje błąd. Pozostałe źródła oraz wszystkie
fragmenty przypięte przez nowe plany zachowują ścisłą kontrolę surowych bajtów.
Budowa na podstawie nieaktualnego preflightu nie korzysta z tego wyjątku.

Pola `target_total_charts` i `target_*_share` pozostają historycznym opisem.
Liczebności budowy sterowane są przez `dataset_build.targets`. Pola
`chart_*_px_initial` nadal nie sterują rendererem; podział konfiguracji nie
aktywuje nowych parametrów i nie zmienia wyglądu wykresów.
