# scrapers/hakabegold.py
from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs, unquote

import requests
import pandas as pd
from openpyxl import load_workbook


URL_HAKABEGOLD = "https://www.logammuliahk.com/#work"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)


@dataclass
class HakabeGoldResult:
    df: pd.DataFrame
    asof_label: str
    buyback_per_gram: Optional[int] = None
    download_url: Optional[str] = None
    iframe_url: Optional[str] = None


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
    )
    return s


def _fetch_text(s: requests.Session, url: str, timeout: int = 30) -> str:
    r = s.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.text


def _fetch_bytes(s: requests.Session, url: str, timeout: int = 30) -> bytes:
    # For download, accept binary strongly
    headers = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    r = s.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.content


def _is_xlsx(data: bytes) -> bool:
    # XLSX is ZIP => starts with PK
    return len(data) >= 2 and data[:2] == b"PK"


def _extract_iframe_src(main_html: str) -> str:
    # Ambil iframe src OneDrive embed (1drv.ms atau onedrive.live.com)
    # di HTML kamu: <iframe ... src='https://1drv.ms/x/c/...?...'>
    m = re.search(r"<iframe[^>]+src=['\"]([^'\"]+)['\"]", main_html, re.I)
    if not m:
        raise RuntimeError("Iframe OneDrive tidak ditemukan di halaman HK (struktur berubah).")
    return m.group(1).strip()


def _best_effort_download_url_from_params(url: str) -> Optional[str]:
    """
    Coba bentuk URL download dari query param (cid/resid/authkey).
    Banyak kasus OneDrive bisa di-download via:
    https://onedrive.live.com/download?cid=...&resid=...&authkey=...
    """
    qs = parse_qs(urlparse(url).query)

    cid = (qs.get("cid") or [None])[0]
    resid = (qs.get("resid") or [None])[0]
    authkey = (qs.get("authkey") or [None])[0]

    # Kadang resid ada di "id" style: F82EA...!106
    # tapi biasanya resid param ada.
    if cid and resid:
        if authkey:
            return f"https://onedrive.live.com/download?cid={cid}&resid={resid}&authkey={authkey}"
        return f"https://onedrive.live.com/download?cid={cid}&resid={resid}"

    return None


def _extract_possible_download_links(html: str) -> list[str]:
    """
    Cari kandidat link download dalam HTML (kalau ada).
    Kita over-generate beberapa pola umum.
    """
    candidates: list[str] = []

    # Pola download endpoint
    for pat in [
        r"https://onedrive\.live\.com/download\?[^\"'\s]+",
        r"https://onedrive\.live\.com/[^\"'\s]*download\.aspx\?[^\"'\s]+",
        r"https://[^\"'\s]+/download\.aspx\?[^\"'\s]+",
    ]:
        candidates.extend(re.findall(pat, html, re.I))

    # Kadang URL ada dalam JSON-escaped (\/)
    esc = re.findall(r"https:\\/\\/onedrive\.live\.com\\/download\\\?[^\"'\s]+", html, re.I)
    for e in esc:
        candidates.append(e.replace("\\/", "/").replace("\\", ""))

    # Dedup, keep order
    out: list[str] = []
    seen = set()
    for u in candidates:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _resolve_download_url(s: requests.Session, iframe_url: str) -> Tuple[Optional[str], str]:
    """
    Strategi:
    1) Kalau iframe_url sudah punya cid/resid/authkey => bentuk /download
    2) Fetch HTML iframe_url, cari link download di HTML
    3) Kalau iframe_url mengandung redeem=..., kadang di situ ada 1drv link; tetap fetch dan cari link download
    """
    # 1) quick build
    dl = _best_effort_download_url_from_params(iframe_url)
    if dl:
        return dl, "from_query_params"

    # 2) fetch iframe html and scrape candidates
    html = _fetch_text(s, iframe_url)
    cands = _extract_possible_download_links(html)
    if cands:
        return cands[0], "from_iframe_html"

    # 3) try to find any onedrive.live.com/edit link then build download from it
    m = re.search(r"https://onedrive\.live\.com/edit\?[^\"'\s]+", html, re.I)
    if m:
        edit_url = m.group(0)
        dl2 = _best_effort_download_url_from_params(edit_url)
        if dl2:
            return dl2, "from_edit_url_in_html"

    return None, "not_found"


