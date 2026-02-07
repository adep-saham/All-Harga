# scrapers/hakabegold.py
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Tuple, Optional

import pandas as pd
import requests

URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"


# -------------------------
# Result container (optional, biar rapi)
# -------------------------
@dataclass
class HakabeResult:
    df: pd.DataFrame
    asof_label: str
    buyback_per_gram: int
    iframe_url: str
    download_url: str


def _headers() -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/144.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def _extract_iframe_src(home_html: str) -> str:
    """
    Ambil src iframe OneDrive dari HTML halaman logammuliahk.com.
    """
    # cari <iframe ... src='...1drv.ms...' ...>
    m = re.search(r"<iframe[^>]+src=['\"]([^'\"]+)['\"]", home_html, flags=re.I)
    if not m:
        raise RuntimeError("Tidak menemukan <iframe src='...'> di HTML halaman HK.")

    src = m.group(1).strip()

    # kadang HTML encode &amp;
    src = src.replace("&amp;", "&")

    if "1drv.ms" not in src and "onedrive.live.com" not in src:
        raise RuntimeError(f"Iframe src bukan OneDrive: {src[:120]}...")

    return src


def _make_download_url(resolved_url: str) -> str:
    """
    Jadikan URL yang sudah redirect (biasanya onedrive.live.com) menjadi link download.
    """
    # kalau sudah ada download=1 biarin
    if "download=1" in resolved_url:
        return resolved_url

    joiner = "&" if "?" in resolved_url else "?"
    return resolved_url + joiner + "download=1"


def _download_xlsx_from_iframe(iframe_url: str) -> Tuple[bytes, str]:
    """
    Request iframe URL -> ikuti redirect -> bentuk download url -> download bytes XLSX.
    Return: (xlsx_bytes, download_url_used)
    """
    s = requests.Session()

    # Step 1: resolve redirect
    r = s.get(iframe_url, headers=_headers(), timeout=30, allow_redirects=True)
    r.raise_for_status()
    resolved = r.url  # final URL after redirects

    # Step 2: build download url
    dl = _make_download_url(resolved)

    # Step 3: download
    r2 = s.get(dl, headers=_headers(), timeout=60, allow_redirects=True)
    r2.raise_for_status()

    content = r2.content

    # Validasi XLSX itu zip => start with 'PK'
    if len(content) < 4 or content[:2] != b"PK":
        # artinya yang balik HTML / halaman login / forbidden
        snippet = content[:400].decode("utf-8", errors="ignore")
        raise RuntimeError(
            "OneDrive mengembalikan HTML (bukan XLSX). "
            "Kemungkinan link embed tidak public-downloadable.\n"
            f"Resolved: {resolved}\n"
            f"Download: {dl}\n"
            f"Snippet: {snippet[:200]}..."
        )

    return content, dl


