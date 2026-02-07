import os
import re
from io import BytesIO
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import pandas as pd

URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"


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
    # contoh: 07 February 2026
    m = re.search(r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b", text or "")
    return m.group(1).strip() if m else None


def _to_direct_download(url: str) -> str:
    """Make best-effort OneDrive URLs into direct download."""
    if not url:
        return url
    u = url.strip()

    if "1drv.ms" in u:
        if "download=1" not in u:
            u += ("&" if "?" in u else "?") + "download=1"
        return u

    if "onedrive.live.com" in u:
        parsed = urlparse(u)
        q = parse_qs(parsed.query)
        if "download" not in q:
            q["download"] = ["1"]
        new_q = urlencode(q, doseq=True)
        return urlunparse(parsed._replace(query=new_q))

    return u


def _find_candidate_excel_links(html: str) -> list[str]:
    """Scan HTML for any excel/onedrive/xlsx/download.aspx URLs."""
    if not html:
        return []

    urls = re.findall(r"https?://[^\s\"'>]+", html)

    cands = []
    for u in urls:
        ul = u.lower()
        if (
            ul.endswith(".xlsx")
            or "1drv.ms" in ul
            or "onedrive.live.com" in ul
            or "download.aspx?uniqueid=" in ul
        ):
            cands.append(u)

    # de-dup preserve order
    seen = set()
    out = []
    for u in cands:
        if u not in seen:
            out.append(u)
            seen.add(u)
    return out


def _download_bytes(url: str) -> tuple[bytes | None, str | None]:
    """
    Download content. Return (bytes, error_reason).
    Reject HTML login pages.
    """
    import requests

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    try:
        r = requests.get(url, headers=headers, timeout=45, allow_redirects=True)
    except Exception as e:
        return None, f"request error: {e}"

    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"

    ctype = (r.headers.get("content-type") or "").lower()
    head = (r.content[:400] or b"").lower()

    # if it returns HTML, likely login/blocked
    if "text/html" in ctype or b"<html" in head:
        return None, "returned HTML (login/blocked)"

    return r.content, None


def _parse_excel(content: bytes) -> tuple[pd.DataFrame, str]:
    """
    Parse XLSX and find table containing 'Berat' + 'Harga End User'.
    Standardize output: vendor, weight_g, sell_idr, buyback_idr
    """
    xls = pd.ExcelFile(BytesIO(content))

    best_raw = None
    best_sheet = None
    header_row = None

    for sh in xls.sheet_names:
        df_raw = pd.read_excel(xls, sheet_name=sh, header=None)
        # scan first N rows to find header row
        for i in range(min(len(df_raw), 250)):
            row_vals = df_raw.iloc[i].tolist()
            row_text = " ".join([str(x) for x in row_vals if pd.notna(x)]).lower()
            if ("berat" in row_text) and ("harga end user" in row_text or "harga end-user" in row_text):
                best_raw = df_raw
                best_sheet = sh
                header_row = i
                break
        if best_raw is not None:
            break

    if best_raw is None:
        return (
            pd.DataFrame(columns=["vendor", "weight_g", "sell_idr", "buyback_idr"]),
            "HK Logam Mulia — XLSX format tidak dikenali",
        )

    headers = [
        str(x).strip().lower() if pd.notna(x) else ""
        for x in best_raw.iloc[header_row].tolist()
    ]

    def find_col(*keys: str) -> int | None:
        for idx, h in enumerate(headers):
            if not h:
                continue
            if all(k in h for k in keys):
                return idx
        return None

    c_berat = find_col("berat")
    # kolom yang paling aman: "Harga End User" (total)
    c_sell = None
    for key in ["harga end user", "harga end-user"]:
        for idx, h in enumerate(headers):
            if key in h:
                c_sell = idx
                break
        if c_sell is not None:
            break

    if c_berat is None or c_sell is None:
        return (
            pd.DataFrame(columns=["vendor", "weight_g", "sell_idr", "buyback_idr"]),
            "HK Logam Mulia — XLSX header tidak lengkap",
        )

    data = best_raw.iloc[header_row + 1 :].copy()

    rows = []
    for _, r in data.iterrows():
        w = _float(r.iloc[c_berat])
        sell = _idr(r.iloc[c_sell])
        if w <= 0 or sell <= 0:
            continue
        rows.append(
            {
                "vendor": "HK Logam Mulia",
                "weight_g": float(w),
                "sell_idr": int(sell),
                "buyback_idr": 0,
            }
        )

    out = pd.DataFrame(rows)

    # Try to find "Buyback ... Rp ... /gram" anywhere in sheet text
    buyback_per_gram = 0
    flat_text = " ".join(
        best_raw.fillna("").astype(str).values.flatten().tolist()
    )
    m = re.search(r"buyback.*?rp\s*([0-9\.,]+)\s*/\s*gram", flat_text, flags=re.I | re.S)
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
    Priority:
    1) Use env/secrets: HAKABEGOLD_DOWNLOAD_URL (tempauth downloadUrl)
    2) Else try to find any xlsx / onedrive link inside HTML
    """
    # 1) Use direct downloadUrl from env (best)
    dl_env = os.getenv("HAKABEGOLD_DOWNLOAD_URL", "").strip()

    text_only = re.sub(r"<[^>]+>", " ", html or "")
    date_str = _extract_date(text_only)

    if dl_env:
        content, err = _download_bytes(dl_env)
        if content:
            df, label = _parse_excel(content)
            if date_str:
                label = f"HK Logam Mulia — {date_str} — {label}"
            return df, label
        # env exists but failed
        label = f"HK Logam Mulia — downloadUrl env gagal ({err})"
        if date_str:
            label = f"HK Logam Mulia — {date_str} — downloadUrl env gagal ({err})"
        return pd.DataFrame(columns=["vendor", "weight_g", "sell_idr", "buyback_idr"]), label

    # 2) fallback: scan html
    links = _find_candidate_excel_links(html or "")
    for u in links:
        dl = _to_direct_download(u)
        content, err = _download_bytes(dl)
        if content:
            df, label = _parse_excel(content)
            if date_str:
                label = f"HK Logam Mulia — {date_str} — {label}"
            return df, label

    label = "HK Logam Mulia — XLSX tidak ditemukan di HTML (butuh HAKABEGOLD_DOWNLOAD_URL)"
    if date_str:
        label = f"HK Logam Mulia — {date_str} — XLSX tidak ditemukan di HTML (butuh HAKABEGOLD_DOWNLOAD_URL)"
    return pd.DataFrame(columns=["vendor", "weight_g", "sell_idr", "buyback_idr"]), label
