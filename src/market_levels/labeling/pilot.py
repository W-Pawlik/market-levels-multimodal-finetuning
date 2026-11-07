"""Etykietowanie istniejącego pilotażu, oddzielne PNG i atomowa publikacja."""
from __future__ import annotations

from collections import Counter
from io import BytesIO
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import platform

from ..charts.renderer import build_figure, require_short_path
from ..data_processing.staging import publication_workspace, publish_directory
from ..data_processing.storage import read_candles_csv, write_json
from ..data_processing.synthetic.quality import canonical_hash
from .algorithm import LabelResult, VERSION, label_window


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def child(root: Path, name: str) -> Path:
    path = (root/name).resolve()
    if root.resolve() not in path.parents:
        raise ValueError("Ścieżka wychodzi poza katalog pilotażu")
    return path


def read_pilot(pilot: Path) -> tuple[list, dict]:
    """Zweryfikuj każdy CSV/PNG/JSON i manifest przed obliczeniami."""
    manifest_path = pilot/"manifest.json"
    ledger = {str(manifest_path.resolve()): sha256(manifest_path)}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest["images"]
    if manifest["actual_count"] != 32 or len(records) != 32:
        raise ValueError("Etap 3.4 wymaga wszystkich 32 przykładów istniejącego pilotażu")
    if len({r["id"] for r in records}) != 32 or len({r["png"] for r in records}) != 32:
        raise ValueError("Powtórzone identyfikatory/pliki pilotażu")
    loaded = []
    for record in records:
        png, csv = child(pilot, record["png"]), child(pilot, record["window_csv"])
        sidecar = png.with_suffix(".json")
        if json.loads(sidecar.read_text(encoding="utf-8")) != record:
            raise ValueError(f"Niezgodny JSON: {sidecar}")
        for path, key in ((png, "png_sha256"), (csv, "window_csv_sha256")):
            if sha256(path) != record[key]:
                raise ValueError(f"Niezgodny SHA-256: {path}")
        for path in (png, csv, sidecar):
            ledger[str(path.resolve())] = sha256(path)
        candles = read_candles_csv(csv, source="labeling-pilot")
        if canonical_hash(candles) != record["ohlc_sha256"]:
            raise ValueError(f"Niezgodny OHLC: {csv}")
        loaded.append((record, candles))
    return loaded, ledger


def render_levels(candles, result: LabelResult, path: Path) -> None:
    """Bazowe osie pozostają identyczne; etykiety mają rozdzielone pozycje."""
    require_short_path(path)
    fig = build_figure(candles)
    try:
        ax = fig.axes[0]
        low, high = ax.get_ylim()
        entries = []
        for groups, color, style, label in ((result.supports, "#2357c6", "--", "Wsparcie"),
                                           (result.resistances, "#a52a82", ":", "Opór")):
            for i, group in enumerate(groups):
                value = float(group.level)
                ax.axhline(value, color=color, linestyle=style, linewidth=1.4,
                           label=label if i == 0 else None)
                price = group.level.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                entries.append((value, color, f"{label}: {price:.2f}"))
        # Pozycje napisów w ułamku osi, odstęp co najmniej 0.045 wysokości.
        entries.sort()
        positions = []
        for value, _, _ in entries:
            positions.append(max((value-low)/(high-low), positions[-1]+0.045 if positions else 0.025))
        if positions:
            positions[-1] = min(positions[-1], 0.96)
            for i in range(len(positions)-2, -1, -1):
                positions[i] = min(positions[i], positions[i+1]-0.045)
        for (value, color, label), position in zip(entries, positions):
            ax.annotate(label, xy=(119, value), xycoords="data", xytext=(0.985, position),
                        textcoords="axes fraction", ha="right", va="center", fontsize=9,
                        color=color, bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": color, "pad": 2},
                        arrowprops={"arrowstyle": "-", "color": color, "linewidth": 0.6})
        if entries:
            ax.legend(loc="upper left", fontsize=9)
        ax.set_ylim(low, high)
        buffer = BytesIO()
        fig.canvas.print_png(buffer, metadata={"Software": f"market-levels-labeling/{VERSION}",
                                              "Purpose": "diagnostic_only_not_vlm_input"})
        with path.open("xb") as stream:
            stream.write(buffer.getvalue())
    finally:
        fig.clear()


def summarize(results: list[tuple[dict, LabelResult]]) -> dict:
    return {"count": len(results),
            "support_counts": dict(sorted(Counter(len(r.supports) for _, r in results).items())),
            "resistance_counts": dict(sorted(Counter(len(r.resistances) for _, r in results).items())),
            "without_supports": sum(not r.supports for _, r in results),
            "without_resistances": sum(not r.resistances for _, r in results),
            "without_either": sum(not r.supports and not r.resistances for _, r in results),
            "extrema_before": sum(len(r.extrema) for _, r in results),
            "reactions_after": sum(len(g.reactions) for _, r in results for g in r.groups),
            "rounding_collisions": sum(len(r.collisions) for _, r in results),
            "rejection_reasons": dict(Counter(g.reason for _, r in results for g in r.groups if g.reason))}