def _to_int_rp(val) -> Optional[int]:
    """
    Convert 'Rp1,473,000' / '1.473.000' / '1,473,000' / angka -> int.
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none"}:
        return None
    s = s.replace("Rp", "").replace("rp", "").strip()
    s = s.replace(".", "").replace(",", "")
    # sisakan digit saja
    s = re.sub(r"[^\d]", "", s)
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None


def _find_asof_label(df_raw: pd.DataFrame) -> str:
    """
    Cari tanggal '07 February 2026' dari isi sheet.
    """
    text = " ".join([str(x) for x in df_raw.values.flatten().tolist() if str(x) != "nan"])
    m = re.search(r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b", text)
    if m:
        return f"HK Logam Mulia 24K — {m.group(1)}"
    return "HK Logam Mulia 24K"


def _parse_table_from_xlsx(xlsx_bytes: bytes) -> HakabeResult:
    """
    Parse Excel bytes jadi DataFrame standar app:
    columns: vendor, weight_g, sell_idr, buyback_idr
    """
    # read first sheet (biasanya Sheet2)
    df_raw = pd.read_excel(BytesIO(xlsx_bytes), header=None, engine="openpyxl")

    asof_label = _find_asof_label(df_raw)

    # Cari baris header yang mengandung 'Berat' dan 'Harga End User'
    header_row_idx = None
    for i in range(min(50, len(df_raw))):
        row = df_raw.iloc[i].astype(str).str.lower().tolist()
        if any("berat" in c for c in row) and any("harga" in c and "end" in c and "user" in c for c in row):
            header_row_idx = i
            break
    if header_row_idx is None:
        raise RuntimeError("Tidak menemukan header tabel (kolom 'Berat' / 'Harga End User') di XLSX.")

    # Bangun df dengan header dari baris itu
    headers = df_raw.iloc[header_row_idx].tolist()
    df_tbl = df_raw.iloc[header_row_idx + 1 :].copy()
    df_tbl.columns = headers

    # Normalisasi nama kolom
    cols_lower = {str(c).strip().lower(): c for c in df_tbl.columns}

    def pick_col(*candidates: str):
        for cand in candidates:
            for k, orig in cols_lower.items():
                if cand in k:
                    return orig
        return None

    col_weight = pick_col("berat")
    col_sell = pick_col("harga end user")

    if col_weight is None or col_sell is None:
        raise RuntimeError("Kolom 'Berat' atau 'Harga End User' tidak ketemu setelah normalisasi.")

    # Buang baris kosong / yang bukan data berat
    df_data = df_tbl[[col_weight, col_sell]].copy()
    df_data = df_data.dropna(how="all")

    # ambil hanya yang beratnya numeric (0.5, 1, 2, dst)
    def _to_float(x):
        try:
            return float(str(x).strip())
        except Exception:
            return None

    df_data["weight_g"] = df_data[col_weight].apply(_to_float)
    df_data = df_data[df_data["weight_g"].notna()]

    # harga jual per bar (total)
    df_data["sell_idr"] = df_data[col_sell].apply(_to_int_rp)
    df_data = df_data[df_data["sell_idr"].notna()]

    # Cari Buyback per gram dari sheet: cari teks "Buyback"
    buyback_per_gram = None
    flat = df_raw.values.flatten().tolist()
    for idx, v in enumerate(flat):
        if isinstance(v, str) and "buyback" in v.lower():
            # biasanya angka buyback ada di sel dekatnya
            # cek 1..8 sel berikutnya
            for j in range(1, 9):
                if idx + j < len(flat):
                    cand = _to_int_rp(flat[idx + j])
                    if cand:
                        buyback_per_gram = cand
                        break
        if buyback_per_gram:
            break

    if not buyback_per_gram:
        # fallback: kalau tidak ketemu, isi 0 agar tidak error
        buyback_per_gram = 0

    df_out = pd.DataFrame({
        "vendor": "HK Logam Mulia",
        "weight_g": df_data["weight_g"].astype(float),
        "sell_idr": df_data["sell_idr"].astype(int),
        "buyback_idr": (df_data["weight_g"].astype(float) * int(buyback_per_gram)).round().astype(int),
    })

    return HakabeResult(
        df=df_out,
        asof_label=asof_label,
        buyback_per_gram=int(buyback_per_gram),
        iframe_url="",
        download_url="",
    )


# -------------------------
# Public API (dipakai app.py kamu)
# -------------------------
def fetch_and_parse_hakabegold() -> HakabeResult:
    """
    End-to-end:
    fetch homepage -> ambil iframe src -> download xlsx -> parse
    """
    r = requests.get(URL_HAKABEGOLD, headers=_headers(), timeout=30)
    r.raise_for_status()
    home_html = r.text

    iframe_url = _extract_iframe_src(home_html)
    xlsx_bytes, download_url = _download_xlsx_from_iframe(iframe_url)

    result = _parse_table_from_xlsx(xlsx_bytes)
    result.iframe_url = iframe_url
    result.download_url = download_url
    return result


def parse_hakabegold(_html_unused: str = "") -> Tuple[pd.DataFrame, str]:
    """
    Kompatibel dengan app.py lama kamu:
    app.py masih memanggil parse_hakabegold(html)
    Sekarang html param tidak dipakai, karena kita fetch sendiri biar auto-discover.
    """
    result = fetch_and_parse_hakabegold()
    return result.df, result.asof_label
