# scrapers/indogold.py
import pandas as pd
import re

URL_INDOGOLD = "https://www.indogold.id/detail-emas-batangan"

ALLOWED_WEIGHTS = {0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 25.0, 50.0, 100.0}

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
    up = (product or "").upper()
    if "UBS" in up:
        return "UBS"
    if "ANTAM" in up:
        return "Antam"
    # fallback: kata pertama
    p = (product or "").strip()
    return (p.split()[0] if p else "IndoGold").title()

def parse_indogold(html: str):
    # strip tags -> text lines
    text = re.sub(r"<[^>]+>", "\n", html or "")
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"\r", "", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n\s+", "\n", text)

    last_update = _extract_last_update(text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # cari semua index "Nama"
    idxs = [i for i, l in enumerate(lines) if l.lower() == "nama"]

    rows = []
    for k, start in enumerate(idxs):
        end = idxs[k + 1] if k + 1 < len(idxs) else len(lines)
        block = lines[start:end]

        # product ada di baris setelah "Nama"
        if len(block) < 2:
            continue
        product = block[1]
        w = _weight_g(product)
        vendor = _norm_vendor(product)

        # hanya UBS & Antam, dan hanya berat yang ada di tabel compare
        if vendor not in {"UBS", "Antam"}:
            continue
        if w not in ALLOWED_WEIGHTS:
            continue

        buy_price = 0
        sell_price = 0

        # cari harga dalam blok ini saja (anti nyangkut produk sebelah)
        for i in range(len(block) - 1):
            if block[i].lower() == "harga beli":
                buy_price = _idr(block[i + 1])
            elif block[i].lower() == "harga jual":
                sell_price = _idr(block[i + 1])

        if buy_price or sell_price:
            rows.append({
                "vendor": vendor,
                "weight_g": w,
                "sell_idr": buy_price,      # harga beli (ke konsumen)
                "buyback_idr": sell_price,  # harga jual (buyback)
            })

    df = pd.DataFrame(rows, columns=["vendor", "weight_g", "sell_idr", "buyback_idr"])

    if df.empty:
        label = "IndoGold — parsing kosong"
        if last_update:
            label = f"IndoGold — parsing kosong — Last Update: {last_update}"
        return df, label

    # rapikan tipe
    df["weight_g"] = pd.to_numeric(df["weight_g"], errors="coerce").fillna(0.0)
    df["sell_idr"] = pd.to_numeric(df["sell_idr"], errors="coerce").fillna(0).astype(int)
    df["buyback_idr"] = pd.to_numeric(df["buyback_idr"], errors="coerce").fillna(0).astype(int)

    # dedup per vendor+weight
    df = (
        df.sort_values(["vendor", "weight_g", "sell_idr", "buyback_idr"])
          .groupby(["vendor", "weight_g"], as_index=False)
          .agg({"sell_idr": "max", "buyback_idr": "max"})
          .sort_values(["vendor", "weight_g"])
          .reset_index(drop=True)
    )

    label = "IndoGold"
    if last_update:
        label = f"IndoGold — Last Update: {last_update}"
    return df, label
