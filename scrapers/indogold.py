# scrapers/indogold.py
import re
import json
import pandas as pd
import requests
from bs4 import BeautifulSoup

URL_INDOGOLD = "https://www.indogold.id/harga-emas-hari-ini"
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


def _extract_token_from_html(html: str) -> str | None:
    """
    Lebih agresif:
    1) pola input hidden
    2) pola json/js
    3) cari hex32 yang dekat kata simulasi/token
    """
    if not html:
        return None

    patterns = [
        r'name=["\']simulasi-token["\']\s*value=["\']([a-f0-9]{16,64})["\']',
        r'"simulasi-token"\s*:\s*"([a-f0-9]{16,64})"',
        r"simulasi-token\s*=\s*'([a-f0-9]{16,64})'",
        r'simulasi-token\s*=\s*"([a-f0-9]{16,64})"',
    ]
    for p in patterns:
        m = re.search(p, html, flags=re.I)
        if m:
            return m.group(1)

    # heuristik: cari hex32 yang dekat "simulasi" / "token"
    for m in re.finditer(r"\b[a-f0-9]{32}\b", html, flags=re.I):
        start = max(0, m.start() - 250)
        end = min(len(html), m.end() + 250)
        around = html[start:end].lower()
        if "simulasi" in around or "token" in around:
            return m.group(0)

    return None


def _try_fetch_token_endpoints(session: requests.Session) -> str | None:
    """
    Karena token tidak muncul di HTML/JS di Streamlit Cloud,
    coba beberapa endpoint umum yang sering dipakai web CI / CSRF token.
    Kita scan responnya untuk hex32.
    """
    candidates = [
        "https://www.indogold.id/home/get_simulasi_token",
        "https://www.indogold.id/home/get_simulasiToken",
        "https://www.indogold.id/home/get_token",
        "https://www.indogold.id/home/token",
        "https://www.indogold.id/home/get_csrf",
        "https://www.indogold.id/home/csrf",
    ]

    headers = {
        **UA,
        "Accept": "*/*",
        "Origin": "https://www.indogold.id",
        "Referer": URL_INDOGOLD,
    }

    for url in candidates:
        try:
            r = session.get(url, headers=headers, timeout=20)
            if r.status_code != 200:
                continue
            txt = r.text or ""
            m = re.search(r"\b[a-f0-9]{32}\b", txt, flags=re.I)
            if m:
                return m.group(0)
        except Exception:
            continue

    return None


def _post_pricelist(session: requests.Session, token: str, product_key: str) -> tuple[dict | None, str]:
    """
    Return (json_or_none, raw_text)
    Agar tidak crash kalau response HTML.
    """
    files = {
        "form": (None, json.dumps({"product": product_key}), "application/json"),
        "simulasi-token": (None, token),
    }
    headers = {
        **UA,
        "Accept": "*/*",
        "Origin": "https://www.indogold.id",
        "Referer": URL_INDOGOLD,
    }
    r = session.post(API_PRICELIST, headers=headers, files=files, timeout=30)
    raw = r.text or ""
    # coba json kalau memang json
    try:
        return r.json(), raw
    except Exception:
        return None, raw


def _parse_comparison_json(payload: dict) -> pd.DataFrame:
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
    IndoGold:
    - Gunakan HTML dari app.py untuk last_update + attempt token.
    - Kalau token tidak ada di HTML, coba endpoint token heuristik.
    - POST API get_data_pricelist (comparison_antamxubs), parse JSON data_denom.
    """
    empty_df = pd.DataFrame(columns=STD_COLS)

    soup = BeautifulSoup(html or "", "html.parser")
    last_update = _find_last_update(soup.get_text(" ", strip=True))

    s = requests.Session()

    # 1) token dari HTML dulu
    token = _extract_token_from_html(html or "")

    # 2) kalau masih None, coba endpoint token
    if not token:
        token = _try_fetch_token_endpoints(s)

    if not token:
        label = "IndoGold — token tidak ditemukan"
        if last_update:
            label = f"IndoGold — token tidak ditemukan — Last Update: {last_update}"
        return empty_df, label

    # 3) call API
    payload, raw = _post_pricelist(s, token=token, product_key="comparison_antamxubs")

    if not payload:
        # tampilkan petunjuk yang berguna, bukan crash
        # (raw biasanya HTML error/redirect)
        hint = raw[:200].replace("\n", " ").strip()
        label = f"IndoGold — API tidak mengembalikan JSON (hint: {hint})"
        if last_update:
            label = f"IndoGold — API tidak JSON — Last Update: {last_update}"
        return empty_df, label

    # 4) parse JSON
    df = _parse_comparison_json(payload)
    df = _dedup(df)

    if df.empty:
        label = "IndoGold — parsing kosong (struktur JSON berubah)"
        if last_update:
            label = f"IndoGold — parsing kosong — Last Update: {last_update}"
        return empty_df, label

    label = "IndoGold — API(JSON)"
    if last_update:
        label = f"IndoGold — API(JSON) — Last Update: {last_update}"
    return df, label
