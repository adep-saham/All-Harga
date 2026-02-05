"""
Streamlit app — Scrape Harga Emas Galeri24 (Jual + Buyback)

✅ Jual: endpoint /api/product-variants (vendor Galeri24)
⚠️ Buyback: berbeda-beda per implementasi backend & bisa berubah.
App ini dibuat robust dengan:
- probing beberapa kandidat endpoint buyback (page-data variants)
- opsi input manual URL buyback
- opsi paste "Copy as cURL" dari DevTools untuk ambil URL + headers

Catatan:
- Kalau buyback masih kosong, hampir pasti URL buyback yang benar belum kita temukan.
  Cara paling cepat: Chrome DevTools → Network → Fetch/XHR → klik request yang berisi buyback → Copy as cURL,
  lalu paste ke kotak "Paste cURL" di app ini.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st


# ----------------------
# CONFIG
# ----------------------
@dataclass(frozen=True)
class Config:
    vendor_id_galeri24: str = "d0fd1d95-ac0a-48d8-95f8-98bd9c5f9197"
    base_url: str = "https://galeri24.co.id"
    page_path: str = "/harga-emas"

    # Sell prices
    take_variants: int = 500  # bump a bit, aman
    timeout_sec: int = 25

    # Default headers (bisa dioverride dari cURL)
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/144.0.0.0 Safari/537.36"
    )


CFG = Config()


def default_headers(referer: Optional[str] = None) -> Dict[str, str]:
    return {
        "User-Agent": CFG.user_agent,
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": referer or f"{CFG.base_url}{CFG.page_path}",
    }


# ----------------------
# HELPERS (parsing & normalization)
# ----------------------
_INT_RE = re.compile(r"[^\d]")


def to_int(x: Any) -> Optional[int]:
    """Best-effort convert (1.234.000 / 'Rp 1,234,000' / 1234000) → int."""
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return int(x)
        s = str(x)
        digits = _INT_RE.sub("", s)
        return int(digits) if digits else None
    except Exception:
        return None


def norm_gram(x: Any) -> Optional[str]:
    """
    Normalize weight string to '1', '0.5', '2.3', etc.
    Examples:
      "1 Gram - Black Gold Series" -> "1"
      "0.5 Gram" -> "0.5"
      "2,3 gr" -> "2.3"
      "1.88 gr [GE-...]" -> "1.88"
    """
    if x is None:
        return None
    s = str(x).lower().strip().replace(",", ".")
    s = s.replace("gram", " ").replace("gr", " ").replace("g", " ")
    # ambil token angka pertama
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return m.group(1) if m else None


def find_first_list(payload: Any) -> Optional[List[Any]]:
    """
    Cari list items pada payload yang bentuknya bisa:
    - list langsung
    - dict dengan key: data/items/results/result
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("items", "results", "result", "data"):
            v = payload.get(k)
            if isinstance(v, list):
                return v
        # data nested
        d = payload.get("data")
        if isinstance(d, dict):
            for k in ("items", "results", "result"):
                v = d.get(k)
                if isinstance(v, list):
                    return v
    return None


# ----------------------
# HTTP utilities
# ----------------------
def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(default_headers())
    return s


def safe_get(
    sess: requests.Session,
    url: str,
    timeout: int,
    expect_json: bool = False,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, str, Dict[str, str], Optional[Any], str]:
    """
    Returns: (status_code, final_url, resp_headers, json_payload_if_any, text_snippet)
    """
    headers = dict(sess.headers)
    if extra_headers:
        headers.update(extra_headers)

    r = sess.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    text = r.text or ""
    payload = None
    if expect_json:
        try:
            payload = r.json()
        except Exception:
            payload = None
    snippet = text[:2500]
    return r.status_code, r.url, dict(r.headers), payload, snippet


# ----------------------
# cURL parser (Copy as cURL)
# ----------------------
_CURL_URL_RE = re.compile(r"curl\s+'([^']+)'|curl\s+\"([^\"]+)\"|curl\s+(\S+)")
_CURL_H_RE = re.compile(r"-H\s+'([^']+)'|-H\s+\"([^\"]+)\"")
_CURL_COOKIE_RE = re.compile(r"-b\s+'([^']+)'|-b\s+\"([^\"]+)\"|--cookie\s+'([^']+)'|--cookie\s+\"([^\"]+)\"")


