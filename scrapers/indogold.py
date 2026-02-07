# scrapers/indogold.py
import re
import pandas as pd
from bs4 import BeautifulSoup

URL_INDOGOLD = "https://www.indogold.id/harga-emas-hari-ini"

# Threshold untuk membedakan EMAS vs PERAK berdasarkan harga/gram.
# Emas ~ 2–4 juta/gram, perak jauh lebih kecil.
MIN_GOLD_IDR_PER_GRAM = 500_000


# =========================
# Helpers
# =========================
def _idr(x: str) -> int:
    """Parse 'Rp. 1.234.567' -> 1234567"""
    if not x:
        return 0
    digits = re.sub(r"[^\d]", "", x)
    return int(digits) if digits else 0


def _gram(x: str) -> float:
    """Parse '0.5 Gram' / '0,25 Gram' / '1.00 Gram' -> float gram"""
    s = (x or "").replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else 0.0


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _find_last_update(text: str) -> str | None:
    m = re.search(
        r"Last\s*Update\s*:\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}\s+[0-9]{2}:[0-9]{2})",
        text,
    )
    return m.group(1).strip() if m else None


def _table_rows(table) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cells = [
            re.sub(r"\s+", " ", c.get_text(" ", strip=True))
            for c in tr.find_all(["th", "td"])
        ]
        if cells:
            rows.append(cells)
    return rows


def _is_gold_table_by_ratio(sample_rows: list[tuple[float, int]]) -> bool:
    """
    sample_rows: list of (weight_g, sell_idr)
    Hitung median sell_idr/weight_g untuk membedakan emas vs perak.
    """
    ratios = []
    for w, sell in sample_rows:
        if w > 0 and sell > 0:
            ratios.append(sell / w)
    if len(ratios) < 2:
        return False
    ratios.sort()
    med = ratios[len(ratios) // 2]
    return med >= MIN_GOLD_IDR_PER_GRAM


# =========================
# Main Parser
# =========================
def parse_indogold(html: str):
    """
    Output kolom (sesuai app.py):
      - vendor
      - weight_g
      - sell_idr      (Harga Beli)
      - buyback_idr   (Harga Jual / Buyback)

    Vendor output (rapi):
      - "Perbandingan - UBS"
      - "Perbandingan - Antam"
      - "UBS"
      - "Antam"
    """
    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text(" ", strip=True)
    last_update = _find_last_update(full_text)

    rows_out: list[dict] = []

    for table in soup.find_all("table"):
        rows = _table_rows(table)
        if len(rows) < 2:
            continue

        header = rows[0]
        h = [_norm(x) for x in header]
        htxt = " | ".join(h)

        # kumpulkan sample rasio harga/gram dari baris tabel
        # - untuk tabel compare: harga jual/buyback tidak ada, tapi ada "harga beli" utk UBS & Antam
        # - untuk tabel UBS/Antam: ada harga beli jelas
        sample = []
        for r in rows[1:]:
            if len(r) < 2:
                continue
            w = _gram(r[0])
            # ambil harga dari kolom ke-2 sebagai proxy (biasanya "Harga Beli")
            sell_proxy = _idr(r[1])
            if w > 0 and sell_proxy > 0:
                sample.append((w, sell_proxy))
        # skip tabel non-emas (perak/yang lain)
        if not _is_gold_table_by_ratio(sample):
            continue

        # =========================
        # A) PERBANDINGAN
        # Pecahan | UBS | Harga Beli | Antam | Harga Beli
        # =========================
        if (
            "pecahan" in htxt
            and "ubs" in htxt
            and "antam" in htxt
            and "harga beli" in htxt
            and "buyback" not in htxt
        ):
            buy_cols = [i for i, col in enumerate(h) if "harga beli" in col]
            if len(buy_cols) >= 2:
                ubs_idx, antam_idx = buy_cols[0], buy_cols[1]
                for r in rows[1:]:
                    if len(r) <= max(ubs_idx, antam_idx):
                        continue
                    w = _gram(r[0])
                    if w <= 0:
                        continue

                    ubs_buy = _idr(r[ubs_idx])
                    antam_buy = _idr(r[antam_idx])

                    if ubs_buy:
                        rows_out.append({
                            "vendor": "Perbandingan - UBS",
                            "weight_g": w,
                            "sell_idr": ubs_buy,
                            "buyback_idr": 0,
                        })
                    if antam_buy:
                        rows_out.append({
                            "vendor": "Perbandingan - Antam",
                            "weight_g": w,
                            "sell_idr": antam_buy,
                            "buyback_idr": 0,
                        })
            continue

        # =========================
        # B) UBS
        # Pecahan | Harga Beli | Harga Jual (Buyback)
        # =========================
        if ("pecahan" in htxt and "harga beli" in htxt and "buyback" in htxt and len(header) == 3):
            for r in rows[1:]:
                if len(r) < 3:
                    continue
                w = _gram(r[0])
                if w <= 0:
                    continue
                buy = _idr(r[1])
                bb = _idr(r[2])
                if buy or bb:
                    rows_out.append({
                        "vendor": "UBS",
                        "weight_g": w,
                        "sell_idr": buy,
                        "buyback_idr": bb,
                    })
            continue

        # =========================
        # C) ANTAM (multi-year)
        # Pecahan | Harga Beli (2026) | Buyback 2026 | ...
        # =========================
        if ("pecahan" in htxt and "harga beli" in htxt and "buyback" in htxt and len(header) >= 4):
            for r in rows[1:]:
                if len(r) < 3:
                    continue
                w = _gram(r[0])
                if w <= 0:
                    continue
                buy_2026 = _idr(r[1])
                bb_2026 = _idr(r[2])
                if buy_2026 or bb_2026:
                    rows_out.append({
                        "vendor": "Antam",
                        "weight_g": w,
                        "sell_idr": buy_2026,
                        "buyback_idr": bb_2026,
                    })
            continue

    df = pd.DataFrame(rows_out)

    # =========================
    # DEDUP vendor+weight
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
