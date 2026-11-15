"""Перевірка розрахунку зміщення на синтетичному файлі зі структурою, схожою на GUNW."""
import math

import pytest

np = pytest.importorskip("numpy")
h5py = pytest.importorskip("h5py")
pytest.importorskip("pyproj")

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nisar"))
import fetch_nisar as fn  # noqa: E402
from kora_nisar_client import L_BAND_WAVELENGTH_M  # noqa: E402

LON, LAT, EPSG = 24.014, 49.8352, 32635


def make_file(path, bump_mm=-12.5, coherence=0.9, comp_zero_at_point=False):
    from pyproj import Transformer

    x0, y0 = Transformer.from_crs(4326, EPSG, always_xy=True).transform(LON, LAT)
    step, n = 80.0, 200
    xs = x0 - 8000 + step * np.arange(n)
    ys = y0 + 8000 - step * np.arange(n)  # y спадає, як у реальних сітках
    phase = np.full((n, n), 1.0)  # фон: константа (опорний зсув)
    iy, ix = int(np.abs(ys - y0).argmin()), int(np.abs(xs - x0).argmin())
    # зміщення -bump_mm у фазі: phi = -4*pi*d/lambda
    phase[iy - 1 : iy + 2, ix - 1 : ix + 2] += -4 * math.pi * (bump_mm / 1000) / L_BAND_WAVELENGTH_M
    comp = np.ones((n, n), dtype="uint8")
    if comp_zero_at_point:
        comp[iy, ix] = 0
    with h5py.File(path, "w") as f:
        g = f.create_group("science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/HH")
        g.create_dataset("unwrappedPhase", data=phase)
        g.create_dataset("coherenceMagnitude", data=np.full((n, n), coherence))
        g.create_dataset("connectedComponents", data=comp)
        parent = f["science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram"]
        parent.create_dataset("xCoordinates", data=xs)
        parent.create_dataset("yCoordinates", data=ys)
        p = parent.create_dataset("projection", data=np.uint32(EPSG))
        p.attrs["epsg_code"] = EPSG


def test_extract_recovers_known_displacement(tmp_path):
    f = tmp_path / "g.h5"
    make_file(f, bump_mm=-12.5)
    with h5py.File(f, "r") as h5:
        r = fn.extract_displacement(h5, LON, LAT)
    assert r["displacement_mm"] == pytest.approx(-12.5, abs=0.1)
    assert r["epsg"] == EPSG and r["pixel_m"] == 80.0 and r["n_ref"] > 50


def test_low_coherence_rejected(tmp_path):
    f = tmp_path / "g.h5"
    make_file(f, coherence=0.1)
    with h5py.File(f, "r") as h5, pytest.raises(ValueError, match="когерентність"):
        fn.extract_displacement(h5, LON, LAT)


def test_point_outside_grid_and_component_zero(tmp_path):
    f = tmp_path / "g.h5"
    make_file(f)
    with h5py.File(f, "r") as h5, pytest.raises(ValueError, match="поза межами"):
        fn.extract_displacement(h5, LON + 1.0, LAT)
    make_file(f, comp_zero_at_point=True)
    with h5py.File(f, "r") as h5, pytest.raises(ValueError, match="connected component"):
        fn.extract_displacement(h5, LON, LAT)


def test_pair_dates_from_real_filename():
    fid = "NISAR_L2_PR_GUNW_032_123_D_063_033_2000_SH_20261008T174318_20261008T174354_20261020T174318_20261020T174354_P05023_N_F_J_001"
    ref, sec = fn.pair_dates(fid)
    assert str(ref) == "2026-10-08" and str(sec) == "2026-10-20"


def test_series_continues_from_its_first_date_without_gaps():
    """Регресія: накопичена сума не має залежати від того, скільки пар узяли в цей запуск."""
    from datetime import date, timedelta

    pairs = [{"sec": date(2026, 8, 15) + timedelta(days=12 * i)} for i in range(8)]  # 8 пар підряд

    # перший запуск (ряду ще нема): лише останні K
    first = fn.select_chain(pairs, None, 3)
    assert [p["sec"] for p in first] == [p["sec"] for p in pairs[-3:]]

    # наступні запуски: ряд триває з тієї ж першої дати, навіть якщо нових пар більше за K
    start = str(first[0]["sec"])
    later = fn.select_chain(pairs, start, 3)
    assert later[0]["sec"] == first[0]["sec"] and later[-1]["sec"] == pairs[-1]["sec"]
    assert len(later) == 3  # у цьому прикладі нових пар ще нема

    more = pairs + [{"sec": pairs[-1]["sec"] + timedelta(days=12 * i)} for i in (1, 2, 3, 4)]
    cont = fn.select_chain(more, start, 3)  # 4 нових пар > K=3: усе одно без пропусків
    assert cont[0]["sec"] == first[0]["sec"] and len(cont) == 3 + 4


def test_duplicate_post_is_not_an_error(monkeypatch):
    import io
    import urllib.error

    import kora_nisar_client as client

    def boom(*a, **k):
        raise urllib.error.HTTPError("u", 409, "Conflict", {}, io.BytesIO(b"{}"))

    monkeypatch.setenv("API_KEY_SATELLITE", "k")
    monkeypatch.setattr(client.urllib.request, "urlopen", boom)
    res = client.post_observation({"x": 1})
    assert res["duplicate"] is True and fn.sent_label(res) == "вже є в базі"


def test_csv_and_simulate_distinguish_duplicates(monkeypatch, tmp_path, capsys):
    """Регресія: раніше дублікат (409) друкувався як NORMAL і не відрізнявся від нового спостереження."""
    from argparse import Namespace

    import kora_nisar_client as client

    answers = iter([
        {"status": "stored", "severity": "WARNING", "alert_created": True},
        {"status": "duplicate", "duplicate": True, "severity": "NORMAL", "alert_created": False},
    ])
    monkeypatch.setattr(client, "post_observation", lambda obs: next(answers))

    f = tmp_path / "r.csv"
    f.write_text("object_id,displacement,unit,observation_date,longitude,latitude,source\n"
                 "1,-12,mm,2026-10-20,24.0,49.8,T\n1,-12,mm,2026-10-20,24.0,49.8,T\n", encoding="utf-8")
    client.cmd_csv(Namespace(file=str(f)))
    lines = capsys.readouterr().out.strip().splitlines()
    assert "WARNING" in lines[0] and "alert" in lines[0]
    assert "вже є в базі" in lines[1] and "NORMAL" not in lines[1]

    answers = iter([{"status": "duplicate", "duplicate": True, "severity": "NORMAL", "alert_created": False}])
    client.cmd_simulate(Namespace(object_id=1, lon=24.0, lat=49.8, count=1, rate=1.5))
    assert "вже є в базі" in capsys.readouterr().out
