# scrapers/hakabegold.py
from __future__ import annotations

import re
from io import BytesIO
from typing import Tuple, Optional

import pandas as pd
import requests


# =========================
# KONFIGURASI
# =========================

# URL halaman (hanya untuk caption / referensi)
URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"

# OneDrive SHARE LINK (bukan content.downloadUrl yang cepat expired)
# Bisa ditaruh langsung di sini atau via Streamlit Secrets
HAKABEGOLD_SHARE_URL = "https://1drv.ms/x/c/7181a7df3eab3581/IQAdDl52fuvfQqpHMQUXarpPAQjSrmRAdGBYh6zQE5QIlF8?e=HhTNvT"


# =========================
# UTIL
# =========================

def _idr_to_int(val) -> int:
    """Rp1.473.000 / Rp. 1,473,000 / 1473000 -> 1473000"""
    if val is None:
        return 0
    s = str(val)
    digits = re.sub(r"[^\d]", "", s)
    return int(digits) if digits else 0


def _to_float(val) -> float:
    if val is None:
        return 0.0
    s = str(val).strip().replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def _download_xlsx_from_onedrive(share_url: str) -> bytes:
    """
    Download XLSX dari OneDrive share link.
    Tambahkan download=1 supaya tidak dapat HTML viewer.
    """
    if "download=1" not in share_url:
        url = share_url + ("&download=1" if "?" in share_url else "?download=1")
    else:
        url = share_url

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    r = requests.get(url, headers=headers, timeout=60, allow_redirects=True)
    r.raise_for_status()

    # Guard: jangan sampai HTML
    ctype = (r.headers.get("content-type") or "").lower()
    if "text/html" in ctype and b"<html" in r.content[:2000].lower():
        raise RuntimeError("OneDrive mengembalikan HTML, bukan file XLSX")

    return r.content


def _extract_date_from_raw(df: pd.DataFrame) -> Optional[str]:
    """
    Cari tanggal seperti '07 February 2026' di seluruh sheet
    """
    pat = re.compile(r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b")
    for v in df.astype(str).fillna("").values.ravel():
        m = pat.search(v)
        if m:
            return m.group(1)
    return None


def _extract_buyback_per_gram(df: pd.DataFrame) -> int:
    """
    Cari teks: 'Buyback Emas Batangan Rp 2,650,000 /gram'
    """
    text = " ".join(df.astype(str).fillna("").values.ravel())
    m = re.search(
        r"Buyback.*?Rp\.?\s*([\d\.,]+)\s*/?\s*gram",
        text,
        flags=re.I
    )
    if m:
        return _idr_to_int(m.group(1))
    return 0


# =========================
# MAIN PARSER
# =========================

def parse_hakabegold(_: str = "") -> Tuple[pd.DataFrame, str]:
    """
    Return:
      df columns:
        - vendor
        - weight_g
        - sell_idr
        - buyback_idr
      update_label: str
    """

    # 1. Download XLSX
    xlsx_bytes = _download_xlsx_from_onedrive(HAKABEGOLD_SHARE_URL)

    # 2. Load workbook
    xls = pd.ExcelFile(BytesIO(xlsx_bytes))

    data_df = None
    raw_df_for_meta = None

    # 3. Cari sheet yang mengandung tabel harga
    for sheet in xls.sheet_names:
        try:
            raw = pd.read_excel(xls, sheet_name=sheet, header=None)
        except Exception:
            continue

        # Cari baris header
        header_idx = None
        for i in range(min(50, len(raw))):
            row = " ".join(raw.iloc[i].astype(str).fillna("").tolist()).lower()
            if "berat" in row and "harga" in row:
                header_idx = i
                break

        if header_idx is None:
            continue

        df = pd.read_excel(xls, sheet_name=sheet, header=header_idx)
        df.columns = [str(c).strip() for c in df.columns]

        col_weight = None
        col_sell = None

        for c in df.columns:
            cl = c.lower()
            if col_weight is None and "berat" in cl:
                col_weight = c
            if col_sell is None and "harga end user" in cl:
                col_sell = c

        if not col_weight or not col_sell:
            continue

        tmp = df[[col_weight, col_sell]].copy()
        tmp = tmp.rename(columns={
            col_weight: "weight_g",
            col_sell: "sell_raw"
        })

        tmp["weight_g"] = tmp["weight_g"].apply(_to_float)
        tmp["sell_idr"] = tmp["sell_raw"].apply(_idr_to_int)

        tmp = tmp[(tmp["weight_g"] > 0) & (tmp["sell_idr"] > 0)]

        if tmp.empty:
            continue

        data_df = tmp[["weight_g", "sell_idr"]].copy()
        raw_df_for_meta = raw
        break

    if data_df is None:
        return (
            pd.DataFrame(columns=["vendor", "weight_g", "sell_idr", "buyback_idr"]),
            "HK Logam Mulia — tabel tidak ditemukan"
        )

    # 4. Metadata
    tanggal = _extract_date_from_raw(raw_df_for_meta)
    buyback_per_gram = _extract_buyback_per_gram(raw_df_for_meta)

    # 5. Hitung buyback per pecahan
    if buyback_per_gram > 0:
        data_df["buyback_idr"] = (
            data_df["weight_g"] * buyback_per_gram
        ).round().astype(int)
    else:
        data_df["buyback_idr"] = 0

    # 6. Final dataframe
    out = pd.DataFrame({
        "vendor": "HK Logam Mulia",
        "weight_g": data_df["weight_g"],
        "sell_idr": data_df["sell_idr"],
        "buyback_idr": data_df["buyback_idr"],
    }).sort_values("weight_g").reset_index(drop=True)

    # 7. Label
    label = "HK Logam Mulia"
    if tanggal:
        label += f" — {tanggal}"
    if buyback_per_gram:
        label += f" — Buyback/gr: Rp{buyback_per_gram:,}".replace(",", ".")

    return out, label