def parse_curl(curl_text: str) -> Tuple[Optional[str], Dict[str, str]]:
    """
    Minimal parser untuk:
    - URL
    - Headers (-H "Key: value")
    - Cookie (-b / --cookie)
    """
    if not curl_text:
        return None, {}

    # URL
    m = _CURL_URL_RE.search(curl_text)
    url = None
    if m:
        url = next((g for g in m.groups() if g), None)

    # Headers
    headers: Dict[str, str] = {}
    for hm in _CURL_H_RE.finditer(curl_text):
        h = next((g for g in hm.groups() if g), "")
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()

    # Cookie
    cm = _CURL_COOKIE_RE.search(curl_text)
    if cm:
        cookie = next((g for g in cm.groups() if g), None)
        if cookie:
            headers["Cookie"] = cookie

    return url, headers


# ----------------------
# SELL: product-variants
# ----------------------
@st.cache_data(show_spinner=False, ttl=60)
def fetch_sell_prices() -> pd.DataFrame:
    sess = new_session()
    url = (
        f"{CFG.base_url}/api/product-variants"
        f"?take={CFG.take_variants}&vendor_id={CFG.vendor_id_galeri24}"
    )
    status, final_url, rh, payload, snippet = safe_get(
        sess, url, timeout=CFG.timeout_sec, expect_json=True
    )
    if status != 200 or payload is None:
        raise RuntimeError(
            f"product-variants gagal: status={status}, final_url={final_url}, "
            f"content-type={rh.get('content-type','')}"
        )

    items = find_first_list(payload)
    if not isinstance(items, list):
        raise RuntimeError("product-variants: tidak menemukan list items pada JSON response")

    rows: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        weight_raw = it.get("weight") or it.get("name") or it.get("variant_name") or it.get("title")
        gram = norm_gram(weight_raw)

        sell_raw = (
            it.get("price")
            or it.get("sell_price")
            or it.get("sellPrice")
            or it.get("selling_price")
            or it.get("sellingPrice")
        )
        sell = to_int(sell_raw)

        if gram and sell:
            rows.append({"gram": gram, "berat": weight_raw, "harga_jual": sell})

    df = pd.DataFrame(rows).drop_duplicates(subset=["gram", "harga_jual"], keep="last")
    if df.empty:
        raise RuntimeError("product-variants: items ditemukan tapi gagal parsing harga_jual")
    return df.sort_values(by=["harga_jual"], ascending=True, ignore_index=True)


