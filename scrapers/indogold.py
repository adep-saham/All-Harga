import re
import pandas as pd
from bs4 import BeautifulSoup

URL_INDOGOLD = "https://www.indogold.id/harga-emas-hari-ini"

def _idr(x: str) -> int:
    if not x:
        return 0
    digits = re.sub(r"[^\d]", "", x)
    return int(digits) if digits else 0

def _gram(x: str) -> float:
    # contoh: "0.5 Gram" / "25.0 Gram"
    m = re.search(r"(\d+(?:\.\d+)?)", x.replace(",", "."))
    return float(m.group(1)) if m else 0.0

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()

def _find_last_update(all_text: str) -> str | None:
    # "Last Update : 07 February 2026 12:28"
    m = re.search(r"Last\s*Update\s*:\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}\s+[0-9]{2}:[0-9]{2})", all_text)
    return m.group(1).strip() if m else None

def _table_to_rows(table) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    return rows

def parse_indogold(html: str):
    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text(" ", strip=True)
    last_update = _find_last_update(full_text)

    rows_out = []

    # ambil semua tabel
    tables = soup.find_all("table")
    for t in tables:
        rows = _table_to_rows(t)
        if len(rows) < 2:
            continue

        header = rows[0]
        htxt = " | ".join([_norm(x) for x in header])

        # =========================
        # 1) Tabel Perbandingan (UBS vs Antam) - hanya Harga Beli
        # header umumnya memuat: pecahan, ubs, harga beli, antam, harga beli
        # =========================
        if ("pecahan" in htxt and "ubs" in htxt and "antam" in htxt and "harga beli" in htxt and "buyback" not in htxt):
            # cari kolom UBS dan Antam harga beli
            # format kolom bisa: Pecahan | UBS | Harga Beli | Antam | Harga Beli
            # atau ada variasi spasi; kita locate index berbasis keyword.
            idx_pecahan = 0

            # cari kolom angka harga beli ubs & antam
            # fallback posisi: 2 untuk UBS buy, 4 untuk Antam buy
            # tapi kita tetap buat robust:
            ubs_buy_idx = None
            antam_buy_idx = None
            for i, col in enumerate(header):
                c = _norm(col)
                # biasanya kolom "Harga Beli" muncul dua kali, kita assign berurutan
                if "harga beli" in c:
                    if ubs_buy_idx is None:
                        ubs_buy_idx = i
                    elif antam_buy_idx is None:
                        antam_buy_idx = i

            # kalau tidak ketemu, skip
            if ubs_buy_idx is None or antam_buy_idx is None:
                continue

            for r in rows[1:]:
                if len(r) <= max(antam_buy_idx, ubs_buy_idx):
                    continue
                pecahan = r[idx_pecahan]
                w = _gram(pecahan)
                ubs_buy = _idr(r[ubs_buy_idx])
                antam_buy = _idr(r[antam_buy_idx])

                if w > 0 and (ubs_buy or antam_buy):
                    if ubs_buy:
                        rows_out.append({
                            "vendor": "UBS (Perbandingan)",
                            "weight_g": w,
                            "sell_idr": ubs_buy,
                            "buyback_idr": 0,
                        })
                    if antam_buy:
                        rows_out.append({
                            "vendor": "Antam (Perbandingan)",
                            "weight_g": w,
                            "sell_idr": antam_buy,
                            "buyback_idr": 0,
                        })
            continue

        # =========================
        # 2) Tabel UBS (Harga Beli + Harga Jual/Buyback) - 3 kolom
        # header: Pecahan | Harga Beli | Harga Jual (Buyback)
        # Ciri UBS: sering ada pecahan 0.1 / 0.25
        # =========================
        if ("pecahan" in htxt and "harga beli" in htxt and "buyback" in htxt and len(header) == 3):
            # parse semua row
            tmp = []
            for r in rows[1:]:
                if len(r) < 3:
                    continue
                w = _gram(r[0])
                buy = _idr(r[1])
                bb = _idr(r[2])
                if w > 0 and (buy or bb):
                    tmp.append((w, buy, bb))

            # identifikasi ini UBS atau bukan lewat pecahan kecil
            weights = [x[0] for x in tmp]
            is_ubs = any(abs(w - 0.1) < 1e-9 or abs(w - 0.25) < 1e-9 for w in weights)

            vendor_name = "UBS" if is_ubs else "IndoGold (Tabel 3 kolom)"
            for w, buy, bb in tmp:
                rows_out.append({
                    "vendor": vendor_name,
                    "weight_g": w,
                    "sell_idr": buy,
                    "buyback_idr": bb,
                })
            continue

        # =========================
        # 3) Tabel Antam multi-year (Buyback 2026/2025/2024)
        # biasanya kolom: Pecahan | Harga Beli | Harga Jual (Buyback) | Harga Jual (Buyback) | Harga Jual (Buyback)
        # kita pakai Buyback 2026 sebagai buyback_idr
        # =========================
        if ("pecahan" in htxt and "tahun 2026" in full_text.lower() and len(header) >= 4 and "harga beli" in htxt and "buyback" in htxt):
            # heuristik: kolom 0 pecahan, kolom 1 harga beli (2026), kolom 2 buyback 2026
            for r in rows[1:]:
                if len(r) < 3:
                    continue
                w = _gram(r[0])
                buy_2026 = _idr(r[1])
                bb_2026 = _idr(r[2])
                if w > 0 and (buy_2026 or bb_2026):
                    rows_out.append({
                        "vendor": "Antam",
                        "weight_g": w,
                        "sell_idr": buy_2026,
                        "buyback_idr": bb_2026,
                    })
            continue

    df = pd.DataFrame(rows_out)

    # =========================
    # DEDUP: buang double (vendor+weight)
    # ambil nilai sell/buyback terbesar (aman kalau ada duplikat identik)
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
