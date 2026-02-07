# scrapers/indogold.py
import re
import json
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

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
    Cari token dari HTML/JS.
    Token bentuknya hex panjang (contoh yang kamu punya: 32 hex).
    """
    patterns = [
        r'name="simulasi-token"\s*value="([a-f0-9]{16,64})"',
        r'"simulasi-token"\s*:\s*"([a-f0-9]{16,64})"',
        r"simulasi-token\s*=\s*'([a-f0-9]{16,64})'",
        r'simulasi-token\s*=\s*"([a-f0-9]{16,64})"',
        # fallback: cari string 32-hex yang dekat kata "token"
        r"token[^a-f0-9]{0,30}([a-f0-9]{32})",
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.I)
        if m:
            return m.group(1)
    return None


def _post_pricelist(session: requests.Session, token: str | None, product_key: str) -> dict:
    """
    Coba POST. Kalau token None, tetap coba (kadang backend tidak strict).
    """
    files = {
        "form": (None, json.dumps({"product": product_key}), "application/json"),
    }
    if token:
        files["simulasi-token"] = (None, token)

    headers = {
        **UA,
        "Accept": "*/*",
        "Origin": "https://www.indogold.id",
        "Referer": URL_INDOGOLD,
    }
    r = session.post(API_PRICELIST, headers=headers, files=files, timeout=30)
    r.raise_for_status()
    return r.json()


def _parse_comparison_json(payload: dict) -> pd.DataFrame:
    """
    Parse JSON seperti yang kamu kirim:
    payload["data"]["data_denom"][denom]["UBS"]["harga"], ["harga_buyback"], dst
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
                if brand == "UBS":
                    rows.append({"vendor": "Perbandingan - UBS", "weight_g": w, "sell_idr": sell, "buyback_idr": bb})
                    rows.append({"vendor": "UBS", "weight_g": w, "sell_idr": sell, "buyback_idr": bb})
                elif brand.lower() == "antam":
                    rows.append({"vendor": "Perbandingan - Antam", "weight_g": w, "sell_idr": sell, "buyback_idr": bb})
                    rows.append({"vendor": "Antam", "weight_g": w, "sell_idr": sell, "buyback_idr": bb})

    df = pd.DataFrame(rows, columns=STD_COLS)
    return df


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


def _extract_script_urls(page_html: str) -> list[str]:
    soup = BeautifulSoup(page_html, "html.parser")
    urls = []
    for s in soup.find_all("script"):
        src = s.get("src")
        if src:
            urls.append(urljoin(BASE, src))
    # unik + urut
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            out.append(u)
            seen.add(u)
    return out


def parse_indogold(html: str):
    """
    1) Pakai HTML dari app untuk last_update + cari token (kalau ada)
    2) Coba call API TANPA token (kadang bisa)
    3) Kalau gagal: cari token di JS bundle yang di-load HTML, lalu call API dengan token
    """
    empty_df = pd.DataFrame(columns=STD_COLS)

    soup = BeautifulSoup(html or "", "html.parser")
    last_update = _find_last_update(soup.get_text(" ", strip=True))

    s = requests.Session()

    # (A) coba token dari HTML
    token = _extract_token_any(html or "")

    # (B) coba API langsung (token optional)
    try:
        payload = _post_pricelist(s, token=token, product_key="comparison_antamxubs")
        df = _parse_comparison_json(payload)
        df = _dedup(df)
        if not df.empty:
            label = "IndoGold — API(JSON)"
            if last_update:
                label = f"IndoGold — API(JSON) — Last Update: {last_update}"
            return df, label
    except Exception:
        pass

    # (C) token belum ketemu / API gagal -> cari token di JS bundle
    script_urls = _extract_script_urls(html or "")
    for js_url in script_urls[:15]:  # batasi biar cepat
        try:
            r = s.get(js_url, headers=UA, timeout=30)
            if r.status_code != 200:
                continue
            js_text = r.text
            token2 = _extract_token_any(js_text)
            if not token2:
                continue

            payload = _post_pricelist(s, token=token2, product_key="comparison_antamxubs")
            df = _parse_comparison_json(payload)
            df = _dedup(df)
            if not df.empty:
                label = "IndoGold — API(JSON) via JS token"
                if last_update:
                    label = f"IndoGold — API(JSON) via JS token — Last Update: {last_update}"
                return df, label
        except Exception:
            continue

    label = "IndoGold — token tidak ditemukan"
    if last_update:
        label = f"IndoGold — token tidak ditemukan — Last Update: {last_update}"
    return empty_df, label
