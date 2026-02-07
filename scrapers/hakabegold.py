# scrapers/hakabegold.py
import re
from io import BytesIO
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import pandas as pd

URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"  # untuk caption UI


def _idr(text: str) -> int:
    if not text:
        return 0
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else 0


def _float(x) -> float:
    if x is None:
        return 0.0
    s = str(x).strip().replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else 0.0


def _extract_date(text: str) -> str | None:
    m = re.search(r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b", text or "")
    return m.group(1) if m else None


def _to_direct_download(url: str) -> str:
    """
    Convert common OneDrive share URLs into direct download attempts.
    Works only if the file is publicly accessible.
    """
    if not url:
        return url

    u = url.strip()

    # 1drv.ms short share links: append download=1
    if "1drv.ms" in u:
        if "download=1" not in u:
            sep = "&" if "?" in u else "?"
            u = f"{u}{sep}download=1"
        return u

    # onedrive.live.com: ensure download=1
    if "onedrive.live.com" in u:
        parsed = urlparse(u)
        q = parse_qs(parsed.query)
        if "download" not in q:
            q["download"] = ["1"]
        new_q = urlencode(q, doseq=True)
        return urlunparse(parsed._replace(query=new_q))

    # raw xlsx link: keep
    return u


def _find_candidate_excel_links(html: str) -> list[str]:
    """
    Scan HTML for any onedrive/1drv/ms/xlsx URL.
    """
    if not html:
        return []

    # include urls inside quotes or plain
    urls = re.findall(r"https?://[^\s\"'>]+", html)

    cands = []
    for u in urls:
        ul = u.lower()
        if any(k in ul for k in ["1drv.ms", "onedrive.live.com"]) or ul.endswith(".xlsx"):
            cands.append(u)

    # de-dup preserve order
    seen = set()
    out = []
    for u in cands:
        if u not in seen:
            out.append(u)
            seen.add(u)
    return out


def _download_bytes(session, url: str) -> bytes | None:
    """
    Try download bytes; return None if blocked.
    """
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    r = session.get(url, headers=headers, timeout=30, allow_redirects=True)
    if r.status_code != 200:
        return None

    ctype = (r.headers.get("content-type") or "").lower()
    # sometimes OneDrive returns html login page; reject
    if "text/html" in ctype and b"<html" in (r.content[:200].lower()):
        return None

    return r.content


def _parse_excel(content: bytes):
    """
    Parse XLSX bytes. Find table row containing header 'Berat' & 'Harga End User'.
    Return standardized df (vendor, weight_g, sell_idr, buyback_idr).
    """
    xls = pd.ExcelFile(BytesIO(content))
    # read all sheets as raw (header=None)
    best = None
    best_sheet = None

    for sh in xls.sheet_names:
        df_raw = pd.read_excel(xls, sheet_name=sh, header=None, dtype=str)
        # find row index containing 'Berat' and 'Harga End User'
        for i in range(min(len(df_raw), 200)):  # limit scan
            row = " ".join([str(x) for x in df_raw.iloc[i].tolist() if x and str(x) != "nan"]).lower()
            if "berat" in row and "harga end user" in row:
                best = df_raw
                best_sheet = sh
                header_row = i
                break
        if best is not None:
            break

    if best is None:
        return pd.DataFrame(columns=["vendor", "weight_g", "sell_idr", "buyback_idr"]), "HK Logam Mulia — XLSX ditemukan tapi format tidak dikenali"

    # map columns by header row cell text
    headers = [str(x).strip().lower() if x and str(x) != "nan" else "" for x in best.iloc[header_row].tolist()]

    def col_idx(keyword: str) -> int | None:
        for idx, h in enumerate(headers):
            if keyword in h:
                return idx
        return None

    c_berat = col_idx("berat")
    c_end_user = col_idx("harga end user")
    c_buyback = None  # buyback biasanya di bawah tabel, bukan kolom

    # data starts after header_row
    data = best.iloc[header_row + 1:].copy()
    rows = []

    for _, r in data.iterrows():
        if c_berat is None or c_end_user is None:
            continue

        w = _float(r.iloc[c_berat])
        sell = _idr(r.iloc[c_end_user])

        if w <= 0 or sell <= 0:
            continue

        rows.append({"vendor": "HK Logam Mulia", "weight_g": w, "sell_idr": sell, "buyback_idr": 0})

    out = pd.DataFrame(rows)

    # try to find buyback per gram from anywhere in sheet text
    buyback_per_gram = 0
    flat_text = " ".join(best.fillna("").astype(str).values.flatten().tolist())
    m = re.search(r"buyback.*?rp\s*([0-9\.,]+)\s*/\s*gram", flat_text, flags=re.I)
    if m:
        buyback_per_gram = _idr(m.group(1))

    if not out.empty and buyback_per_gram > 0:
        out["buyback_idr"] = (out["weight_g"] * buyback_per_gram).round().astype(int)

    if not out.empty:
        out = out.sort_values(["vendor", "weight_g"]).reset_index(drop=True)

    label = f"HK Logam Mulia — XLSX({best_sheet})"
    if buyback_per_gram > 0:
        label += f" — Buyback/gr: Rp{buyback_per_gram:,}".replace(",", ".")
    return out, label


def parse_hakabegold(html: str):
    """
    Primary strategy:
    - Find public Excel link in HTML (1drv/onedrive)
    - Download xlsx (must be public)
    - Parse xlsx into standardized df
    """
    import requests

    text = re.sub(r"<[^>]+>", " ", html or "")
    date_str = _extract_date(text)

    session = requests.Session()
    links = _find_candidate_excel_links(html or "")
    # try each link in order
    for u in links:
        dl = _to_direct_download(u)
        content = _download_bytes(session, dl)
        if content:
            df, label = _parse_excel(content)
            if date_str:
                label = f"HK Logam Mulia — {date_str} — {label}"
            return df, label

    # if no links or cannot download -> empty with clear reason
    label = "HK Logam Mulia — XLSX tidak bisa diunduh (butuh link publik)"
    if date_str:
        label = f"HK Logam Mulia — {date_str} — XLSX tidak bisa diunduh (butuh link publik)"
    return pd.DataFrame(columns=["vendor", "weight_g", "sell_idr", "buyback_idr"]), label
