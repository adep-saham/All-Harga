import re
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup

URL_ANEKALOGAM = "https://anekalogam.co.id/id"

WEIGHT_ORDER = [0.1, 0.25, 0.5, 1, 2, 3, 5, 10, 25, 50, 100, 250, 500, 1000]
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
    # Halaman menampilkan teks: "** Harga berlaku untuk ... tahun 2025" dll
    # Kita ambil yang paling stabil: tanggal snapshot + (kalau ada) tahun produksi
    m = re.search(r"Harga berlaku.*?tahun\s+(\d{4})", text, re.IGNORECASE)
    if m:
        return f"Harga berlaku untuk produksi tahun {m.group(1)}"
    return f"Snapshot {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

def parse_anekalogam(html: str) -> tuple[pd.DataFrame, str]:
    soup = BeautifulSoup(html, "html.parser")
    text = normalize_spaces(soup.get_text(" ", strip=True))
    update_label = parse_update_label(text)

    # Tabel di halaman berisi pola seperti:
    # "1gram Rp 3.280.000 Rp 2.800.000" dst. :contentReference[oaicite:1]{index=1}
    # Kita buat regex toleran:
    # - weight bisa "1gram" atau "1 gram"
    # - harga bisa "Rp 3.280.000"
    pair = re.compile(
        r"(\d+(?:[.,]\d+)?)\s*gram\s*Rp\s*([\d\.\,]+)\s*Rp\s*([\d\.\,]+)",
        re.IGNORECASE,
    )

    rows = []
    for w_raw, sell_raw, buy_raw in pair.findall(text):
        w = float(w_raw.replace(",", "."))
        if not (0.1 <= w <= 1000):
            continue

        rows.append({
            "snapshot_ts": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "update_label": update_label,
            "source_site": "anekalogam",
            "vendor": "ANEKA LOGAM",
            "weight_g": w,
            "sell_idr": rupiah_to_int("Rp" + sell_raw),
            "buyback_idr": rupiah_to_int("Rp" + buy_raw),
            "source_url": URL_ANEKALOGAM,
        })

    if not rows:
        # Debug cepat kalau struktur berubah
        raise RuntimeError("AnekaLogam: tidak menemukan pasangan '<gram> Rp<jual> Rp<beli>'. Struktur halaman berubah.")

    df = pd.DataFrame(rows).drop_duplicates(subset=["update_label", "weight_g", "sell_idr", "buyback_idr"])

    df["__w0"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[0])
    df["__w1"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[1])
    df = df.sort_values(["__w0", "__w1"]).drop(columns=["__w0", "__w1"])

    return df, update_label
