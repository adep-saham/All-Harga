# scrapers/hakabegold.py
import re
import pandas as pd
from bs4 import BeautifulSoup

URL_HAKABEGOLD = "https://www.logammuliahk.com/"  # fragment #work tidak dibutuhkan saat requests


def _idr(text: str) -> int:
    """Convert 'Rp1,473,000' / 'Rp 1.473.000' -> 1473000"""
    if not text:
        return 0
    t = str(text)
    t = t.replace("\xa0", " ")
    digits = re.sub(r"[^\d]", "", t)
    return int(digits) if digits else 0


def _float(text: str) -> float:
    """Convert '0.5' / '0,5' -> 0.5"""
    if text is None:
        return 0.0
    t = str(text).strip().replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", t)
    return float(m.group(1)) if m else 0.0


def _extract_update_label(full_text: str) -> str | None:
    """
    Cari tanggal seperti: '07 February 2026' / '7 February 2026'
    """
    if not full_text:
        return None
    m = re.search(
        r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b",
        full_text,
        flags=re.I
    )
    if m:
        return m.group(1).strip()
    return None


def _extract_buyback_per_gram(full_text: str) -> int:
    """
    Cari buyback per gram dari teks:
    'Buyback Emas Batangan Rp 2,650,000 /gram'
    """
    if not full_text:
        return 0
    # fleksibel: "Buyback" ... "Rp" ... "/gram"
    m = re.search(r"Buyback.*?Rp\s*([0-9\.,]+)\s*/\s*gram", full_text, flags=re.I | re.S)
    if m:
        return _idr(m.group(1))
    # fallback: cari 'Buyback' + angka Rp terbesar di sekitar
    idx = full_text.lower().find("buyback")
    if idx >= 0:
        window = full_text[idx: idx + 300]
        nums = re.findall(r"Rp\s*([0-9\.,]+)", window, flags=re.I)
        if nums:
            # ambil terbesar
            vals = [_idr(x) for x in nums]
            return max(vals) if vals else 0
    return 0


def _find_price_table(soup: BeautifulSoup):
    """
    Temukan tabel yang header-nya mengandung 'Berat' dan 'Harga End User'
    """
    for table in soup.find_all("table"):
        headers = []
        thead = table.find("thead")
        if thead:
            headers = [th.get_text(" ", strip=True).lower() for th in thead.find_all(["th", "td"])]
        else:
            # fallback: baris pertama
            first_tr = table.find("tr")
            if first_tr:
                headers = [x.get_text(" ", strip=True).lower() for x in first_tr.find_all(["th", "td"])]

        header_join = " | ".join(headers)
        if "berat" in header_join and "harga end user" in header_join:
            return table

    # fallback: tabel pertama
    tables = soup.find_all("table")
    return tables[0] if tables else None


def parse_hakabegold(html: str):
    """
    Return:
      df columns: vendor, weight_g, sell_idr, buyback_idr
      update_label: str
    """
    soup = BeautifulSoup(html or "", "html.parser")
    full_text = soup.get_text(" ", strip=True)

    date_str = _extract_update_label(full_text)
    buyback_per_gram = _extract_buyback_per_gram(full_text)

    table = _find_price_table(soup)
    rows = []

    if table:
        trs = table.find_all("tr")
        for tr in trs:
            tds = tr.find_all(["td", "th"])
            if not tds or len(tds) < 2:
                continue

            # skip header row
            if any("berat" in td.get_text(" ", strip=True).lower() for td in tds):
                continue

            # Struktur kolom pada screenshot:
            # 0: Berat
            # 1: Harga End User (total)
            # 2: Harga End User/gr
            # 3: Harga+PPH 22 (total)
            # 4: Harga+PPH 22/gr
            # 5: Stok
            berat = _float(tds[0].get_text(" ", strip=True))
            harga_end_user = _idr(tds[1].get_text(" ", strip=True))

            if berat <= 0 or harga_end_user <= 0:
                continue

            buyback_total = int(buyback_per_gram * berat) if buyback_per_gram > 0 else 0

            rows.append({
                "vendor": "HK Logam Mulia",
                "weight_g": float(berat),
                "sell_idr": int(harga_end_user),
                "buyback_idr": int(buyback_total),
            })

    df = pd.DataFrame(rows, columns=["vendor", "weight_g", "sell_idr", "buyback_idr"])

    if not df.empty:
        df["weight_g"] = pd.to_numeric(df["weight_g"], errors="coerce").fillna(0.0)
        df["sell_idr"] = pd.to_numeric(df["sell_idr"], errors="coerce").fillna(0).astype(int)
        df["buyback_idr"] = pd.to_numeric(df["buyback_idr"], errors="coerce").fillna(0).astype(int)
        df = df.sort_values(["vendor", "weight_g"]).reset_index(drop=True)

    label = "HK Logam Mulia"
    if date_str:
        label = f"HK Logam Mulia — Last Update: {date_str}"
    if buyback_per_gram > 0:
        label += f" — Buyback: Rp{buyback_per_gram:,}".replace(",", ".")

    return df, label
