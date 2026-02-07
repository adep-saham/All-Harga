import re
import pandas as pd
from bs4 import BeautifulSoup

URL_INDOGOLD = "https://www.indogold.id/harga-emas-hari-ini"

GOLD_WEIGHTS = {0.1, 0.25, 0.5, 1, 2, 3, 4, 5, 10, 25, 50, 100}

def _idr(x: str) -> int:
    if not x:
        return 0
    digits = re.sub(r"[^\d]", "", x)
    return int(digits) if digits else 0

def _gram(x: str) -> float:
    # "0.5 Gram" / "25.0 Gram" / kadang "0,5 Gram"
    s = (x or "").replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else 0.0

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()

def _find_last_update(text: str) -> str | None:
    m = re.search(
        r"Last\s*Update\s*:\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}\s+[0-9]{2}:[0-9]{2})",
        text
    )
    return m.group(1).strip() if m else None

def _table_rows(table) -> list[list[str]]:
    out = []
    for tr in table.find_all("tr"):
        cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
        if cells:
            out.append(cells)
    return out

def _is_gold_weights(ws: list[float]) -> bool:
    # valid jika semua berat yang non-zero berada dalam himpunan pecahan emas
    valid = [w for w in ws if w > 0]
    if not valid:
        return False
    # kalau ada 500 dst -> bukan emas
    if any(w > 150 for w in valid):
        return False
    return all((w in GOLD_WEIGHTS) for w in valid)

def parse_indogold(html: str):
    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text(" ", strip=True)
    last_update = _find_last_update(full_text)

    rows_out = []

    tables = soup.find_all("table")
    for t in tables:
        rows = _table_rows(t)
        if len(rows) < 2:
            continue

        header = rows[0]
        h = [_norm(x) for x in header]
        htxt = " | ".join(h)

        # ambil weights dulu buat filter emas/perak
        tmp_weights = []
        for r in rows[1:]:
            if len(r) >= 1:
                tmp_weights.append(_gram(r[0]))
        if not _is_gold_weights(tmp_weights):
            # skip tabel non-emas (biasanya perak / tabel lain)
            continue

        # =========================
        # A) Perbandingan: Pecahan | UBS | Harga Beli | Antam | Harga Beli
        # =========================
        if ("pecahan" in htxt and "ubs" in htxt and "antam" in htxt and "harga beli" in htxt and "buyback" not in htxt):
            # cari 2 kolom "Harga Beli"
            buy_cols = [i for i, col in enumerate(h) if "harga beli" in col]
            if len(buy_cols) >= 2:
                ubs_buy_idx, antam_buy_idx = buy_cols[0], buy_cols[1]
                for r in rows[1:]:
                    if len(r) <= max(ubs_buy_idx, antam_buy_idx):
                        continue
                    w = _gram(r[0])
                    ubs_buy = _idr(r[ubs_buy_idx])
                    antam_buy = _idr(r[antam_buy_idx])
                    if w in GOLD_WEIGHTS:
                        if ubs_buy:
                            rows_out.append({"vendor": "Perbandingan - UBS", "weight_g": w, "sell_idr": ubs_buy, "buyback_idr": 0})
                        if antam_buy:
                            rows_out.append({"vendor": "Perbandingan - Antam", "weight_g": w, "sell_idr": antam_buy, "buyback_idr": 0})
            continue

        # =========================
        # B) UBS: Pecahan | Harga Beli | Harga Jual (Buyback)  (3 kolom)
        # =========================
        if ("pecahan" in htxt and "harga beli" in htxt and "buyback" in htxt and len(header) == 3):
            # karena sudah lolos filter GOLD_WEIGHTS, ini kita anggap UBS
            for r in rows[1:]:
                if len(r) < 3:
                    continue
                w = _gram(r[0])
                buy = _idr(r[1])
                bb = _idr(r[2])
                if w in GOLD_WEIGHTS and (buy or bb):
                    rows_out.append({"vendor": "UBS", "weight_g": w, "sell_idr": buy, "buyback_idr": bb})
            continue

        # =========================
        # C) Antam: multi-year (biasanya >= 4 kolom)
        # kolom: Pecahan | Harga Beli (2026) | Buyback 2026 | Buyback 2025 | Buyback 2024
        # =========================
        if ("pecahan" in htxt and "harga beli" in htxt and "buyback" in htxt and len(header) >= 4):
            for r in rows[1:]:
                if len(r) < 3:
                    continue
                w = _gram(r[0])
                buy_2026 = _idr(r[1])
                bb_2026 = _idr(r[2])
                if w in GOLD_WEIGHTS and (buy_2026 or bb_2026):
                    rows_out.append({"vendor": "Antam", "weight_g": w, "sell_idr": buy_2026, "buyback_idr": bb_2026})
            continue

    df = pd.DataFrame(rows_out)

    # =========================
    # DEDUP: vendor+weight ambil max (kalau ada duplikat)
    # =========================
    if not df.empty:
        df["weight_g"] = pd.to_numeric(df["weight_g"], errors="coerce").fillna(0.0)
        df["sell_idr"] = pd.to_numeric(df["sell_idr"], errors="coerce").fillna(0).astype(int)
        df["buyback_idr"] = pd.to_numeric(df["buyback_idr"], errors="coerce").fillna(0).astype(int)

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
    else:
        label = "IndoGold — Last Update: (tidak terbaca)"

    return df, label