def _parse_sheet2_table(xlsx_bytes: bytes) -> HakabeGoldResult:
    wb = load_workbook(BytesIO(xlsx_bytes), data_only=True)

    # Prefer Sheet2 (sesuai embed "Sheet2")
    sheet_name = None
    for name in wb.sheetnames:
        if str(name).strip().lower() == "sheet2":
            sheet_name = name
            break
    if not sheet_name:
        # fallback: first sheet
        sheet_name = wb.sheetnames[0]

    ws = wb[sheet_name]

    # Tabel biasanya ada header "Berat" dst, lalu baris data.
    # Kita scan area A1:K60 untuk cari cell "Berat".
    start_row = None
    start_col = None
    for r in range(1, 61):
        for c in range(1, 12):
            v = ws.cell(r, c).value
            if isinstance(v, str) and v.strip().lower() == "berat":
                start_row, start_col = r, c
                break
        if start_row:
            break

    if not start_row:
        raise RuntimeError("Tidak menemukan header 'Berat' di XLSX (format berubah).")

    # Kita ambil 6 kolom seperti di gambar:
    # Berat | Harga End User | Harga End User/gr | Harga+PPH 22 | Harga+PPH 22/gr | Stok
    headers = []
    for c in range(start_col, start_col + 6):
        headers.append(ws.cell(start_row, c).value)

    # Data sampai ketemu baris kosong di kolom Berat
    rows = []
    r = start_row + 1
    while r < start_row + 80:
        weight = ws.cell(r, start_col).value
        if weight is None or str(weight).strip() == "":
            break

        vals = [ws.cell(r, start_col + i).value for i in range(6)]
        rows.append(vals)
        r += 1

    if not rows:
        raise RuntimeError("Tabel harga kosong di XLSX.")

    # Cari buyback per gram: scan bawah tabel untuk kata "Buyback"
    buyback = None
    for rr in range(r, min(r + 20, 120)):
        row_text = " ".join([str(ws.cell(rr, cc).value or "") for cc in range(1, 10)]).lower()
        if "buyback" in row_text:
            # ambil angka terbesar di baris itu
            nums = []
            for cc in range(1, 12):
                v = ws.cell(rr, cc).value
                if isinstance(v, (int, float)):
                    nums.append(int(v))
                elif isinstance(v, str):
                    m = re.sub(r"[^\d]", "", v)
                    if m.isdigit():
                        nums.append(int(m))
            if nums:
                buyback = max(nums)
            break

    # Cari tanggal/as-of dari header atas: scan 1..15 baris untuk string yang mirip tanggal
    asof = "HK Logam Mulia"
    for rr in range(1, min(start_row, 20)):
        v = ws.cell(rr, start_col + 1).value  # area judul biasanya di tengah
        if isinstance(v, str) and ("202" in v or "feb" in v.lower() or "january" in v.lower()):
            asof = v.strip()
            break

    # Build df long format: vendor, weight_g, sell_idr, buyback_idr
    out = []
    for w, sell, sell_gr, pph, pph_gr, stok in rows:
        # w bisa 0.5, 1, 2, dst
        try:
            weight_g = float(w)
        except Exception:
            continue

        # harga end user (kolom 2)
        sell_idr = _to_int(sell)
        # buyback: kalau ada per gram, kalikan weight
        buyback_idr = int(buyback * weight_g) if buyback else 0

        out.append(
            {
                "vendor": "HK Logam Mulia",
                "weight_g": weight_g,
                "sell_idr": sell_idr,
                "buyback_idr": buyback_idr,
                "stock": str(stok or "").strip(),
            }
        )

    df = pd.DataFrame(out)
    return HakabeGoldResult(df=df, asof_label=f"HK Logam Mulia — {asof}", buyback_per_gram=buyback)


def _to_int(x) -> int:
    if x is None:
        return 0
    if isinstance(x, (int, float)):
        return int(x)
    if isinstance(x, str):
        s = re.sub(r"[^\d]", "", x)
        return int(s) if s.isdigit() else 0
    return 0


def fetch_and_parse_hakabegold() -> HakabeGoldResult:
    """
    Pipeline:
    1) fetch halaman HK
    2) extract iframe OneDrive
    3) resolve URL download XLSX
    4) download bytes -> validasi PK
    5) parse sheet2
    """
    s = _session()

    main_html = _fetch_text(s, URL_HAKABEGOLD)
    iframe_url = _extract_iframe_src(main_html)

    download_url, how = _resolve_download_url(s, iframe_url)
    if not download_url:
        raise RuntimeError(
            "Gagal auto-discover link download XLSX dari iframe. "
            "Kemungkinan OneDrive mengubah pola embed, atau butuh akses/cookies."
        )

    xlsx_bytes = _fetch_bytes(s, download_url)
    if not _is_xlsx(xlsx_bytes):
        # debugging hint (tanpa bocorin terlalu banyak)
        head = xlsx_bytes[:200].decode("utf-8", errors="ignore")
        raise RuntimeError(
            "Download tidak mengembalikan XLSX (PK...). "
            f"Metode: {how}. URL: {download_url}\n"
            f"Snippet awal respons (bukan file): {head[:200]!r}"
        )

    result = _parse_sheet2_table(xlsx_bytes)
    result.download_url = download_url
    result.iframe_url = iframe_url
    return result


def parse_hakabegold(_: str = "") -> Tuple[pd.DataFrame, str]:
    """
    Kompatibel dengan pola app kamu: parse_* mengembalikan (df, update_label)
    """
    res = fetch_and_parse_hakabegold()
    return res.df, res.asof_label
