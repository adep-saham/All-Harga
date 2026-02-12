import re
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import pandas as pd
from bs4 import BeautifulSoup

URL_GALERI24 = "https://galeri24.co.id/harga-emas"

# Urutan berat (gram) untuk sorting yang rapi
WEIGHT_ORDER = [0.1, 0.25, 0.5, 1, 2, 3, 5, 10, 25, 50, 100, 250, 500, 1000]
WEIGHT_RANK = {w: i for i, w in enumerate(WEIGHT_ORDER)}


def weight_sort_key(w: float):
    if w in WEIGHT_RANK:
        return (0, WEIGHT_RANK[w])
    return (1, w)


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


def rupiah_to_int(s: str) -> int:
    """Konversi string rupiah seperti 'Rp290.277.000' -> 290277000."""
    s = str(s).replace("Rp", "").replace(" ", "").strip()
    s = s.replace(".", "").replace(",", "")
    return int(s) if s.isdigit() else 0


def parse_update_label(text: str) -> str:
    """Ambil label update dari halaman (contoh: 'Diperbarui Kamis, 12 Februari 2026')."""
    # Halaman Galeri24 biasanya berbahasa Indonesia, tapi kita buat cukup fleksibel.
    m = re.search(
        r"(Diperbarui\s+[A-Za-zÀ-ÿ]+,\s*\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        # Normalisasi kapitalisasi awal saja biar konsisten
        return normalize_spaces(m.group(1))
    # Fallback: tetap ada label agar dedup jalan
    return f"Diperbarui {datetime.now().strftime('%Y-%m-%d')}"


def normalize_vendor(raw_vendor: str) -> str:
    """Normalisasi vendor agar tidak 'ANTAM' dan 'GALERI 24' tercampur variasi penulisan."""
    v = normalize_spaces(raw_vendor).upper()
    # Banyak variasi: GALERI24 / GALERI 24 / GALERI-24
    if "ANTAM" in v:
        return "ANTAM"
    if "GALERI" in v:
        return "GALERI 24"
    return v


def parse_galeri24(html: str) -> tuple[pd.DataFrame, str]:
    soup = BeautifulSoup(html, "html.parser")

    full_text = normalize_spaces(soup.get_text(" ", strip=True))
    update_label = parse_update_label(full_text)
    snapshot_ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    def extract_vendor(heading_text: str) -> str:
        # "Harga GALERI 24" -> "GALERI 24"
        v = heading_text.strip()[len("Harga "):].strip()
        return normalize_spaces(v).upper()

    # 1) Cari semua elemen yang teksnya diawali "Harga "
    # (tidak hanya h1-h6, karena kadang pakai div/span)
    headings = []
    for tag in soup.find_all(True):
        t = tag.get_text(" ", strip=True)
        if not t:
            continue
        t = normalize_spaces(t)
        if t.upper().startswith("HARGA "):
            # hindari teks kepanjangan (kadang sidebar/footer kebaca)
            if 5 <= len(t) <= 40:
                headings.append((tag, t))

    # dedup heading by text order
    seen = set()
    uniq_headings = []
    for tag, t in headings:
        key = t.upper()
        if key in seen:
            continue
        seen.add(key)
        uniq_headings.append((tag, t))
    headings = uniq_headings

    if not headings:
        raise RuntimeError("Galeri24: heading 'Harga <vendor>' tidak ditemukan (struktur berubah).")

    rows = []

    for tag, heading_text in headings:
        vendor = extract_vendor(heading_text)

        # tabel terdekat setelah heading
        table = tag.find_next("table")
        if table is None:
            continue

        # baca baris
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 3:
                continue

            cell_texts = [normalize_spaces(c.get_text(" ", strip=True)) for c in cells]

            # skip header baris
            joined = " ".join(cell_texts).lower()
            if "berat" in joined and "harga" in joined:
                continue

            # ambil kandidat harga: sel yang mengandung "Rp"
            price_cells = [t for t in cell_texts if "rp" in t.lower()]
            if len(price_cells) < 2:
                # kalau tidak ada 2 harga, skip
                continue

            sell_raw = price_cells[0]
            buy_raw = price_cells[1]

            # ambil kandidat berat: sel pertama yang mengandung angka (dan bukan rupiah)
            w = None
            for t in cell_texts:
                if "rp" in t.lower():
                    continue
                m = re.search(r"(\d+(?:\.\d+)?)", t)
                if m:
                    try:
                        w = float(m.group(1))
                        break
                    except:
                        pass
            if w is None:
                continue

            # sanity
            if not (0.001 <= w <= 5000):
                continue

            sell = rupiah_to_int(sell_raw)
            buy = rupiah_to_int(buy_raw)

            # jangan buang buyback 0 (karena ada yang memang Rp0)
            if sell == 0 and buy == 0:
                continue

            rows.append({
                "snapshot_ts": snapshot_ts,
                "update_label": update_label,
                "source_site": "galeri24",
                "vendor": vendor,          # ini untuk grouping di Streamlit
                "weight_g": w,
                "sell_idr": sell,
                "buyback_idr": buy,
                "source_url": URL_GALERI24,
            })

    if not rows:
        raise RuntimeError("Galeri24: tabel ditemukan tapi tidak ada data berat+harga yang berhasil diparse.")

    df = pd.DataFrame(rows)

    # dedup jika ada duplikasi identik
    df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr", "buyback_idr"]).reset_index(drop=True)

    # urutkan vendor sesuai urutan heading di halaman
    vendor_order = [extract_vendor(t) for _, t in headings]
    rank = {v: i for i, v in enumerate(vendor_order)}
    df["__vr"] = df["vendor"].map(lambda x: rank.get(x, 9999))
    df["__w0"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[0])
    df["__w1"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[1])
    df = df.sort_values(["__vr", "vendor", "__w0", "__w1"]).drop(columns=["__vr", "__w0", "__w1"]).reset_index(drop=True)

    return df, update_label




def pick_price_row(df: pd.DataFrame, vendor: str, weight_g: float) -> Optional[Dict]:
    """
    Ambil 1 baris harga untuk vendor+weight tertentu.
    Contoh:
        pick_price_row(df, 'ANTAM', 100)
        pick_price_row(df, 'GALERI 24', 100)
    """
    v = normalize_vendor(vendor)
    m = (df["vendor"] == v) & (df["weight_g"].astype(float) == float(weight_g))
    out = df.loc[m]
    if out.empty:
        return None
    # Ambil yang terbaru jika ada multiple snapshot
    out = out.sort_values("snapshot_ts").tail(1)
    return out.iloc[0].to_dict()
