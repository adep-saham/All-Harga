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

    rows = []
    update_label = ""
    
    # Cari semua blok vendor berdasarkan id
    vendor_blocks = soup.find_all("div", id=True)

    for block in vendor_blocks:
        vendor = block.get("id", "").strip().upper()
        if not vendor:
            continue

        # cari label update
        update_div = block.find("div", string=re.compile("Diperbarui"))
        if update_div:
            update_label = update_div.get_text(strip=True)

        # cari semua row grid harga
        grids = block.find_all("div", class_=re.compile("grid grid-cols-5"))

        for g in grids:
            cols = g.find_all("div")
            if len(cols) != 3:
                continue

            try:
                weight = float(cols[0].get_text(strip=True))
                sell = rupiah_to_int(cols[1].get_text(strip=True))
                buy = rupiah_to_int(cols[2].get_text(strip=True))
            except:
                continue

            if weight <= 0:
                continue

            rows.append({
                "snapshot_ts": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "update_label": update_label,
                "source_site": "galeri24",
                "vendor": vendor,
                "weight_g": weight,
                "sell_idr": sell,
                "buyback_idr": buy,
                "source_url": URL_GALERI24,
            })

    if not rows:
        raise RuntimeError("Galeri24: tidak menemukan data harga.")

    df = pd.DataFrame(rows)
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
