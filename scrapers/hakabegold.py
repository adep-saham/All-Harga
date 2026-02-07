# scrapers/hakabegold.py
from __future__ import annotations

import re
from io import BytesIO
from dataclasses import dataclass
from typing import Optional, Tuple, List

import pandas as pd
import requests


# =========================
# Config
# =========================
SOURCE_PAGE_URL = "https://www.logammuliahk.com/#work"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


# =========================
# Exceptions
# =========================
class HakabeGoldError(RuntimeError):
    pass


class DiscoverError(HakabeGoldError):
    pass


class DownloadError(HakabeGoldError):
    pass


# =========================
# Helpers: fetch page & discover iframe
# =========================
IFRAME_SRC_RE = re.compile(
    r"""<iframe[^>]+src=['"](?P<src>https?://[^'"]+)['"]""",
    re.IGNORECASE,
)

ONEDRIVE_SHORT_RE = re.compile(r"^https?://1drv\.ms/", re.IGNORECASE)


def fetch_page_html(url: str = SOURCE_PAGE_URL, timeout: int = 30) -> str:
    r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text


def discover_iframe_src(html: str) -> str:
    """
    Ambil iframe src dari halaman HK.
    Kita pilih iframe yang mengarah ke 1drv.ms (Excel embed).
    """
    matches = list(IFRAME_SRC_RE.finditer(html))
    if not matches:
        raise DiscoverError("Tidak menemukan <iframe src=...> di HTML.")

    # pilih yang 1drv.ms (excel)
    candidates = []
    for m in matches:
        src = m.group("src").strip()
        if ONEDRIVE_SHORT_RE.search(src):
            candidates.append(src)

    if not candidates:
        # fallback: pakai iframe pertama
        return matches[0].group("src").strip()

    # biasanya cuma 1
    return candidates[0]


# =========================
# OneDrive: resolve to direct download
# =========================
CID_RE = re.compile(r"(?:\?|&)cid=([0-9A-Fa-f]{16})")
RESID_RE = re.compile(r"(?:\?|&)resid=([^&]+)")
AUTHKEY_RE = re.compile(r"(?:\?|&)authkey=([^&]+)")


def _follow_redirect(url: str, timeout: int = 30) -> str:
    """
    Follow redirect 1drv.ms -> onedrive.live.com / officeapps
    """
    r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return str(r.url)


