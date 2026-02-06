import re
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup

URL_GALERI24 = "https://galeri24.co.id/harga-emas"

WEIGHT_ORDER = [0.1, 0.25, 0.5, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000]
WEIGHT_RANK = {w: i for i, w in enumerate(WEIGHT_ORDER)}

def weight_sort_key(w: float):
    if w in WEIGHT_RANK:
        return (0, WEIGHT_RANK[w])
    return (1, w)

def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()

def rupiah_to_int(s: str) -> int:
    s = str(s).replace("Rp", "").replace(" ", "").strip()
    s = s.replace(".", "").replace(",", "")
    return int(s) if s.isdigit() else 0

def parse_update_label(text: str) -> str:
    m = re.search(r"(Diperbarui\s+[A-Za-z]+,\s*\d{1,2}\s+[A-Za-z]+\s+\d{4})", text)
    if m:
        return m.group(1)
    return f"Diperbarui {datetime.now().strftime('%Y-%m-%d')}"

def parse_galeri24(html: str) -> tuple[pd.DataFrame, str]:
    soup = BeautifulSoup(html, "html.parser")
    text = normalize_spaces(soup.get_text(" ", strip=True))
    update_label = parse_update_label(text)

    block_pattern = re.compile(
        r"Harga\s+(?P<vendor>.+?)\s+Berat\s+Harga\s+Jual\s+Harga\s+Buyback\s+(?P<body>.+?)"
        r"(?=(?:\s+Harga\s+.+?\s+Berat\s+Harga\s+Jual\s+Harga\s+Buyback)|(?:\s+Diperbarui)|\Z)",
        re.IGNORECASE,
    )
    blocks = list(block_pattern.finditer(text))
    if not blocks:
        raise RuntimeError("Galeri24: tidak menemukan blok vendor (struktur berubah).")

    pair_pattern = re.compile(
        r"(?P<w>\d+(?:\.\d+)?)\s+Rp\s*(?P<sell>[\d\.\,]+)\s+Rp\s*(?P<buy>[\d\.\,]+)",
        re.IGNORECASE,
    )

    rows = []
    vendor_order = []
    for b in blocks:
        vendor = normalize_spaces(b.group("vendor")).upper()
        if vendor not in vendor_order:
            vendor_order.append(vendor)

        body = b.group("body")
        for p in pair_pattern.finditer(body):
            w = float(p.group("w"))
            if not (0.1 <= w <= 1000):
                continue
            rows.append({
                "snapshot_ts": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "update_label": update_label,
                "source_site": "galeri24",
                "vendor": vendor,
                "weight_g": w,
                "sell_idr": rupiah_to_int("Rp" + p.group("sell")),
                "buyback_idr": rupiah_to_int("Rp" + p.group("buy")),
                "source_url": URL_GALERI24,
            })

    if not rows:
        raise RuntimeError("Galeri24: tidak menemukan pasangan berat+harga.")

    df = pd.DataFrame(rows).drop_duplicates(subset=["update_label", "vendor", "weight_g", "sell_idr", "buyback_idr"])

    vendor_rank = {v: i for i, v in enumerate(vendor_order)}
    df["__vr"] = df["vendor"].map(lambda x: vendor_rank.get(x, 9999))
    df["__w0"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[0])
    df["__w1"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[1])
    df = df.sort_values(["__vr", "vendor", "__w0", "__w1"]).drop(columns=["__vr", "__w0", "__w1"])

    return df, update_label
