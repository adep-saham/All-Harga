# scrapers/indogold.py
import re
import pandas as pd
from bs4 import BeautifulSoup

URL_INDOGOLD = "https://www.indogold.id/harga-emas-hari-ini"

# kolom standar yang dipakai app.py
STD_COLS = ["vendor", "weight_g", "sell_idr", "buyback_idr"]


def _idr(x: str) -> int:
    """Parse 'Rp. 1.234.567' -> 1234567"""
    if not x:
        return 0
    digits = re.sub(r"[^\d]", "", x)
    return int(digits) if digits else 0


def _gram(x: str) -> float:
    """Parse '0.5 Gram' / '0,5 Gram' / '25.0 Gram' -> float"""
    s = (x or "").replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else 0.0


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _find_last_update(text: str) -> str | None:
    # "Last Update : 07 February 2026 12:28"
    m = re.search(
        r"Last\s*Update\s*:\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}\s+[0-9]{2}:[0-9]{2})",
        text,
    )
    return m.group(1).strip() if m else None


def _table_matrix(table) -> list[list[str]]:
    """Return list of rows; each row is list of cell texts (th/td)."""
    out = []
    for tr in table.find_all("tr"):
        cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
        if cells:
            out.append(cells)
    return out


def _find_compare_table(soup: BeautifulSoup):
    """
    Cari tabel Perbandingan yang punya:
      - kolom 'pecahan'
      - ada kata 'ubs' dan 'antam'
      - ada 2x 'harga beli' (untuk UBS & Antam)
    """
    for t in soup.find_all("table"):
        rows = _table_matrix(t)
        if len(rows) < 2:
            continue

        header = rows[0]
        h = [_norm(x) for x in header]
        htxt = " | ".join(h)

        # ciri kuat tabel perbandingan
        if "pecahan" in htxt and "ubs" in htxt and "antam" in htxt:
            # harus ada minimal 2 kolom "harga beli"
            buy_cols = [i for i, col in enumerate(h) if "harga beli" in col]
            if len(buy_cols) >= 2:
                return t, rows, buy_cols

    return None, None, None


def parse_indogold(html: str):
    """
    IndoGold (Perbandingan only):
      - vendor: "Perbandingan - UBS", "Perbandingan - Antam"
      - sell_idr = Harga Beli
      - buyback_idr = 0 (karena tabel compare tidak memuat buyback)
    """
    # default df kosong tapi kolom lengkap (biar app.py nggak KeyError)
    empty_df = pd.DataFrame(columns=STD_COLS)

    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text(" ", strip=True)
    last_update = _find_last_update(full_text)

    table, rows, buy_cols = _find_compare_table(soup)
    if table is None:
        label = "IndoGold — Perbandingan (tabel tidak ditemukan)"
        if last_update:
            label = f"IndoGold — Perbandingan — Last Update: {last_update}"
        return empty_df, label

    # tabel compare biasanya:
    # Pecahan | UBS | Harga Beli | Antam | Harga Beli
    # -> dua buy_cols pertama = UBS_Buy, Antam_Buy (urut muncul)
    ubs_buy_idx, antam_buy_idx = buy_cols[0], buy_cols[1]

    out = []
    for r in rows[1:]:
        if len(r) <= max(ubs_buy_idx, antam_buy_idx):
            continue

        w = _gram(r[0])
        if w <= 0:
            continue

        ubs_buy = _idr(r[ubs_buy_idx])
        antam_buy = _idr(r[antam_buy_idx])

        # Skip baris kosong
        if not (ubs_buy or antam_buy):
            continue

        if ubs_buy:
            out.append({
                "vendor": "Perbandingan - UBS",
                "weight_g": w,
                "sell_idr": ubs_buy,
                "buyback_idr": 0,
            })

        if antam_buy:
            out.append({
                "vendor": "Perbandingan - Antam",
                "weight_g": w,
                "sell_idr": antam_buy,
                "buyback_idr": 0,
            })

    df = pd.DataFrame(out, columns=STD_COLS)

    # dedup vendor+weight ambil max
    if not df.empty:
        df["weight_g"] = pd.to_numeric(df["weight_g"], errors="coerce").fillna(0.0)
        df["sell_idr"] = pd.to_numeric(df["sell_idr"], errors="coerce").fillna(0).astype(int)
        df["buyback_idr"] = pd.to_numeric(df["buyback_idr"], errors="coerce").fillna(0).astype(int)

        df = (
            df.sort_values(["vendor", "weight_g", "sell_idr"])
              .groupby(["vendor", "weight_g"], as_index=False)
              .agg({"sell_idr": "max", "buyback_idr": "max"})
              .sort_values(["vendor", "weight_g"])
              .reset_index(drop=True)
        )

    label = "IndoGold — Perbandingan"
    if last_update:
        label = f"IndoGold — Perbandingan — Last Update: {last_update}"

    return df, label