# ----------------------
# BUYBACK: strategies
# ----------------------
def candidate_buyback_urls() -> List[str]:
    """
    Daftar kandidat endpoint buyback yang sering muncul.
    Kita "over-generate" karena backend bisa beda format.
    """
    p = CFG.page_path
    # beberapa variasi path/slug yang umum
    variants = [
        f"{CFG.base_url}/api/page-data?path={p}",
        f"{CFG.base_url}/api/page-data?path={p}/",
        f"{CFG.base_url}/api/page-data?path={p.lstrip('/')}",
        f"{CFG.base_url}/api/page-data?slug=harga-emas",
        f"{CFG.base_url}/api/page-data?path=/harga-emas",
        f"{CFG.base_url}/api/page-data?path=harga-emas",
        f"{CFG.base_url}/api/page-data?take=10000&path={p}",
        f"{CFG.base_url}/api/page-data?take=10000&path={p}/",
        f"{CFG.base_url}/api/page-data?take=10000&slug=harga-emas",
        # sometimes "page-data" is under different prefix (keep as optional)
        f"{CFG.base_url}/api/page-data?take=10000&path=%2Fharga-emas",
    ]
    # dedup preserve order
    seen = set()
    out = []
    for u in variants:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def walk_find_buyback_rows(obj: Any, out_rows: List[Dict[str, Any]]) -> None:
    """
    Heuristik: cari dict yang punya:
    - berat/weight/gram/denomination
    - harga jual/sell/price
    - buyback/buy back/harga buyback
    """
    if isinstance(obj, dict):
        keys_lower = {str(k).lower(): k for k in obj.keys()}

        # find keys
        w_key = next(
            (keys_lower[c] for c in ("berat", "weight", "gram", "denomination", "ukuran") if c in keys_lower),
            None,
        )
        sell_key = next(
            (
                keys_lower[c]
                for c in (
                    "harga_jual",
                    "harga jual",
                    "hargajual",
                    "sellingprice",
                    "sellprice",
                    "sell_price",
                    "price",
                    "jual",
                )
                if c in keys_lower
            ),
            None,
        )
        bb_key = next(
            (
                keys_lower[c]
                for c in (
                    "harga_buyback",
                    "harga buyback",
                    "hargabuyback",
                    "buybackprice",
                    "buyback_price",
                    "buyback",
                    "buy back",
                )
                if c in keys_lower
            ),
            None,
        )

        if w_key and (sell_key or bb_key) and bb_key:
            gram = norm_gram(obj.get(w_key))
            bb = to_int(obj.get(bb_key))
            sell = to_int(obj.get(sell_key)) if sell_key else None
            if gram and bb is not None:
                out_rows.append({"gram": gram, "harga_buyback": bb, "harga_jual_maybe": sell})

        for v in obj.values():
            walk_find_buyback_rows(v, out_rows)

    elif isinstance(obj, list):
        for v in obj:
            walk_find_buyback_rows(v, out_rows)


def buyback_map_from_payload(payload: Any) -> Dict[str, int]:
    rows: List[Dict[str, Any]] = []
    walk_find_buyback_rows(payload, rows)
    # map terakhir menang (biasanya yang paling bawah itu paling "final")
    m: Dict[str, int] = {}
    for r in rows:
        g = r.get("gram")
        bb = r.get("harga_buyback")
        if g and isinstance(bb, int):
            m[g] = bb
    return m


def fetch_buyback_by_url(
    sess: requests.Session,
    url: str,
    timeout: int,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, int], Dict[str, Any]]:
    status, final_url, rh, payload, snippet = safe_get(
        sess, url, timeout=timeout, expect_json=True, extra_headers=extra_headers
    )
    dbg = {
        "url": url,
        "status": status,
        "final_url": final_url,
        "content_type": rh.get("content-type", ""),
        "snippet": snippet,
    }
    if status != 200 or payload is None:
        return {}, dbg
    m = buyback_map_from_payload(payload)
    dbg["parsed_items"] = len(m)
    return m, dbg