def report_markdown(results, summary):
    lines = ["# Etykietowanie pilotażu 3.4", "", "Status: diagnostyczny, oczekuje ręcznej oceny autora. Obrazy z liniami nie są wejściami VLM.",
             "", "Algorytm: ścisłe ekstrema 3+3, końcowy Wilder ATR(14), delta=ATR/2, wspólne grupy H/L o pełnej rozpiętości ≤ delta. Mediana wszystkich ekstremów przed filtrowaniem.",
             "Najpierw zachowujemy najsilniejsze ekstremum (H: cena−mediana, L: mediana−cena), usuwając reakcje bliższe niż 5 świec. Remis wygrywa późniejsza świeca, następnie H przed L. To może dać mniej reakcji niż maksymalizacja ich liczby.",
             "Ranking: liczba reakcji, ostatnia reakcja, odległość od Close, cena i ID. Kolizje po ROUND_HALF_UP rozstrzyga ranking przed limitem trzech; pominięcie jest jawne w diagnostyce.",
             "Obliczenia Decimal: stały kontekst 50 cyfr znaczących, bez zaokrąglania do centów przed serializacją odpowiedzi. ATR jest rekurencją skończonej precyzji (nie dokładną liczbą wymierną). Indeksy diagnostyki od zera.",
             "", "## Wyniki", "", "```json", json.dumps(summary, ensure_ascii=False, indent=2), "```", "",
             "Liczba reakcji po filtrowaniu obejmuje wszystkie grupy, także później odrzucone jako poziomy.", "",
             "| Plik | Symbol / źródło | Wsparcia | Opory | Ekstrema → reakcje |", "|---|---|---|---|---|"]
    for i, (record, result) in enumerate(results):
        target = json.loads(result.target_json())
        lines.append(f"| {i:03d} | {record['symbol']} / {record['source']} | {target['supports']} | {target['resistances']} | {len(result.extrema)} → {sum(len(g.reactions) for g in result.groups)} |")
    lines += ["", "## Przykłady do ręcznej kontroli", ""]
    picks = [min(range(len(results)), key=lambda i: len(results[i][1].supports)+len(results[i][1].resistances)),
             max(range(len(results)), key=lambda i: len(results[i][1].supports)+len(results[i][1].resistances)),
             max(range(len(results)), key=lambda i: len(results[i][1].extrema)-sum(len(g.reactions) for g in results[i][1].groups)),
             max(range(len(results)), key=lambda i: sum({e.kind for e in g.extrema} == {"H", "L"} for g in results[i][1].groups))]
    for i, reason in zip(picks, ("najmniej poziomów", "najwięcej poziomów", "najwięcej odrzuconych bliskich reakcji", "najwięcej grup mieszanych H/L")):
        lines.append(f"- `overlays/{i:03d}.png`, `diagnostics/{i:03d}.json`: {reason}; ID `{results[i][0]['id']}`.")
    lines += ["", "Nie przeprowadzono niezależnej eksperckiej oceny poziomów. Pilotaż celowo pokrywa różne sytuacje i nie jest reprezentatywną próbą rynku. Brak poziomów stanowi wynik reguł; nie dopasowywano parametrów do obrazu. Nie zmieniano generatora, statusów profili ani oryginałów; nie generowano OHLC, nie pobierano danych i nie wykonywano etapu 3.5.", ""]
    return "\n".join(lines)


