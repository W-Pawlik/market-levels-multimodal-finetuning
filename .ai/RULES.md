# Trwałe zasady projektu

## Zakres i prostota

Projekt jest jedną aplikacją badawczą do pracy inżynierskiej o dostrajaniu modelu
multimodalnego do poziomów wsparcia i oporu. Implementuj etap zlecony przez autora.
Nie dopisuj przyszłych funkcji wyłącznie dlatego, że przygotowano dla nich katalog.
Zlecenie wdrożenia kolejnego etapu upoważnia do jego implementacji; instrukcje
opisujące wcześniejszy stan nie są zakazem rozwoju.

Stosuj jeden moduł na spójną odpowiedzialność. Preferuj proste funkcje i standardowe
struktury. Nie buduj frameworka, mikroserwisów, ogólnego klienta giełd ani klas
Repository/Factory/Service bez konkretnej potrzeby. Nie dodawaj atrap klas,
NotImplementedError ani pustych konfiguracji na zapas.

## Architektura i nazwy

- Katalog projektu: market-levels-multimodal-finetuning.
- Pakiet: market_levels, w src-layout. Dystrybucja: market-levels.
- Kod obsługi danych: src/market_levels/data_processing/.
- Główny data/ przechowuje artefakty danych, nie kod.
- Nie przywracaj src/download_data.py, src/validate_data.py ani src/__init__.py bez wyraźnego zlecenia.
- Importuj market_levels; wewnątrz pakietu używaj importów względnych. Nie poprawiaj importów przez ręczne modyfikowanie sys.path.
- Oddzielaj model i walidację od HTTP i zapisu. Pipeline koordynuje funkcje; main obsługuje argumenty i błędy.
- W aktywnych obszarach utrzymuj podział domain / workflows / io / reporting / config,
  tworząc tylko potrzebne role. Core grupuje wspólne modele i obliczenia;
  shared operacje techniczne. Nie importuj workflow, I/O ani CLI do domain,
  obszarów aplikacji do core/shared ani CLI do biblioteki. Nie dodawaj cykli,
  także przez importy wewnątrz funkcji. Kontrola środowiska runnera może sprawdzić
  importowalność istniejących CLI; nie przenoś takich kontroli do algorytmów.
  Szczegóły i świadome API są w ARCHITECTURE.md.
- Nazwy kodu pisz po angielsku. Dokumentację projektu i wyjaśnienia dla autora pisz po polsku.
- Dodawaj zrozumiałe typowanie i krótkie docstringi tam, gdzie pomagają; unikaj nadmiaru komentarzy.

## Konfiguracja jest aktywna

Domyślnie CLI wczytuje configs/experiment.json; --config wskazuje inny plik.
Jawne argumenty CLI mają pierwszeństwo przed JSON. Ścieżki konfiguracji i wyjścia
są względne wobec katalogu uruchomienia.

Nie zastępuj konfiguracji stałymi w CLI. Nowe faktycznie konfigurowalne parametry
podłącz do odpowiedniego etapu i sprawdź ich działanie. Nie opisuj parametrów
przyszłego etapu jako aktywnych przed implementacją. Nieobsługiwane ustawienia
muszą powodować czytelny błąd zamiast cichego ignorowania.

## Ochrona danych i kontrakt istniejącego procesu

Podczas refaktoryzacji zachowuj logikę, wyjątki, formaty, nazwy i lokalizacje
wyników, o ile autor nie zlecił świadomej zmiany. Błąd wykryty przy okazji opisz
oddzielnie; nie zmieniaj reguł badawczych pod pozorem porządkowania kodu.

- Nie usuwaj ani nie nadpisuj lokalnych danych podczas prac porządkowych, także gdy Git je ignoruje.
- Nie uruchamiaj automatycznie pobierania całej historii. Zwykłe testy mają działać bez Internetu.
- Rzeczywisty CLI zapisuje CSV i raporty pod tymi samymi nazwami. Próby wykonuj w osobnym katalogu tymczasowym z kopiami potrzebnych archiwów.
- Zachowuj SHA-256 i CHECKSUM, źródłowe ZIP oraz metadane pochodzenia i licencji.
- Czytaj ZIP bez niebezpiecznego wypakowywania jego zawartości.
- Zachowuj Decimal dla cen, UTC oraz obsługę znaczników ms/µs.
- Nie interpoluj luk. Zachowuj kontrolę OHLC, granic świec, duplikatów, ciągłości i zgodności okresu.
- Obecny nagłówek CSV: open_time_utc,open,high,low,close.
- Fallback dzienny pozostaje ograniczony do ostatniego zakończonego miesiąca i dotychczasowych warunków; zmiana reguły wymaga świadomego zakresu zadania.

## Decyzje badawcze i licencja

Nie zmieniaj zatwierdzonych parametrów w konfiguracji ani reguł etykietowania
bez zlecenia autora. Nie utożsamiaj wartości roboczych z ostatecznie zatwierdzonymi.
Nie wybieraj samodzielnie modelu, hiperparametrów, podziałów danych ani technologii
tylko po to, aby wypełnić przyszłe katalogi.

Nie publikuj i nie dołączaj automatycznie danych rynkowych, danych pochodnych,
wag, adapterów ani checkpointów. Zachowuj dokumenty decyzji i zastrzeżenia
licencyjne. Nie utożsamiaj licencji kodu z licencją danych i nie przedstawiaj
istniejącej notatki jako nowej weryfikacji prawnej.

## Zależności, artefakty i rzetelność

Działający proces danych używa biblioteki standardowej. Nie dodawaj Pandas ani
ciężkich bibliotek ML lub wykresów do samego pobierania. Zależności kolejnego
zleconego etapu dodawaj dopiero wraz z implementacją, z jasno określonym zakresem.

Nie edytuj ręcznie build/, *.egg-info/, .venv/ ani cache jako sposobu zmiany
aplikacji. Są generowane. Zmian dokonuj w źródłach i konfiguracji pakietowania.
Nie zakładaj istnienia repozytorium Git; nie twórz automatycznie commitów.

Nie deklaruj testów, pobrań ani integracji, których nie wykonano. Oddzielaj
wynik testów z mockami od rzeczywistego kontaktu z serwerem, a plan od implementacji.

## Licencja własnego kodu

Autor wybrał MIT dla kodu projektu; obowiązuje główny LICENSE.
Nie rozszerzaj tej licencji na dane Binance ani inne materiały osób trzecich.
