# scrapers/hakabegold.py
from __future__ import annotations

import re
from io import BytesIO
from typing import Tuple, Optional
from urllib.parse import urlparse, parse_qs, unquote

import pandas as pd
import requests


URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"

# Pakai link 1drv.ms terbaru kamu
HAKABEGOLD_SHARE_URL = "https://1drv.ms/x/c/7181a7df3eab3581/IQAdDl52fuvfQqpHMQUXarpPAQjSrmRAdGBYh6zQE5QIlF8?e=HhTNvT"


# =========================
# Helpers
# =========================

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    return s


def _is_html_response(r: requests.Response) -> bool:
    ctype = (r.headers.get("content-type") or "").lower()
    if "text/html" in ctype:
        return True
    head = (r.content or b"")[:2000].lower()
    return b"<html" in head or b"<!doctype html" in head


def _idr_to_int(val) -> int:
    if val is None:
        return 0
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits else 0


def _to_float(val) -> float:
    if val is None:
        return 0.0
    s = str(val).strip().replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def _extract_resid_authkey_from_url(u: str) -> tuple[Optional[str], Optional[str]]:
    qs = parse_qs(urlparse(u).query)
    resid = (qs.get("resid") or [None])[0]
    authkey = (qs.get("authkey") or [None])[0]
    return resid, authkey


def _build_public_download(resid: str, authkey: str) -> str:
    # ini endpoint download publik paling “stabil”
    return f"https://onedrive.live.com/download?resid={resid}&authkey={authkey}"


def _find_download_link_in_html(html: str) -> Optional[str]:
    """
    Cari link download yang disisipkan di HTML/JS.
    Pola yang umum:
      - https://onedrive.live.com/download?resid=...&authkey=...
      - https://onedrive.live.com/download.aspx?... (kadang)
      - string ber-escape seperti https:\/\/onedrive.live.com\/download?resid=...
    """
    if not html:
        return None

    # unescape minimal
    h = html.replace("\\u0026", "&")
    h = h.replace("\\/", "/")

    # 1) langsung cari download?resid=...&authkey=...
    m = re.search(r"(https://onedrive\.live\.com/download\?resid=[A-Za-z0-9!]+&authkey=[A-Za-z0-9\-_]+)", h)
    if m:
        return m.group(1)

    # 2) cari resid & authkey di dalam HTML (JS config)
    m_resid = re.search(r"resid=([A-Za-z0-9!]+)", h)
    m_auth = re.search(r"authkey=([A-Za-z0-9\-_]+)", h)
    if m_resid and m_auth:
        return _build_public_download(m_resid.group(1), m_auth.group(1))

    # 3) kadang ada download.aspx?UniqueId=...&tempauth=...
    m2 = re.search(r"(https://my\.microsoftpersonalcontent\.com/[^\"'\s]+download\.aspx\?[^\"'\s]+)", h)
    if m2:
        return m2.group(1)

    return None


def _download_xlsx_from_share(share_url: str) -> bytes:
    s = _session()

    # Step A: resolve redirect chain (browser-like)
    r = s.get(share_url, timeout=60, allow_redirects=True, headers={"Referer": "https://onedrive.live.com/"})
    r.raise_for_status()

    # Kalau sudah langsung file -> OK
    if not _is_html_response(r):
        return r.content

    final_url = r.url

    # Step B: coba pakai resid/authkey dari URL final
    resid, authkey = _extract_resid_authkey_from_url(final_url)
    if resid and authkey:
        dl = _build_public_download(resid, authkey)
        r2 = s.get(dl, timeout=60, allow_redirects=True, headers={"Referer": "https://onedrive.live.com/"})
        r2.raise_for_status()
        if not _is_html_response(r2):
            return r2.content

    # Step C: ekstrak download link dari HTML viewer
    dl2 = _find_download_link_in_html(r.text or "")
    if dl2:
        r3 = s.get(dl2, timeout=60, allow_redirects=True, headers={"Referer": "https://onedrive.live.com/"})
        r3.raise_for_status()
        if not _is_html_response(r3):
            return r3.content

    # Step D (last resort): add download=1 ke final_url
    joiner = "&" if "?" in final_url else "?"
    r4 = s.get(final_url + joiner + "download=1", timeout=60, allow_redirects=True,
              headers={"Referer": "https://onedrive.live.com/"})
    r4.raise_for_status()
    if not _is_html_response(r4):
        return r4.content

    raise RuntimeError("OneDrive masih mengembalikan HTML (bukan XLSX). Link share kemungkinan tidak benar-benar public untuk server Streamlit / diblok anti-bot.")


def _extract_date_from_raw(df: pd.DataFrame) -> Optional[str]:
    pat = re.compile(r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b")
    for v in df.astype(str).fillna("").values.ravel():
        m = pat.search(v)
        if m:
            return m.group(1)
    return None


def _ explain_buyback_per_gram(df: pd.DataFrame) -> int:
    text = " ".join(df.astype(str).fillna("").values.ravel())
    m = re.search(r"Buyback.*?Rp\.?\s*([\d\.,]+)\s*/?\s*gram", text, flags=re.I)
    return _idr_to_int(m.group(1)) if m else 0


# =========================
# Main parser
# =========================

def parse_hakabegold(_: str = "") -> Tuple[pd.DataFrame, str]:
    xlsx_bytes = _download_xlsx_from_share(HAKABEGOLD_SHARE_URL)
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
            if col_sell is None and "harga end user" in cl:
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
    buyback_per_gram = _explain_buyback_per_gram(raw_df_for_meta)

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