def fetch_buyback_probe(
    sess: requests.Session,
    timeout: int,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    """
    Probe kandidat endpoint. Balik pertama yang berhasil parse buyback.
    """
    debug_rows: List[Dict[str, Any]] = []
    for u in candidate_buyback_urls():
        m, dbg = fetch_buyback_by_url(sess, u, timeout=timeout, extra_headers=extra_headers)
        debug_rows.append(dbg)
        if m:
            return m, debug_rows
    return {}, debug_rows


# ----------------------
# UI
# ----------------------
st.set_page_config(page_title="Harga Emas Galeri24", layout="wide")
st.title("📊 Harga Emas Galeri24 — Jual + Buyback")

with st.sidebar:
    st.header("Pengaturan")
    debug = st.toggle("Tampilkan debug detail", value=False)

    st.divider()
    st.subheader("Opsional: Override buyback URL")
    manual_buyback_url = st.text_input(
        "Buyback URL (kalau sudah ketemu dari DevTools)",
        placeholder="Contoh: https://galeri24.co.id/api/page-data?path=/harga-emas",
    )

    st.subheader("Opsional: Paste cURL (paling ampuh)")
    st.caption(
        "DevTools → Network → klik request yang berisi buyback → Copy as cURL, paste di sini."
    )
    curl_text = st.text_area("Paste cURL di sini", height=160, placeholder="curl 'https://...'\n  -H 'accept: ...'\n  ...")

    st.divider()
    st.subheader("Cache")
    if st.button("Clear cache & reload"):
        st.cache_data.clear()
        st.rerun()

st.caption("Jual: /api/product-variants | Buyback: probe /api/page-data (atau manual/cURL)")

# Prepare session (shared)
sess = new_session()

# If user pasted curl, override headers (and url optionally)
curl_url, curl_headers = parse_curl(curl_text.strip()) if curl_text.strip() else (None, {})
extra_headers = {k: v for k, v in curl_headers.items() if k.lower() not in ("host", "content-length")}

# Fetch sell prices
with st.spinner("Mengambil harga jual..."):
    df_sell = fetch_sell_prices()

# Determine buyback source
buyback_map: Dict[str, int] = {}
buyback_debug: List[Dict[str, Any]] = []

with st.spinner("Mengambil harga buyback (probe)..."):
    if manual_buyback_url.strip():
        buyback_map, dbg = fetch_buyback_by_url(
            sess,
            manual_buyback_url.strip(),
            timeout=CFG.timeout_sec,
            extra_headers=extra_headers or None,
        )
        buyback_debug = [dbg]
    elif curl_url:
        # Prefer curl_url (user copied exact request)
        buyback_map, dbg = fetch_buyback_by_url(
            sess,
            curl_url,
            timeout=CFG.timeout_sec,
            extra_headers=extra_headers or None,
        )
        buyback_debug = [dbg]
    else:
        buyback_map, buyback_debug = fetch_buyback_probe(
            sess, timeout=CFG.timeout_sec, extra_headers=extra_headers or None
        )

# Merge
df = df_sell.copy()
df["harga_buyback"] = df["gram"].map(buyback_map)

df["tanggal"] = datetime.now().strftime("%Y-%m-%d")
df["produk"] = "GALERI 24"
df_out = df[["tanggal", "produk", "gram", "berat", "harga_jual", "harga_buyback"]].copy()

# Display
c1, c2, c3, c4 = st.columns(4)
c1.metric("Jumlah Varian", f"{len(df_out):,}")

one = df[df["gram"] == "1"]
if not one.empty:
    c2.metric("Harga Jual 1 gr", f"Rp {int(one.iloc[0]['harga_jual']):,}")
    bb = one.iloc[0]["harga_buyback"]
    c3.metric("Buyback 1 gr", f"Rp {int(bb):,}" if pd.notna(bb) else "—")
else:
    c2.metric("Harga Jual 1 gr", "—")
    c3.metric("Buyback 1 gr", "—")

filled = int(df_out["harga_buyback"].notna().sum())
c4.metric("Buyback Terisi", f"{filled}/{len(df_out)}")

st.dataframe(df_out, use_container_width=True)

# Warnings / guidance
if df_out["harga_buyback"].isna().all():
    st.error("Buyback masih kosong.")
    st.info(
        "Yang perlu kamu ambil dari DevTools itu **request yang response-nya berisi angka buyback**.\n\n"
        "Cara cepat:\n"
        "1) Buka galeri24.co.id/harga-emas\n"
        "2) DevTools → Network → Filter: Fetch/XHR\n"
        "3) Klik satu-per-satu request yang statusnya 200\n"
        "4) Di tab **Preview/Response**, cari kata: buyback / 'harga buyback'\n"
        "5) Kalau sudah ketemu request yang benar → **Copy → Copy as cURL** → paste ke sidebar (Paste cURL)."
    )

# Debug section
if debug:
    st.subheader("🔎 Debug — Buyback probing")
    st.write("Extra headers from cURL (if any):")
    st.json(extra_headers or {})

    st.write("Probe results:")
    st.dataframe(pd.DataFrame(buyback_debug), use_container_width=True)

    st.subheader("🔎 Debug — Sell sample")
    st.write("Top 10 (sorted by harga_jual):")
    st.dataframe(df_sell.head(10), use_container_width=True)

    st.subheader("🔎 Debug — Buyback map sample")
    st.json(dict(list(buyback_map.items())[:20]))
