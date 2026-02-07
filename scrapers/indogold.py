# scrapers/indogold.py
import re
import pandas as pd
from bs4 import BeautifulSoup

# Pakai endpoint detail (lebih stabil, tidak tergantung JS tab)
URL_INDOGOLD = "https://www.indogold.id/detail-emas-batangan"

STD_COLS = ["vendor", "weight_g", "sell_idr", "buyback_idr"]

# Pecahan yang mau ditampilkan di tab "Perbandingan" (sesuai web)
COMPARE_WEIGHTS = {0.5, 1, 2, 3, 5, 10, 25, 50, 100}


def _idr(text: str) -> int:
    if not text:
        return 0
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0


def _weight_gram(name: str) -> float:
    # contoh: "UBS Gold 99.99% 1.0 Gram"
    # contoh: "ANTAM 5 Gram"
    s = (name or "").replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*Gram", s, flags=re.I)
    return float(m.group(1)) if m else 0.0


def _extract_last_update(text: str) -> str | None:
    # kadang ada "Last Update : 07 February 2026 16:41"
    m = re.search(
        r"Last\s*Update\s*:\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}\s+[0-9]{2}:[0-9]{2})",
        text,
        flags=re.I,
    )
    return m.group(1).strip() if m else None


def parse_indogold(html: str):
    """
    Perbandingan-only:
      - vendor: "Perbandingan - UBS", "Perbandingan - Antam"
      - sell_idr = Harga Beli (ke konsumen)
      - buyback_idr = 0 (tab perbandingan tidak pakai buyback)
    """
    # Default kosong tapi kolom lengkap (biar app.py aman)
    empty_df = pd.DataFrame(columns=STD_COLS)

    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text("\n", strip=True)
    last_update = _extract_last_update(full_text)

    # Strategy parsing dari teks (stabil): pola berulang
    # Nama
    # <PRODUCT>
    # Harga Beli
    # <RP>
    # Harga Jual
    # <RP>
    lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]

    rows = []
    i = 0
    while i < len(lines):
        if lines[i].lower() == "nama" and i + 1 < len(lines):
            product = lines[i + 1]

            # window scan
            buy_price = 0
            for j in range(i, min(i + 25, len(lines) - 1)):
                if lines[j].lower() == "harga beli":
                    buy_price = _idr(lines[j + 1])
                    break

            w = _weight_gram(product)

            # classify brand: UBS vs Antam
            p_low = product.lower()
            brand = None
            if "ubs" in p_low:
                brand = "UBS"
            elif "antam" in p_low or "logam mulia" in p_low or "lm" in p_low:
                brand = "Antam"

            # ambil hanya UBS/Antam dan pecahan compare
            if brand and w in COMPARE_WEIGHTS and buy_price > 0:
                rows.append({
                    "vendor": f"Perbandingan - {brand}",
                    "weight_g": w,
                    "sell_idr": buy_price,
                    "buyback_idr": 0,
                })
        i += 1

    if not rows:
        label = "IndoGold — Perbandingan (data tidak ditemukan)"
        if last_update:
            label = f"IndoGold — Perbandingan — Last Update: {last_update}"
        return empty_df, label

    df = pd.DataFrame(rows, columns=STD_COLS)

    # Dedup by vendor+weight (kalau ada varian ganda), ambil harga MIN (umumnya paling relevan)
    df["weight_g"] = pd.to_numeric(df["weight_g"], errors="coerce").fillna(0.0)
    df["sell_idr"] = pd.to_numeric(df["sell_idr"], errors="coerce").fillna(0).astype(int)
    df["buyback_idr"] = pd.to_numeric(df["buyback_idr"], errors="coerce").fillna(0).astype(int)

    df = (
        df.groupby(["vendor", "weight_g"], as_index=False)
          .agg({"sell_idr": "min", "buyback_idr": "max"})
          .sort_values(["vendor", "weight_g"])
          .reset_index(drop=True)
    )

    label = "IndoGold — Perbandingan"
    if last_update:
        label = f"IndoGold — Perbandingan — Last Update: {last_update}"

    return df, label
