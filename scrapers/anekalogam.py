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
    """
    Mengekstrak informasi tanggal pembaruan harga langsung dari teks halaman.
    """
    # 1. Mencari pola "Terakhir Diperbarui: dd Month yyyy hh.mm"
    m_update = re.search(r"Terakhir Diperbarui:\s*([\d]+\s+[a-zA-Z]+\s+[\d]+\s+[\d\.]+)", text, re.IGNORECASE)
    if m_update:
        return f"Terakhir Diperbarui: {m_update.group(1).strip()}"
    
    # 2. Fallback jika tidak ditemukan, cari info tahun produksi
    m_year = re.search(r"Harga berlaku.*?tahun\s+(\d{4})", text, re.IGNORECASE)
    if m_year:
        return f"Harga berlaku produksi tahun {m_year.group(1)}"
    
    # 3. Fallback terakhir menggunakan waktu saat ini
    return f"Snapshot {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

def parse_anekalogam(html: str) -> tuple[pd.DataFrame, str]:
    soup = BeautifulSoup(html, "html.parser")
    text = normalize_spaces(soup.get_text(" ", strip=True))
    
    # Sekarang mengambil label berdasarkan teks "Terakhir Diperbarui"
    update_label = parse_update_label(text)

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
        raise RuntimeError("AnekaLogam: tidak menemukan data harga. Struktur halaman mungkin berubah.")

    df = pd.DataFrame(rows).drop_duplicates(subset=["update_label", "weight_g", "sell_idr", "buyback_idr"])

    df["__w0"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[0])
    df["__w1"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[1])
    df = df.sort_values(["__w0", "__w1"]).drop(columns=["__w0", "__w1"])

    return df, update_label
