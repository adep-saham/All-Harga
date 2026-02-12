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


def parse_galeri24(html: str) -> Tuple[pd.DataFrame, str]:
    """
    Parse halaman https://galeri24.co.id/harga-emas.

    IMPORTANT:
    Halaman ini memuat beberapa tabel vendor sekaligus (minimal: ANTAM dan GALERI 24).
    Output df akan berisi semua vendor. Saat dipakai untuk 'Antam 100gr',
    WAJIB filter vendor == 'ANTAM' dan weight_g == 100.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = normalize_spaces(soup.get_text(" ", strip=True))
    update_label = parse_update_label(text)

    # Ambil tiap blok tabel:
    # "Harga ANTAM ... Berat Harga Jual Harga Buyback ... (rows) ... Harga GALERI 24 ..."
    block_pattern = re.compile(
        r"Harga\s+(?P<vendor>.+?)\s+Berat\s+Harga\s+Jual\s+Harga\s+Buyback\s+(?P<body>.+?)"
        r"(?=(?:\s+Harga\s+.+?\s+Berat\s+Harga\s+Jual\s+Harga\s+Buyback)|(?:\s+Diperbarui)|\Z)",
        re.IGNORECASE,
    )
    blocks = list(block_pattern.finditer(text))
    if not blocks:
        raise RuntimeError("Galeri24: tidak menemukan blok vendor (struktur halaman berubah).")

    # Tiap baris: "<w> Rp <sell> Rp <buyback>"
    pair_pattern = re.compile(
        r"(?P<w>\d+(?:\.\d+)?)\s+Rp\s*(?P<sell>[\d\.,]+)\s+Rp\s*(?P<buy>[\d\.,]+)",
        re.IGNORECASE,
    )

    snapshot_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    vendor_order = []

    for b in blocks:
        raw_vendor = b.group("vendor")
        vendor = normalize_vendor(raw_vendor)
        if vendor not in vendor_order:
            vendor_order.append(vendor)

        body = b.group("body")
        for p in pair_pattern.finditer(body):
            w = float(p.group("w"))
            # Batasi nilai w yang masuk akal
            if not (0.1 <= w <= 1000):
                continue

            rows.append(
                {
                    "snapshot_ts": snapshot_ts,
                    "update_label": update_label,
                    "source_site": "galeri24",
                    "vendor": vendor,  # hasil normalisasi: 'ANTAM' / 'GALERI 24'
                    "weight_g": w,
                    "sell_idr": rupiah_to_int("Rp" + p.group("sell")),
                    "buyback_idr": rupiah_to_int("Rp" + p.group("buy")),
                    "source_url": URL_GALERI24,
                }
            )

    if not rows:
        raise RuntimeError("Galeri24: tidak menemukan pasangan berat+harga (regex gagal / struktur berubah).")

    df = pd.DataFrame(rows)

    # Dedup agar aman jika teks halaman punya pengulangan
    df = df.drop_duplicates(
        subset=["update_label", "vendor", "weight_g", "sell_idr", "buyback_idr"]
    )

    # Sorting vendor & berat
    vendor_rank = {v: i for i, v in enumerate(vendor_order)}
    df["__vr"] = df["vendor"].map(lambda x: vendor_rank.get(x, 9999))
    df["__w0"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[0])
    df["__w1"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[1])
    df = df.sort_values(["__vr", "vendor", "__w0", "__w1"]).drop(columns=["__vr", "__w0", "__w1"])

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
