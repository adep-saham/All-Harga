import pandas as pd
import re

URL_INDOGOLD = "https://www.indogold.id/detail-emas-batangan"

def _idr(text: str) -> int:
    if not text:
        return 0
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0

def _weight_g(name: str) -> float:
    # contoh: "UBS Gold 99.99% 1.0 Gram"
    m = re.search(r"(\d+(?:\.\d+)?)\s*Gram", name, flags=re.I)
    return float(m.group(1)) if m else 0.0

def _extract_last_update(text: str) -> str | None:
    # beberapa variasi tampilan mungkin: "Last Update : 07 February 2026 15:57"
    m = re.search(r"Last\s*Update\s*:\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}\s+[0-9]{2}:[0-9]{2})", text)
    return m.group(1).strip() if m else None

def parse_indogold(html: str):
    """
    Return:
      df columns: vendor, weight_g, sell_idr, buyback_idr
      update_label: str
    """
    # ambil semua teks supaya robust walau HTML berubah sedikit
    # (tanpa BeautifulSoup biar dependency minimal; tapi tetap efektif karena pola textnya konsisten)
    text = re.sub(r"<[^>]+>", "\n", html)  # strip tags kasar
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n\s+", "\n", text)

    last_update = _extract_last_update(text)

    # pecah lines
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    rows = []
    i = 0
    while i < len(lines):
        # blok umumnya:
        # Nama
        # <product>
        # Harga Beli
        # Rp ...
        # Harga Jual
        # Rp ...
        if lines[i].lower() == "nama" and i + 1 < len(lines):
            product = lines[i + 1]

            buy_price = 0
            sell_price = 0

            # scan window kecil setelah "Nama"
            window = lines[i:i+25]
            for j in range(len(window) - 1):
                if window[j].lower() == "harga beli":
                    buy_price = _idr(window[j + 1])
                elif window[j].lower() == "harga jual":
                    sell_price = _idr(window[j + 1])

            # skip kalau kosong
            if buy_price or sell_price:
                brand = product.split()[0] if product else "IndoGold"
                rows.append({
                    "vendor": brand,                 # biar tampil per brand (UBS/Antam/dll)
                    "weight_g": _weight_g(product),
                    "sell_idr": buy_price,           # Harga Beli (ke konsumen)
                    "buyback_idr": sell_price,       # Harga Jual (buyback)
                })

        i += 1

    df = pd.DataFrame(rows)
    if not df.empty:
        # rapikan tipe & sort
        df["weight_g"] = pd.to_numeric(df["weight_g"], errors="coerce").fillna(0.0)
        df["sell_idr"] = pd.to_numeric(df["sell_idr"], errors="coerce").fillna(0).astype(int)
        df["buyback_idr"] = pd.to_numeric(df["buyback_idr"], errors="coerce").fillna(0).astype(int)
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)

    label = "IndoGold"
    if last_update:
        label = f"IndoGold — Last Update: {last_update}"
    else:
        label = "IndoGold — Last Update: (tidak terbaca)"

    return df, label