def _extract_onedrive_tokens(final_url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extract cid/resid/authkey dari URL final (onedrive.live.com)
    """
    cid = None
    resid = None
    authkey = None

    m = CID_RE.search(final_url)
    if m:
        cid = m.group(1)

    m = RESID_RE.search(final_url)
    if m:
        resid = m.group(1)

    m = AUTHKEY_RE.search(final_url)
    if m:
        authkey = m.group(1)

    return cid, resid, authkey


def resolve_onedrive_download_url(iframe_src: str) -> str:
    """
    Konsep:
    1) iframe src = 1drv.ms embed link
    2) follow redirect -> dapat URL panjang (biasanya onedrive.live.com / excel.officeapps)
    3) ambil cid/resid/authkey
    4) bentuk direct download:

       https://onedrive.live.com/download?cid=...&resid=...&authkey=...

    Kalau token tidak ketemu, fallback: tambahkan &download=1 ke URL final.
    """
    final_url = _follow_redirect(iframe_src)

    cid, resid, authkey = _extract_onedrive_tokens(final_url)

    if cid and resid:
        # direct download endpoint (paling umum berhasil)
        if authkey:
            return f"https://onedrive.live.com/download?cid={cid}&resid={resid}&authkey={authkey}"
        return f"https://onedrive.live.com/download?cid={cid}&resid={resid}"

    # fallback: beberapa kasus final_url sudah punya param download=1 yang bekerja
    if "download=1" in final_url:
        return final_url

    joiner = "&" if "?" in final_url else "?"
    return final_url + f"{joiner}download=1"


def _looks_like_xlsx(content: bytes) -> bool:
    # XLSX adalah ZIP: magic bytes "PK"
    return len(content) >= 2 and content[:2] == b"PK"


def download_xlsx(download_url: str, timeout: int = 45) -> bytes:
    """
    Download XLSX bytes. Validasi:
    - status 200
    - bytes mulai dengan 'PK'
    Kalau yang balik HTML, lempar error biar kelihatan jelas.
    """
    headers = dict(DEFAULT_HEADERS)
    headers["Accept"] = "application/octet-stream,*/*"

    r = requests.get(download_url, headers=headers, timeout=timeout, allow_redirects=True)
    r.raise_for_status()

    data = r.content
    if _looks_like_xlsx(data):
        return data

    # kalau bukan xlsx, biasanya HTML error page
    snippet = data[:300].decode("utf-8", errors="ignore").lower()
    if "<html" in snippet or "<!doctype" in snippet:
        raise DownloadError(
            "Download URL mengembalikan HTML (bukan XLSX). "
            "Kemungkinan share tidak public-downloadable / butuh izin."
        )

    raise DownloadError("File yang didownload tidak terdeteksi sebagai XLSX (bukan ZIP/PK).")


# =========================
# Parse HK Excel
# =========================
@dataclass
class HakabeGoldResult:
    table: pd.DataFrame
    buyback_per_gram: Optional[float]
    asof_label: Optional[str]


def _normalize_col(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def _find_header_row(df_raw: pd.DataFrame) -> int:
    """
    Cari baris yang punya header 'berat' dan 'harga end user' dll.
    """
    for i in range(min(len(df_raw), 60)):
        row = df_raw.iloc[i].astype(str).tolist()
        joined = " | ".join(_normalize_col(x) for x in row)
        if "berat" in joined and "harga end user" in joined:
            return i
    return -1


def _to_number_id(s: str) -> Optional[float]:
    if s is None:
        return None
    t = str(s)
    t = t.replace("Rp", "").replace("rp", "").replace(".", "").replace(",", ".")
    t = re.sub(r"[^0-9.\-]", "", t)
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def parse_hakabegold_from_xlsx(xlsx_bytes: bytes) -> HakabeGoldResult:
    """
    Baca XLSX -> ambil Sheet2 (sesuai embed).
    Parser dibuat fleksibel: cari header row, lalu ambil baris-baris data hingga kosong.
    """
    # baca semua sheet name dulu (biar tahan kalau nama berubah)
    xls = pd.ExcelFile(BytesIO(xlsx_bytes))
    sheet_name = None
    for name in xls.sheet_names:
        if _normalize_col(name) == "sheet2":
            sheet_name = name
            break
    if sheet_name is None:
        # fallback: ambil sheet pertama
        sheet_name = xls.sheet_names[0]

    df_raw = pd.read_excel(BytesIO(xlsx_bytes), sheet_name=sheet_name, header=None)

    # label tanggal/as-of (kadang ada di atas tabel)
    asof_label = None
    for i in range(min(len(df_raw), 15)):
        line = " ".join(str(x) for x in df_raw.iloc[i].tolist() if str(x).strip() not in ("nan", "None"))
        if re.search(r"\b20\d{2}\b", line):
            asof_label = line.strip()
            break

    hdr_i = _find_header_row(df_raw)
    if hdr_i < 0:
        raise HakabeGoldError("Tidak menemukan header tabel (Berat / Harga End User) di sheet.")

    header = df_raw.iloc[hdr_i].tolist()
    data = df_raw.iloc[hdr_i + 1 :].copy()
    data.columns = header

    # rapikan kolom: ambil kolom yang relevan dengan nama mendekati
    cols = list(data.columns)

    def pick_col(keywords: List[str]) -> Optional[str]:
        for c in cols:
            cc = _normalize_col(c)
            if all(k in cc for k in keywords):
                return c
        return None

    col_berat = pick_col(["berat"])
    col_end_user = pick_col(["harga", "end", "user"])
    col_end_user_gr = pick_col(["harga", "end", "user/gr"]) or pick_col(["harga", "end", "user", "gr"])
    col_pph = pick_col(["pph"])
    col_pph_gr = pick_col(["pph", "gr"])
    col_stok = pick_col(["stok"])

    if not col_berat or not col_end_user:
        raise HakabeGoldError("Kolom utama (Berat, Harga End User) tidak ditemukan.")

    # stop saat berat kosong
    out_rows = []
    for _, r in data.iterrows():
        berat = r.get(col_berat, None)
        if pd.isna(berat) or str(berat).strip().lower() in ("", "nan", "none"):
            # biasanya setelah tabel ada baris buyback
            break

        row = {
            "Berat": _to_number_id(berat) if str(berat).strip() not in ("-", "") else None,
            "Harga End User": _to_number_id(r.get(col_end_user, None)),
        }
        if col_end_user_gr:
            row["Harga End User/gr"] = _to_number_id(r.get(col_end_user_gr, None))
        if col_pph:
            row["Harga+PPH22"] = _to_number_id(r.get(col_pph, None))
        if col_pph_gr:
            row["Harga+PPH22/gr"] = _to_number_id(r.get(col_pph_gr, None))
        if col_stok:
            row["Stok"] = str(r.get(col_stok, "")).strip()

        out_rows.append(row)

    table = pd.DataFrame(out_rows)

    # cari buyback (biasanya di baris bawah: "Buyback Emas Batangan" + angka /gram)
    buyback = None
    for i in range(hdr_i + 1, min(len(df_raw), hdr_i + 80)):
        line = " ".join(str(x) for x in df_raw.iloc[i].tolist() if str(x).strip().lower() not in ("nan", "none"))
        if "buyback" in line.lower():
            # ambil angka pertama yang masuk akal
            nums = re.findall(r"[\d\.\,]+", line)
            for n in nums[::-1]:
                val = _to_number_id(n)
                if val and val > 1000:
                    buyback = val
                    break
            if buyback:
                break

    return HakabeGoldResult(table=table, buyback_per_gram=buyback, asof_label=asof_label)


def fetch_and_parse_hakabegold() -> HakabeGoldResult:
    """
    Full pipeline:
    - fetch html
    - discover iframe src (1drv.ms)
    - resolve direct download
    - download xlsx
    - parse
    """
    html = fetch_page_html(SOURCE_PAGE_URL)
    iframe_src = discover_iframe_src(html)
    dl_url = resolve_onedrive_download_url(iframe_src)
    xlsx_bytes = download_xlsx(dl_url)
    return parse_hakabegold_from_xlsx(xlsx_bytes)
