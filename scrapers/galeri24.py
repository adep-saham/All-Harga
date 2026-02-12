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

    # update label (tetap)
    full_text = normalize_spaces(soup.get_text(" ", strip=True))
    update_label = parse_update_label(full_text)

    rows = []
    snapshot_ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # Cari semua heading yang bertuliskan "Harga <VENDOR>"
    headings = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        t = normalize_spaces(tag.get_text(" ", strip=True))
        if t.upper().startswith("HARGA "):
            headings.append((tag, t))

    if not headings:
        raise RuntimeError("Galeri24: heading 'Harga <vendor>' tidak ditemukan (struktur berubah).")

    def extract_vendor(heading_text: str) -> str:
        # "Harga GALERI 24" -> "GALERI 24"
        v = heading_text.strip()[len("Harga "):].strip()
        v = normalize_spaces(v).upper()
        return v

    # Untuk tiap heading, ambil tabel terdekat setelahnya
    for tag, heading_text in headings:
        vendor = extract_vendor(heading_text)

        # cari table berikutnya setelah heading ini
        table = tag.find_next("table")
        if table is None:
            continue

        # ambil semua row tabel
        for tr in table.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) < 3:
                continue

            w_raw = normalize_spaces(tds[0].get_text(" ", strip=True))
            sell_raw = normalize_spaces(tds[1].get_text(" ", strip=True))
            buy_raw = normalize_spaces(tds[2].get_text(" ", strip=True))

            # skip header
            if w_raw.lower() in ["berat", "weight"]:
                continue

            # berat bisa "0.5" atau "0.5 gr"
            m = re.search(r"(\d+(?:\.\d+)?)", w_raw)
            if not m:
                continue
            w = float(m.group(1))
            if not (0.1 <= w <= 1000):
                continue

            sell = rupiah_to_int(sell_raw)
            buy = rupiah_to_int(buy_raw)

            # skip baris kosong
            if sell == 0 and buy == 0:
                continue

            rows.append({
                "snapshot_ts": snapshot_ts,
                "update_label": update_label,
                "source_site": "galeri24",
                "vendor": vendor,          # ini yang dipakai untuk grouping di Streamlit
                "weight_g": w,
                "sell_idr": sell,
                "buyback_idr": buy,
                "source_url": URL_GALERI24,
            })

    if not rows:
        raise RuntimeError("Galeri24: tabel ditemukan tapi tidak ada data berat+harga yang berhasil diparse.")

    df = pd.DataFrame(rows)

    # dedup aman (kalau HTML punya duplikasi row)
    df = df.drop_duplicates(subset=["update_label", "vendor", "weight_g", "sell_idr", "buyback_idr"])

    # sorting vendor (berdasarkan kemunculan heading di halaman)
    vendor_order = [extract_vendor(h[1]) for h in headings]
    vendor_rank = {v: i for i, v in enumerate(vendor_order)}
    df["__vr"] = df["vendor"].map(lambda x: vendor_rank.get(x, 9999))
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
