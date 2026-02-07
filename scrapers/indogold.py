# scrapers/indogold.py
import pandas as pd
import re

URL_INDOGOLD = "https://www.indogold.id/detail-emas-batangan"

def _idr(text: str) -> int:
    if not text:
        return 0
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0

def _weight_g(name: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*Gram", name, flags=re.I)
    return float(m.group(1)) if m else 0.0

def _extract_last_update(text: str) -> str | None:
    m = re.search(
        r"Last\s*Update\s*:\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}\s+[0-9]{2}:[0-9]{2})",
        text,
        flags=re.I
    )
    return m.group(1).strip() if m else None

def _norm_vendor(product: str) -> str:
    """
    Biar vendor rapi dan konsisten.
    """
    p = (product or "").strip()
    up = p.upper()

    if up.startswith("UBS"):
        return "UBS"
    if "ANTAM" in up:
        return "Antam"
    if up.startswith("LM") or "LOGAM MULIA" in up:
        return "LM"
    # fallback: kata pertama
    return (p.split()[0] if p else "IndoGold").title()

def parse_indogold(html: str):
    """
    Return:
      df columns: vendor, weight_g, sell_idr, buyback_idr
      update_label: str
    """
    # strip tags kasar -> text
    text = re.sub(r"<[^>]+>", "\n", html or "")
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"\r", "", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n\s+", "\n", text)

    last_update = _extract_last_update(text)

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    rows = []
    i = 0
    while i < len(lines):
        if lines[i].lower() == "nama" and i + 1 < len(lines):
            product = lines[i + 1]

            buy_price = 0
            sell_price = 0

            window = lines[i:i+30]
            for j in range(len(window) - 1):
                if window[j].lower() == "harga beli":
                    buy_price = _idr(window[j + 1])
                elif window[j].lower() == "harga jual":
                    sell_price = _idr(window[j + 1])

            w = _weight_g(product)
            vendor = _norm_vendor(product)

            # validasi minimal
            if w > 0 and (buy_price > 0 or sell_price > 0):
                rows.append({
                    "product": product,
                    "vendor": vendor,
                    "weight_g": w,
                    "sell_idr": buy_price,      # harga beli (ke konsumen)
                    "buyback_idr": sell_price,  # harga jual (buyback)
                })
        i += 1

    df = pd.DataFrame(rows)

    if df.empty:
        label = "IndoGold — parsing kosong"
        if last_update:
            label = f"IndoGold — parsing kosong — Last Update: {last_update}"
        return pd.DataFrame(columns=["vendor", "weight_g", "sell_idr", "buyback_idr"]), label

    # tipe data
    df["weight_g"] = pd.to_numeric(df["weight_g"], errors="coerce").fillna(0.0)
    df["sell_idr"] = pd.to_numeric(df["sell_idr"], errors="coerce").fillna(0).astype(int)
    df["buyback_idr"] = pd.to_numeric(df["buyback_idr"], errors="coerce").fillna(0).astype(int)

    # 1) buang duplikat product (sering muncul 2x karena template/hidden)
    df = df.drop_duplicates(subset=["product", "sell_idr", "buyback_idr"], keep="first")

    # 2) dedup per vendor + weight (ambil harga max supaya satu baris per berat)
    df = (
        df.groupby(["vendor", "weight_g"], as_index=False)
          .agg({"sell_idr": "max", "buyback_idr": "max"})
          .sort_values(["vendor", "weight_g"])
          .reset_index(drop=True)
    )

    label = "IndoGold"
    if last_update:
        label = f"IndoGold — Last Update: {last_update}"
    else:
        label = "IndoGold — Last Update: (tidak terbaca)"

    return df, label
