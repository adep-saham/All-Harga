# scrapers/hakabegold.py
from __future__ import annotations

import re
from io import BytesIO
from typing import Tuple, Optional
from urllib.parse import urlparse, parse_qs

import pandas as pd
import requests


# =========================
# KONFIGURASI
# =========================

URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"

# OneDrive SHARE LINK (yang kamu kasih)
HAKABEGOLD_SHARE_URL = "https://1drv.ms/x/c/7181a7df3eab3581/IQAdDl52fuvfQqpHMQUXarpPAQjSrmRAdGBYh6zQE5QIlF8?e=HhTNvT"


# =========================
# UTIL
# =========================

def _idr_to_int(val) -> int:
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


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    return s


def _resolve_onedrive_direct_download(share_url: str) -> str:
    """
    Resolve 1drv.ms -> onedrive doc.aspx -> build stable public download:
      https://onedrive.live.com/download?resid=...&authkey=...
    """
    s = _session()

    # Step 1: follow redirects to get final URL
    r = s.get(share_url, timeout=60, allow_redirects=True)
    r.raise_for_status()
    final_url = r.url  # biasanya doc.aspx?resid=...&authkey=...

    # Step 2: parse resid/authkey
    qs = parse_qs(urlparse(final_url).query)
    resid = (qs.get("resid") or [None])[0]
    authkey = (qs.get("authkey") or [None])[0]

    if resid and authkey:
        return f"https://onedrive.live.com/download?resid={resid}&authkey={authkey}"

    # Fallback A: kadang ada di HTML meta/JS
    html = r.text or ""
    m_resid = re.search(r"resid=([A-Za-z0-9!]+)", html)
    m_auth = re.search(r"authkey=([A-Za-z0-9\-_]+)", html)
    if m_resid and m_auth:
        resid2 = m_resid.group(1)
        auth2 = m_auth.group(1)
        return f"https://onedrive.live.com/download?resid={resid2}&authkey={auth2}"

    # Fallback B: pakai trik download=1 (lebih sering kena 403, tapi jadi last resort)
    joiner = "&" if "?" in final_url else "?"
    return final_url + joiner + "download=1"


def _download_xlsx(share_url: str) -> bytes:
    s = _session()

    dl = _resolve_onedrive_direct_download(share_url)

    # Add Referer supaya lebih “browser-like”
    headers = {"Referer": "https://onedrive.live.com/"}
    r = s.get(dl, headers=headers, timeout=60, allow_redirects=True)

    # kalau 403, coba ulang dengan Accept yang lebih spesifik
    if r.status_code == 403:
        headers2 = {
            "Referer": "https://onedrive.live.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        r = s.get(dl, headers=headers2, timeout=60, allow_redirects=True)

    r.raise_for_status()

    # Guard: jangan sampai HTML viewer
    ctype = (r.headers.get("content-type") or "").lower()
    if ("text/html" in ctype) or (b"<html" in r.content[:2000].lower()):
        raise RuntimeError("OneDrive mengembalikan HTML (bukan XLSX). Link share kemungkinan bukan public-downloadable.")

    return r.content


def _extract_date_from_raw(df: pd.DataFrame) -> Optional[str]:
    pat = re.compile(r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b")
    for v in df.astype(str).fillna("").values.ravel():
        m = pat.search(v)
        if m:
            return m.group(1)
    return None


def _extract_buyback_per_gram(df: pd.DataFrame) -> int:
    text = " ".join(df.astype(str).fillna("").values.ravel())
    m = re.search(r"Buyback.*?Rp\.?\s*([\d\.,]+)\s*/?\s*gram", text, flags=re.I)
    return _idr_to_int(m.group(1)) if m else 0


# =========================
# MAIN PARSER
# =========================

def parse_hakabegold(_: str = "") -> Tuple[pd.DataFrame, str]:
    """
    Return df columns:
      vendor, weight_g, sell_idr, buyback_idr
    """
    xlsx_bytes = _download_xlsx(HAKABEGOLD_SHARE_URL)

    xls = pd.ExcelFile(BytesIO(xlsx_bytes))

    data_df = None
    raw_df_for_meta = None

    for sheet in xls.sheet_names:
        try:
            raw = pd.read_excel(xls, sheet_name=sheet, header=None)
        except Exception:
            continue

        header_idx = None
        for i in range(min(80, len(raw))):
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
            # paling “aman” ambil Harga End User (harga beli end-user)
            if col_sell is None and ("harga end user" in cl):
                col_sell = c

        if not col_weight or not col_sell:
            continue

        tmp = df[[col_weight, col_sell]].copy()
        tmp = tmp.rename(columns={col_weight: "weight_g", col_sell: "sell_raw"})

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

    tanggal = _extract_date_from_raw(raw_df_for_meta)
    buyback_per_gram = _extract_buyback_per_gram(raw_df_for_meta)

    if buyback_per_gram > 0:
        data_df["buyback_idr"] = (data_df["weight_g"] * buyback_per_gram).round().astype(int)
    else:
        data_df["buyback_idr"] = 0

    out = pd.DataFrame({
        "vendor": "HK Logam Mulia",
        "weight_g": data_df["weight_g"],
        "sell_idr": data_df["sell_idr"],
        "buyback_idr": data_df["buyback_idr"],
    }).sort_values("weight_g").reset_index(drop=True)

    label = "HK Logam Mulia"
    if tanggal:
        label += f" — {tanggal}"
    if buyback_per_gram:
        label += f" — Buyback/gr: Rp{buyback_per_gram:,}".replace(",", ".")

    return out, label
