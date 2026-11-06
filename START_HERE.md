# Audyt OHLC i pierwszy pilotaż PNG

Zrealizowany etap: ilościowy audyt **600 istniejących V2-full-refined** i
**32 obrazy PNG 1024 × 768**: po 8 BTC/ETH × real/synthetic.
Rzeczywiste okna pochodzą wyłącznie z train 2020–2023. Wszystkie profile i pilotaż
pozostają niezatwierdzone. Nie zmieniono matematyki generatora ani parametrów.

W paczce handoff zacznij od `AUDYT_ROZNORODNOSCI.md`, następnie obejrzyj `pilot/`.
Każdy PNG ma boczny JSON i dokładne 120 świec CSV. Pełny audyt jest w JSON;
manifest pilotażu podaje identyfikatory, hashe, profile, seedy i zasady selekcji.

- [Raport renderera](docs/charts/RAPORT_RENDERERA.md).
- [Testy i ograniczenia weryfikacji](docs/charts/RAPORT_TESTOW.md).
- [Instrukcja PowerShell i sprawdzenie paczki](docs/charts/INSTRUKCJA_POWERSHELL.md).

W repozytorium wyniki są lokalne w `results/diagnostics/`, poza Git i finalnymi
zbiorami. Handoff zawiera raporty i mały pilotaż; nie zawiera pełnych danych,
historycznych eksperymentów, środowiska ani cache. Oryginalne ścieżki i SHA
zachowano w `run.json` i `SOURCE_INTEGRITY.json` dołączonych do paczki.
Nie są potrzebne do obejrzenia pilotażu ani jego ponownego renderowania.

MIT obejmuje kod. Nie rozszerza licencji na dane i PNG z notowań Binance;
zachowano [notatkę o danych](docs/LICENCJA_DANYCH.md). Paczka jest lokalnym
przekazaniem na zlecenie autora; nie wykonano publikacji ani treningu.