def run_labeling(*, pilot: Path, output: Path) -> Path:
    pilot, output = Path(pilot).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"Odmowa nadpisania: {output}")
    allowed = Path("results/diagnostics").resolve()
    if allowed not in output.parents or pilot == output or pilot in output.parents:
        raise ValueError("Wynik musi być nowym katalogiem pod results/diagnostics poza źródłowym pilotażem")
    for name in ("diagnostics/031.json", "SOURCE_INTEGRITY.json", "overlays/031.png"):
        require_short_path(output/name)
        require_short_path(output.parent/(".labels-"+"x"*8)/"batch"/name)
    loaded, ledger = read_pilot(pilot)
    results = [(record, label_window(candles)) for record, candles in loaded]
    output.parent.mkdir(parents=True, exist_ok=True)
    with publication_workspace(output.parent, prefix=".labels-") as temporary:
        stage = temporary/"batch"
        for name in ("labels", "diagnostics", "overlays"):
            (stage/name).mkdir(parents=True)
        images = []
        for i, ((record, candles), (_, result)) in enumerate(zip(loaded, results)):
            names = {"label": f"labels/{i:03d}.json", "diagnostic": f"diagnostics/{i:03d}.json",
                     "overlay": f"overlays/{i:03d}.png"}
            (stage/names["label"]).write_text(result.target_json(), encoding="utf-8")
            write_json(stage/names["diagnostic"], dict(result.diagnostics(), source_metadata=record,
                                                     overlay_is_vlm_input=False))
            render_levels(candles, result, stage/names["overlay"])
            images.append(dict(id=record["id"], source_png=record["png"], source_csv=record["window_csv"],
                               source_png_sha256=record["png_sha256"], source_csv_sha256=record["window_csv_sha256"],
                               ohlc_sha256=record["ohlc_sha256"], **names))
        summary = summarize(results)
        write_json(stage/"summary.json", summary)
        (stage/"RAPORT.md").write_text(report_markdown(results, summary), encoding="utf-8")
        if any(sha256(Path(p)) != digest for p, digest in ledger.items()):
            raise ValueError("Zmiana źródła w trakcie etykietowania")
        write_json(stage/"SOURCE_INTEGRITY.json", {"unchanged": True, "files": ledger})
        files = {p.relative_to(stage).as_posix(): sha256(p) for p in sorted(stage.rglob("*")) if p.is_file()}
        import matplotlib
        write_json(stage/"manifest.json", {"schema_version": 1, "algorithm_version": VERSION,
                                          "status": "diagnostic_unapproved", "overlay_is_vlm_input": False,
                                          "pilot": str(pilot), "count": 32, "images": images, "files": files,
                                          "runtime": {"python": platform.python_version(), "matplotlib": matplotlib.__version__}})
        publish_directory(stage, output)
    return output


def verify_labeling(output: Path, pilot: Path, *, re_render: bool = False) -> None:
    """Kontrola hashy, pochodzenia i ponownego obliczenia całej diagnostyki."""
    import tempfile
    manifest = json.loads((output/"manifest.json").read_text(encoding="utf-8"))
    if manifest["algorithm_version"] != VERSION or manifest["overlay_is_vlm_input"] is not False:
        raise ValueError("Niezgodna wersja lub przeznaczenie wyników")
    expected_files = {"summary.json", "RAPORT.md", "SOURCE_INTEGRITY.json"}
    expected_files.update(f"{folder}/{i:03d}.{suffix}" for i in range(32)
                          for folder, suffix in (("labels", "json"), ("diagnostics", "json"), ("overlays", "png")))
    actual_files = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
    if set(manifest["files"]) != expected_files or actual_files != expected_files | {"manifest.json"}:
        raise ValueError("Niekompletna lista plików lub hashy")
    for name, digest in manifest["files"].items():
        if sha256(child(output, name)) != digest:
            raise ValueError(f"Niezgodny hash wyniku: {name}")
    loaded, ledger = read_pilot(pilot)
    if manifest["count"] != 32 or len(manifest["images"]) != 32:
        raise ValueError("Niekompletny wynik")
    integrity = json.loads((output/"SOURCE_INTEGRITY.json").read_text(encoding="utf-8"))
    # W przeniesionym handoff ścieżki absolutne mogą się zmienić; porównujemy zawartość.
    if sorted(ledger.values()) != sorted(integrity["files"].values()) or not integrity["unchanged"]:
        raise ValueError("Źródłowy pilotaż zmienił się")
    results = []
    with tempfile.TemporaryDirectory(prefix="sr-verify-") as temporary:
        for i, ((record, candles), image) in enumerate(zip(loaded, manifest["images"])):
            if (image["label"], image["diagnostic"], image["overlay"]) != (f"labels/{i:03d}.json", f"diagnostics/{i:03d}.json", f"overlays/{i:03d}.png"):
                raise ValueError("Powtórzone lub niezgodne pliki w manifeście")
            result = label_window(candles)
            results.append((record, result))
            if (image["id"], image["source_png_sha256"], image["source_csv_sha256"], image["ohlc_sha256"]) != (record["id"], record["png_sha256"], record["window_csv_sha256"], record["ohlc_sha256"]):
                raise ValueError("Niezgodne pochodzenie")
            if child(output, image["label"]).read_text(encoding="utf-8") != result.target_json():
                raise ValueError("Niezgodna etykieta")
            expected = dict(result.diagnostics(), source_metadata=record, overlay_is_vlm_input=False)
            if json.loads(child(output, image["diagnostic"]).read_text(encoding="utf-8")) != expected:
                raise ValueError("Niezgodna diagnostyka")
            if re_render:
                path = Path(temporary)/f"{i:03d}.png"
                render_levels(candles, result, path)
                if sha256(path) != sha256(child(output, image["overlay"])):
                    raise ValueError("Niezgodny odtworzony PNG; sprawdź wersje renderera i fonty")
    if json.loads((output/"summary.json").read_text(encoding="utf-8")) != json.loads(json.dumps(summarize(results))):
        raise ValueError("Niezgodne podsumowanie")
