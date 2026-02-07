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


def _extract_token(page_html: str) -> str | None:
    # token biasanya ada di HTML/JS
    patterns = [
        r'name="simulasi-token"\s*value="([a-f0-9]{16,64})"',
        r'"simulasi-token"\s*:\s*"([a-f0-9]{16,64})"',
        r"simulasi-token\s*=\s*'([a-f0-9]{16,64})'",
        r'simulasi-token\s*=\s*"([a-f0-9]{16,64})"',
    ]
    for p in patterns:
        m = re.search(p, page_html, flags=re.I)
        if m:
            return m.group(1)
    return None


def _post_pricelist(session: requests.Session, token: str, product_key: str) -> dict:
    """
    POST multipart/form-data:
      form: {"product":"comparison_antamxubs"}
      simulasi-token: <token>
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
    r.raise_for_status()
    return r.json()


def parse_indogold(_html_unused: str):
    """
    IndoGold via API JSON comparison_antamxubs.
    Output vendor:
      - Perbandingan - UBS
      - Perbandingan - Antam
      - UBS
      - Antam
    Kolom:
      vendor, weight_g, sell_idr, buyback_idr
    """
    empty_df = pd.DataFrame(columns=STD_COLS)

    # 1) buka halaman untuk dapat cookies + token + last update
    s = requests.Session()
    try:
        page = s.get(URL_INDOGOLD, headers=UA, timeout=30)
        page.raise_for_status()
        page_html = page.text
    except Exception:
        return empty_df, "IndoGold — gagal akses halaman"

    soup = BeautifulSoup(page_html, "html.parser")
    last_update = _find_last_update(soup.get_text(" ", strip=True))
    token = _extract_token(page_html)

    if not token:
        label = "IndoGold — token tidak ditemukan (format berubah)"
        if last_update:
            label = f"IndoGold — token tidak ditemukan — Last Update: {last_update}"
        return empty_df, label

    # 2) panggil API: perbandingan UBS vs Antam
    try:
        payload = _post_pricelist(s, token=token, product_key="comparison_antamxubs")
    except Exception:
        label = "IndoGold — API gagal (get_data_pricelist)"
        if last_update:
            label = f"IndoGold — API gagal — Last Update: {last_update}"
        return empty_df, label

    # 3) parse JSON sesuai contoh user
    # payload["data"]["data_denom"] -> dict: denom_str -> {"Antam":{harga,harga_buyback}, "UBS":{...}}
    try:
        data = payload.get("data", {})
        denom_map = data.get("data_denom", {})
        variants = data.get("list_variant", ["UBS", "Antam"])
    except Exception:
        denom_map = {}
        variants = ["UBS", "Antam"]

    if not denom_map:
        label = "IndoGold — data_denom kosong"
        if last_update:
            label = f"IndoGold — data_denom kosong — Last Update: {last_update}"
        return empty_df, label

    rows = []
    for denom_str, vmap in denom_map.items():
        try:
            w = float(str(denom_str).replace(",", "."))
        except Exception:
            continue

        # build untuk UBS dan Antam kalau ada
        for brand in variants:
            obj = (vmap or {}).get(brand) or {}
            sell = _idr(obj.get("harga", ""))
            bb = _idr(obj.get("harga_buyback", ""))

            if sell or bb:
                # output 4 vendor: perbandingan + brand utama
                if brand == "UBS":
                    rows.append({"vendor": "Perbandingan - UBS", "weight_g": w, "sell_idr": sell, "buyback_idr": bb})
                    rows.append({"vendor": "UBS", "weight_g": w, "sell_idr": sell, "buyback_idr": bb})
                elif brand == "Antam":
                    rows.append({"vendor": "Perbandingan - Antam", "weight_g": w, "sell_idr": sell, "buyback_idr": bb})
                    rows.append({"vendor": "Antam", "weight_g": w, "sell_idr": sell, "buyback_idr": bb})

    df = pd.DataFrame(rows, columns=STD_COLS)

    # dedup vendor+weight (ambil max)
    df["weight_g"] = pd.to_numeric(df["weight_g"], errors="coerce").fillna(0.0)
    df["sell_idr"] = pd.to_numeric(df["sell_idr"], errors="coerce").fillna(0).astype(int)
    df["buyback_idr"] = pd.to_numeric(df["buyback_idr"], errors="coerce").fillna(0).astype(int)

    df = (
        df.sort_values(["vendor", "weight_g", "sell_idr", "buyback_idr"])
          .groupby(["vendor", "weight_g"], as_index=False)
          .agg({"sell_idr": "max", "buyback_idr": "max"})
          .sort_values(["vendor", "weight_g"])
          .reset_index(drop=True)
    )

    label = "IndoGold — Comparison (API)"
    if last_update:
        label = f"IndoGold — Comparison (API) — Last Update: {last_update}"

    return df, label
