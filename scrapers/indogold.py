# scrapers/indogold.py
import re
import json
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

URL_INDOGOLD = "https://www.indogold.id/harga-emas-hari-ini"
BASE = "https://www.indogold.id"
API_PRICELIST = "https://www.indogold.id/home/get_data_pricelist"

STD_COLS = ["vendor", "weight_g", "sell_idr", "buyback_idr"]

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

HEADERS_HTML = {
    **UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
HEADERS_API = {
    **UA,
    "Accept": "*/*",
    "Origin": "https://www.indogold.id",
    "Referer": URL_INDOGOLD,
}


def _idr(x: str) -> int:
    if not x:
        return 0
    digits = re.sub(r"[^\d]", "", x)
    return int(digits) if digits else 0


def _find_last_update(text: str) -> str | None:
    m = re.search(
        r"Last\s*Update\s*:\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}\s+[0-9]{2}:[0-9]{2})",
        text,
        flags=re.I,
    )
    return m.group(1).strip() if m else None


def _extract_token_any(text: str) -> str | None:
    """
    Token IndoGold terlihat seperti 32-hex (contoh: f8c593ec3314c01f904a9c5515989387)
    """
    if not text:
        return None

    # pola eksplisit
    patterns = [
        r'name=["\']simulasi-token["\']\s*value=["\']([a-f0-9]{16,64})["\']',
        r'"simulasi-token"\s*:\s*"([a-f0-9]{16,64})"',
        r"simulasi-token\s*=\s*'([a-f0-9]{16,64})'",
        r'simulasi-token\s*=\s*"([a-f0-9]{16,64})"',
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.I)
        if m:
            return m.group(1)

    # fallback: cari hex32
    m = re.search(r"\b[a-f0-9]{32}\b", text, flags=re.I)
    return m.group(0) if m else None


def _is_local_script(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        return host.endswith("indogold.id")
    except Exception:
        return False


def _extract_script_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    urls = []
    for s in soup.find_all("script"):
        src = s.get("src")
        if src:
            full = urljoin(BASE, src)
            if _is_local_script(full):
                urls.append(full)
    # unique preserve order
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            out.append(u)
            seen.add(u)
    return out


def _extract_home_endpoints(text: str) -> list[str]:
    """
    Ambil semua string endpoint /home/xxx dari HTML/JS.
    """
    eps = set()
    for m in re.finditer(r"(\/home\/[a-zA-Z0-9_]+)", text or ""):
        eps.add(m.group(1))
    # prioritaskan yang mengandung token/simulasi
    prioritized = sorted(
        eps,
        key=lambda x: (("token" not in x and "simul" not in x), len(x))
    )
    return prioritized


def _try_get_token_from_candidates(session: requests.Session, candidates: list[str]) -> str | None:
    for path in candidates:
        url = urljoin(BASE, path)
        try:
            r = session.get(url, headers=HEADERS_API, timeout=20)
            if r.status_code != 200:
                continue
            tok = _extract_token_any(r.text or "")
            if tok and re.fullmatch(r"[a-f0-9]{32}", tok, flags=re.I):
                return tok
        except Exception:
            continue
    return None


def _post_pricelist(session: requests.Session, token: str) -> tuple[dict | None, str]:
    files = {
        "form": (None, json.dumps({"product": "comparison_antamxubs"}), "application/json"),
        "simulasi-token": (None, token),
    }
    r = session.post(API_PRICELIST, headers=HEADERS_API, files=files, timeout=30)
    raw = r.text or ""
    try:
        return r.json(), raw
    except Exception:
        return None, raw


def _parse_comparison_json(payload: dict) -> pd.DataFrame:
    """
    payload contoh:
    {"status": true, "data": {"list_variant":["UBS","Antam"], "data_denom": {...}, "type":"comparison"}}
    """
    rows = []

    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    denom_map = data.get("data_denom", {}) if isinstance(data, dict) else {}
    variants = data.get("list_variant", ["UBS", "Antam"]) if isinstance(data, dict) else ["UBS", "Antam"]

    for denom_str, vmap in (denom_map or {}).items():
        try:
            w = float(str(denom_str).replace(",", "."))
        except Exception:
            continue

        for brand in variants:
            obj = (vmap or {}).get(brand) or {}
            sell = _idr(obj.get("harga", ""))
            bb = _idr(obj.get("harga_buyback", ""))

            if sell or bb:
                if brand.strip().upper() == "UBS":
                    rows.append({"vendor": "Perbandingan - UBS", "weight_g": w, "sell_idr": sell, "buyback_idr": bb})
                    rows.append({"vendor": "UBS", "weight_g": w, "sell_idr": sell, "buyback_idr": bb})
                elif brand.strip().lower() == "antam":
                    rows.append({"vendor": "Perbandingan - Antam", "weight_g": w, "sell_idr": sell, "buyback_idr": bb})
                    rows.append({"vendor": "Antam", "weight_g": w, "sell_idr": sell, "buyback_idr": bb})

    return pd.DataFrame(rows, columns=STD_COLS)


def _dedup(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df["weight_g"] = pd.to_numeric(df["weight_g"], errors="coerce").fillna(0.0)
    df["sell_idr"] = pd.to_numeric(df["sell_idr"], errors="coerce").fillna(0).astype(int)
    df["buyback_idr"] = pd.to_numeric(df["buyback_idr"], errors="coerce").fillna(0).astype(int)

    return (
        df.sort_values(["vendor", "weight_g", "sell_idr", "buyback_idr"])
          .groupby(["vendor", "weight_g"], as_index=False)
          .agg({"sell_idr": "max", "buyback_idr": "max"})
          .sort_values(["vendor", "weight_g"])
          .reset_index(drop=True)
    )


def parse_indogold(html: str):
    """
    Flow:
    - pakai HTML dari app untuk last_update
    - scan HTML + JS lokal untuk menemukan endpoint token yang benar
    - call endpoint token -> dapat token hex32
    - POST get_data_pricelist -> pastikan status true -> parse data_denom
    """
    empty_df = pd.DataFrame(columns=STD_COLS)

    soup = BeautifulSoup(html or "", "html.parser")
    last_update = _find_last_update(soup.get_text(" ", strip=True))

    session = requests.Session()

    # 0) buka halaman (biar cookie/session kebentuk)
    # (HTML sudah dari app, tapi session di sini butuh cookie juga)
    try:
        session.get(URL_INDOGOLD, headers=HEADERS_HTML, timeout=20)
    except Exception:
        pass

    # 1) cari token langsung di HTML (kalau ada)
    token = _extract_token_any(html or "")

    # 2) kalau tidak ada, cari endpoint token dari HTML/JS
    if not token:
        candidates = []
        # dari HTML
        candidates += _extract_home_endpoints(html or "")

        # dari JS lokal
        script_urls = _extract_script_urls(html or "")
        for js_url in script_urls[:25]:  # cukup 25 biar cepat
            try:
                r = session.get(js_url, headers=HEADERS_API, timeout=20)
                if r.status_code != 200:
                    continue
                candidates += _extract_home_endpoints(r.text or "")
            except Exception:
                continue

        # unik + tetap urut
        seen = set()
        uniq = []
        for c in candidates:
            if c not in seen:
                uniq.append(c)
                seen.add(c)

        token = _try_get_token_from_candidates(session, uniq)

    if not token:
        label = "IndoGold — token tidak ditemukan"
        if last_update:
            label = f"IndoGold — token tidak ditemukan — Last Update: {last_update}"
        return empty_df, label

    # 3) POST pricelist
    payload, raw = _post_pricelist(session, token=token)

    if not payload:
        hint = (raw[:200] or "").replace("\n", " ").strip()
        label = f"IndoGold — API tidak JSON (hint: {hint})"
        if last_update:
            label = f"IndoGold — API tidak JSON — Last Update: {last_update}"
        return empty_df, label

    # 4) pastikan status true (kalau status false, ini biasanya token salah)
    if payload.get("status") is False:
        # banyak backend taruh message di "message" / "msg" / "data"
        msg = payload.get("message") or payload.get("msg") or ""
        label = f"IndoGold — status false (token invalid) {msg}".strip()
        if last_update:
            label = f"IndoGold — status false (token invalid) — Last Update: {last_update}"
        return empty_df, label

    df = _parse_comparison_json(payload)
    df = _dedup(df)

    if df.empty:
        # supaya tidak generik, tampilkan key penting (debug ringan)
        keys = list((payload.get("data") or {}).keys()) if isinstance(payload, dict) else []
        label = f"IndoGold — parsing kosong (keys: {keys})"
        if last_update:
            label = f"IndoGold — parsing kosong — Last Update: {last_update}"
        return empty_df, label

    label = "IndoGold — API(JSON)"
    if last_update:
        label = f"IndoGold — API(JSON) — Last Update: {last_update}"
    return df, label
