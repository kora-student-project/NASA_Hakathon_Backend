#!/usr/bin/env python3
"""KORA: автоматично бере реальні дані NASA NISAR (GUNW) і шле зміщення в бекенд.

Що робить `run`:
  1. Бере список об'єктів з бекенду (GET /api/objects).
  2. Для кожного об'єкта шукає в архіві ASF DAAC продукти NISAR L2 GUNW (розгорнуті
     інтерферограми, 12-добові пари), що накривають координати будівлі.
  3. З кожного файлу читає ЛИШЕ невелику ділянку навколо будівлі (файл ~2,4 ГБ,
     повністю його не завантажуємо; HTTP range-запити).
  4. Рахує зміщення вздовж лінії погляду (мм) відносно оточення, накопичує по парах.
  5. Шле результат у POST /api/satellite/data (source = "NASA NISAR GUNW ...").

Потрібно: безкоштовний акаунт NASA Earthdata і токен (urs.earthdata.nasa.gov → Generate Token).
Змінні середовища (або у файлі .env у корені репозиторію): API_URL, API_KEY_SATELLITE, EARTHDATA_TOKEN.

Приклади:
  python nisar/fetch_nisar.py run --dry-run               # лише пошук, без завантаження
  python nisar/fetch_nisar.py run --max-granules 4        # 4 останні пари
  python nisar/fetch_nisar.py inspect файл.h5             # показати структуру HDF5

ВАЖЛИВО: дані NISAR L2 GUNW (PROVISIONAL), зміщення відносне (до оточення, у напрямку
на супутник), точність залежить від когерентності й атмосфери. Це індикатор, а не висновок.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from kora_nisar_client import api_url, make_observation, phase_to_los_mm, post_observation, sent_label

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "state.json"


# ---------------------------------------------------------------- налаштування

def load_dotenv(path: str | None = None) -> None:
    """Підтягує змінні з env-файлу (за замовч. .env у корені репозиторію), не перезаписуючи вже задані."""
    env = Path(path).expanduser() if path else HERE.parent / ".env"
    if not env.exists():
        sys.exit(f"Файл {env} не знайдено")
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ---------------------------------------------------------------- бекенд API

def api_get(path: str):
    url = api_url() + path
    with urllib.request.urlopen(url, timeout=90) as r:
        return json.load(r)


# ---------------------------------------------------------------- стан (що вже оброблено)

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- пошук в ASF

TS_RE = re.compile(r"(\d{8})T\d{6}")


def pair_dates(file_id: str) -> tuple[date, date]:
    """З назви GUNW: ..._<ref start>_<ref end>_<sec start>_<sec end>_... → (дата ref, дата secondary)."""
    ts = TS_RE.findall(file_id)
    if len(ts) < 3:
        raise ValueError(f"Не вдалося розібрати дати з назви {file_id}")
    d = lambda s: datetime.strptime(s, "%Y%m%d").date()
    return d(ts[0]), d(ts[2])


def search_gunw(lon: float, lat: float, since: str | None):
    import asf_search as asf

    kw = dict(
        dataset=asf.DATASET.NISAR,
        processingLevel="GUNW",
        intersectsWith=f"POINT({lon} {lat})",
        maxResults=500,
    )
    if since:
        kw["start"] = since
    res = [r for r in asf.search(**kw) if r.properties.get("platform") == "NISAR"]
    out = []
    for r in res:
        p = r.properties
        fid = p["fileID"]
        ref, sec = pair_dates(fid)
        h5_url = p["url"]
        size = next((v["bytes"] for k, v in (p.get("bytes") or {}).items() if k.endswith(".h5") and "QA" not in k), None)
        out.append(
            dict(
                file_id=fid,
                ref=ref,
                sec=sec,
                url=h5_url,
                group=f"{p.get('pathNumber')}{str(p.get('flightDirection', '?'))[0]}",
                size=size,
                product=r,
            )
        )
    out.sort(key=lambda g: g["sec"])
    return out


# ---------------------------------------------------------------- читання HDF5

def index_datasets(h5) -> dict:
    import h5py

    idx: dict[str, list[str]] = defaultdict(list)

    def visit(name, obj):
        if isinstance(obj, h5py.Dataset):
            idx[name.rsplit("/", 1)[-1]].append(name)

    h5.visititems(visit)
    return idx


def pick(idx: dict, name: str, near: str | None = None, prefer: str | None = None) -> str | None:
    cands = idx.get(name, [])
    if not cands:
        return None
    if prefer:
        pref = [c for c in cands if f"/{prefer}/" in c]
        cands = pref or cands
    if near:
        parent = near.rsplit("/", 1)[0]
        grand = parent.rsplit("/", 1)[0]
        for level in (parent, grand):
            for c in cands:
                if c.rsplit("/", 1)[0] == level:
                    return c
    return cands[0]


def read_epsg(h5, idx: dict, near: str) -> int:
    path = pick(idx, "projection", near)
    if path is None:
        raise RuntimeError("У файлі не знайдено dataset 'projection'. Запустіть: inspect <файл>")
    ds = h5[path]
    for key in ("epsg_code", "epsg", "EPSG"):
        if key in ds.attrs:
            return int(ds.attrs[key])
    return int(ds[()])


def extract_displacement(
    h5,
    lon: float,
    lat: float,
    ref_radius_m: float = 2000.0,
    exclude_radius_m: float = 300.0,
    point_halfwin: int = 1,
    min_coherence: float = 0.3,
    min_ref_pixels: int = 50,
) -> dict:
    """Зміщення в точці відносно медіани оточення. Повертає dict або кидає ValueError з причиною."""
    import numpy as np
    from pyproj import Transformer

    idx = index_datasets(h5)
    ph_path = pick(idx, "unwrappedPhase", prefer="HH") or pick(idx, "unwrappedPhase")
    if ph_path is None:
        raise RuntimeError("У файлі не знайдено 'unwrappedPhase'. Запустіть: inspect <файл>")
    xs_path = pick(idx, "xCoordinates", ph_path)
    ys_path = pick(idx, "yCoordinates", ph_path)
    if xs_path is None or ys_path is None:
        raise RuntimeError("Не знайдено xCoordinates/yCoordinates. Запустіть: inspect <файл>")

    epsg = read_epsg(h5, idx, ph_path)
    x_pt, y_pt = Transformer.from_crs(4326, epsg, always_xy=True).transform(lon, lat)
    xs, ys = h5[xs_path][()], h5[ys_path][()]
    if not (xs.min() <= x_pt <= xs.max() and ys.min() <= y_pt <= ys.max()):
        raise ValueError("Точка поза межами сітки продукту")
    ix, iy = int(np.abs(xs - x_pt).argmin()), int(np.abs(ys - y_pt).argmin())
    step = float(abs(xs[1] - xs[0]))  # метри на піксель
    half = max(int(ref_radius_m / step), point_halfwin + 2)

    phase_ds = h5[ph_path]
    y0, y1 = max(iy - half, 0), min(iy + half + 1, phase_ds.shape[0])
    x0, x1 = max(ix - half, 0), min(ix + half + 1, phase_ds.shape[1])
    ph = phase_ds[y0:y1, x0:x1].astype("float64")
    cy, cx = iy - y0, ix - x0

    comp = coh = None
    cc_path = pick(idx, "connectedComponents", ph_path)
    if cc_path and h5[cc_path].shape == phase_ds.shape:
        comp = h5[cc_path][y0:y1, x0:x1]
    co_path = pick(idx, "coherenceMagnitude", ph_path)
    if co_path and h5[co_path].shape == phase_ds.shape:
        coh = h5[co_path][y0:y1, x0:x1].astype("float64")

    valid = np.isfinite(ph)
    valid &= (comp > 0) if comp is not None else (ph != 0)
    yy, xx = np.mgrid[0 : ph.shape[0], 0 : ph.shape[1]]
    dist = np.hypot(yy - cy, xx - cx) * step

    win = (np.abs(yy - cy) <= point_halfwin) & (np.abs(xx - cx) <= point_halfwin) & valid
    if comp is not None:
        label = comp[cy, cx]
        if label <= 0:
            raise ValueError("Піксель будівлі поза областю розгортання фази (connected component = 0)")
        win &= comp == label
        valid &= comp == label  # фаза порівнюється лише в межах одного компонента
    if win.sum() < 3:
        raise ValueError("Замало валідних пікселів навколо будівлі")
    point_coh = float(np.nanmedian(coh[win])) if coh is not None else None
    if point_coh is not None and point_coh < min_coherence:
        raise ValueError(f"Низька когерентність {point_coh:.2f} < {min_coherence}")

    ring = valid & (dist >= exclude_radius_m) & (dist <= ref_radius_m)
    if ring.sum() < min_ref_pixels:
        raise ValueError(f"Замало опорних пікселів ({int(ring.sum())})")

    point_phase = float(np.median(ph[win]))
    ref_phase = float(np.median(ph[ring]))
    return dict(
        displacement_mm=phase_to_los_mm(point_phase - ref_phase),
        point_phase=point_phase,
        ref_phase=ref_phase,
        n_ref=int(ring.sum()),
        coherence=point_coh,
        pixel_m=step,
        epsg=epsg,
    )


def open_remote(url: str, token: str):
    """Відкриває віддалений HDF5 без повного завантаження (HTTP range-запити)."""
    import fsspec
    import h5py

    fs = fsspec.filesystem("https", headers={"Authorization": f"Bearer {token}"}, block_size=4 * 1024 * 1024)
    return h5py.File(fs.open(url, "rb", cache_type="readahead"), "r")


def open_downloaded(granule: dict, token: str, cache_dir: Path):
    """Запасний режим: повне завантаження файлу (~2,4 ГБ) через asf_search."""
    import asf_search as asf
    import h5py

    cache_dir.mkdir(parents=True, exist_ok=True)
    session = asf.ASFSession().auth_with_token(token)
    granule["product"].download(path=str(cache_dir), session=session, fileType=asf.FileDownloadType.DEFAULT_FILES)
    path = cache_dir / (granule["file_id"] + ".h5")
    return h5py.File(path, "r"), path


# ---------------------------------------------------------------- команди

def cmd_inspect(args) -> None:
    import h5py

    with h5py.File(args.file, "r") as h5:
        def show(name, obj):
            if isinstance(obj, h5py.Dataset):
                print(f"{name}  shape={obj.shape} dtype={obj.dtype}")
        h5.visititems(show)


def select_chain(granules: list[dict], series_start: str | None, max_granules: int) -> list[dict]:
    """Які пари обробляти. Ряд, що вже почали, продовжуємо з його першої дати БЕЗ пропусків: накопичена сума
    має завжди починатися з однієї й тієї ж пари, інакше нові значення «стрибнуть» відносно вже надісланих.
    Перший запуск бере останні `max_granules` пар."""
    if series_start is None:
        return granules[-max_granules:]
    return [g for g in granules if str(g["sec"]) >= series_start]


def build_obs(obj: dict, sec: date, cumulative: float, gname: str) -> dict:
    return make_observation(obj["id"], round(cumulative, 2), sec.isoformat(), obj["longitude"], obj["latitude"],
                            source=f"NASA NISAR GUNW track {gname}")


def cmd_run(args) -> None:
    load_dotenv(args.env_file)
    if args.env_file:  # окремий файл = окремий стан, щоб не мішати з іншими серверами
        global STATE_FILE
        STATE_FILE = HERE / f"state.{Path(args.env_file).name.lstrip('.')}.json"
    token = os.environ.get("EARTHDATA_TOKEN")
    if not token and not args.dry_run:
        sys.exit("Задайте EARTHDATA_TOKEN (urs.earthdata.nasa.gov → Generate Token) або запустіть з --dry-run")

    objects = api_get("/api/objects?limit=500")
    if args.object_id:
        objects = [o for o in objects if o["id"] == args.object_id]
    if not objects:
        sys.exit("Об'єктів не знайдено")

    state = load_state()
    posted = 0
    for obj in objects:
        print(f"\n== Об'єкт {obj['id']}: {obj['name']} ({obj['latitude']}, {obj['longitude']})")
        prefix = f"{obj['id']}:"
        known = {k: v for k, v in state.items() if k.startswith(prefix) and "pair_mm" in v}
        stored_group = Counter(v["group"] for v in known.values()).most_common(1)[0][0] if known else None
        # --since діє лише на першому запуску: далі ряд продовжується з уже збереженої першої дати
        found = search_gunw(obj["longitude"], obj["latitude"], None if known else args.since)
        if not found:
            print("  GUNW над цим об'єктом не знайдено")
            continue
        groups: dict[str, list] = defaultdict(list)
        for g in found:
            groups[g["group"]].append(g)
        summary = ", ".join(f"{k}: {len(v)}" for k, v in sorted(groups.items()))
        print(f"  Знайдено GUNW: {len(found)} (траєкторії {summary})")
        gname = args.group or stored_group or max(groups, key=lambda k: len(groups[k]))
        series_start = min((v["sec"] for v in known.values() if v["group"] == gname), default=None)
        chain = select_chain(groups[gname], series_start, args.max_granules)
        print(f"  Траєкторія {gname}: {len(chain)} пар" + (f", ряд триває з {series_start}" if series_start else ", новий ряд"))

        cumulative = 0.0
        prev_sec = None
        for g in chain:
            key = f"{obj['id']}:{g['file_id']}"
            size = f"{g['size'] / 1e9:.1f} ГБ" if g["size"] else "?"
            print(f"  - {g['ref']} → {g['sec']}  ({size})", end="  ")
            if prev_sec is not None and g["ref"] != prev_sec:
                print("\n    ! пропуск між парами: накопичене зміщення ненадійне", end="  ")
            prev_sec = g["sec"]
            if key in state:
                st = state[key]
                if "pair_mm" not in st:
                    print(f"вже оброблено, пропущено ({st.get('skipped')}); накопичене нижче неточне")
                    continue
                cumulative += st["pair_mm"]
                print(f"вже обчислено, пара {st['pair_mm']:+.1f} мм, накопичено {cumulative:+.1f} мм", end="")
                if not st.get("posted") and not args.no_post and not args.dry_run:
                    res = post_observation(build_obs(obj, g["sec"], cumulative, gname))
                    st["posted"] = True
                    posted += 1
                    save_state(state)
                    print(f"  → відправлено: {sent_label(res)}", end="")
                print()
                continue
            if args.dry_run:
                print("(dry-run)")
                continue
            try:
                if args.download:
                    h5, path = open_downloaded(g, token, HERE / "cache")
                else:
                    h5, path = open_remote(g["url"], token), None
                with h5:
                    r = extract_displacement(
                        h5, obj["longitude"], obj["latitude"],
                        ref_radius_m=args.ref_radius, min_coherence=args.min_coherence,
                    )
                if path and not args.keep_files:
                    path.unlink(missing_ok=True)
            except ValueError as e:  # якість: не рахуємо, запам'ятовуємо
                print(f"пропущено: {e}")
                state[key] = {"skipped": str(e)}
                save_state(state)
                continue
            cumulative += r["displacement_mm"]
            print(f"пара {r['displacement_mm']:+.1f} мм, накопичено {cumulative:+.1f} мм (coh {r['coherence']})")
            state[key] = {
                "pair_mm": r["displacement_mm"], "ref": str(g["ref"]), "sec": str(g["sec"]), "group": gname,
                "coherence": r["coherence"], "posted": False,
            }
            obs = build_obs(obj, g["sec"], cumulative, gname)
            if args.no_post:
                print("    (без відправки: --no-post)")
            else:
                res = post_observation(obs)
                state[key]["posted"] = True
                posted += 1
                print(f"    → бекенд: {sent_label(res)}" + (" (створено попередження)" if res.get("alert_created") else ""))
            save_state(state)
    print(f"\nГотово. Відправлено спостережень: {posted}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="знайти, обчислити й відправити")
    r.add_argument("--object-id", type=int, help="лише цей об'єкт (за замовч. усі)")
    r.add_argument("--since", help="лише спостереження з цієї дати, YYYY-MM-DD")
    r.add_argument("--max-granules", type=int, default=6, help="скільки останніх пар обробляти (за замовч. 6)")
    r.add_argument("--group", help="траєкторія, напр. 28A (за замовч. та, де найбільше пар)")
    r.add_argument("--env-file", help="окремий env-файл (напр. ~/kora-render.env з API_URL, API_KEY_SATELLITE, EARTHDATA_TOKEN)")
    r.add_argument("--dry-run", action="store_true", help="лише пошук, без читання даних і відправки")
    r.add_argument("--no-post", action="store_true", help="обчислити, але не відправляти в бекенд")
    r.add_argument("--download", action="store_true", help="повністю завантажувати файли (~2,4 ГБ) замість range-запитів")
    r.add_argument("--keep-files", action="store_true", help="не видаляти завантажені файли")
    r.add_argument("--ref-radius", type=float, default=2000.0, help="радіус опорної області, м (2000)")
    r.add_argument("--min-coherence", type=float, default=0.3, help="мінімальна когерентність у точці (0.3)")
    r.set_defaults(func=cmd_run)

    i = sub.add_parser("inspect", help="показати структуру HDF5-файлу")
    i.add_argument("file")
    i.set_defaults(func=cmd_inspect)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
