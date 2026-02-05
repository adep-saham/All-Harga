import requests
import pandas as pd
import streamlit as st
from datetime import datetime
import re
import json

# ======================
# CONFIG
# ======================
VENDOR_ID_GALERI24 = "d0fd1d95-ac0a-48d8-95f8-98bd9c5f9197"

API_VARIANTS = f"https://galeri24.co.id/api/product-variants?take=300&vendor_id={VENDOR_ID_GALERI24}"

# BUYBACK biasanya ada di page-data (sesuai yang terlihat di Network list kamu)
PAGE_DATA_CANDIDATES = [
    "https://galeri24.co.id/api/page-data?take=10000&slug=harga-emas",
    "https://galeri24.co.id/api/page-data?slug=harga-emas",
    "https://galeri24.co.id/api/page-data?path=/harga-emas",
    "https://galeri24.co.id/api/page-data?take=10000&path=/harga-emas",
]

PAGE_URL = "https://galeri24.co.id/harga-emas"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/144.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://galeri24.co.id/harga-emas",
}

# ======================
# UTIL
# ======================
def to_int(x):
    try:
        if x is None:
            return None
        if isinstance(x, str):
            digits = re.sub(r"[^\d]", "", x)
            return int(digits) if digits else None
        return int(x)
    except Exception:
        return None

def norm_gram(x):
    """
    "1 Gram - Black Gold Series" -> "1"
    "0.5 Gram" -> "0.5"
    "2,3 gr" -> "2.3"
    """
    s = str(x).lower().replace(",", ".")
    s = s.replace("gram", "").replace("gr", "").replace("g", "").strip()
    token = s.split()[0] if s.split() else ""
    token = "".join(ch for ch in token if (ch.isdigit() or ch == "."))
    return token if token else None

def http_get(url: str):
    r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
    return r

def find_items(payload):
    """
    Robust: cari list dari dict/list apapun.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ["data", "items", "results", "result"]:
            v = payload.get(k)
            if isinstance(v, list):
                return v
        # nested dict
        d = payload.get("data")
        if isinstance(d, dict):
            for k in ["items", "results", "result"]:
                v = d.get(k)
                if isinstance(v, list):
                    return v
    return None

def walk_find_rows(obj, rows_out):
    """
    Cari struktur yang punya berat/weight dan harga_jual & harga_buyback
    di JSON page-data (heuristik).
    """
    if isinstance(obj, dict):
        keys_lower = {k.lower(): k for k in obj.keys()}

        # kandidat field berat
        w_key = None
        for cand in ["berat", "weight", "gram", "denomination", "ukuran"]:
            if cand in keys_lower:
                w_key = keys_lower[cand]
                break

        # kandidat field jual
        sell_key = None
        for cand in ["harga jual", "hargajual", "sellingprice", "sellprice", "price", "jual"]:
            if cand in keys_lower:
                sell_key = keys_lower[cand]
                break

        # kandidat field buyback
        bb_key = None
        for cand in ["harga buyback", "hargabuyback", "buybackprice", "buyback", "buy back"]:
            if cand in keys_lower:
                bb_key = keys_lower[cand]
                break

        if w_key and sell_key and bb_key:
            gram = norm_gram(obj.get(w_key))
            sell = to_int(obj.get(sell_key))
            bb = to_int(obj.get(bb_key))
            if gram and sell:
                rows_out.append({"gram": gram, "harga_jual": sell, "harga_buyback": bb})

        # traverse
        for v in obj.values():
            walk_find_rows(v, rows_out)

    elif isinstance(obj, list):
        for v in obj:
            walk_find_rows(v, rows_out)

# ======================
# SELL: product-variants (ROBUST + DEBUG)
# ======================
def fetch_sell_prices():
    r = http_get(API_VARIANTS)

    with st.expander("🧾 Debug: product-variants response"):
        st.write("URL:", API_VARIANTS)
        st.write("Status:", r.status_code)
        st.write("Final URL:", r.url)
        st.write("Content-Type:", r.headers.get("content-type", ""))
        st.code(r.text[:2500])

    r.raise_for_status()

    try:
        payload = r.json()
    except Exception:
        raise ValueError("product-variants tidak mengembalikan JSON (lihat debug)")

    items = find_items(payload)
    if not isinstance(items, list):
        raise ValueError("product-variants: tidak menemukan list items (lihat debug JSON)")

    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        weight = it.get("weight") or it.get("name") or it.get("variant_name")
        gram = norm_gram(weight)

        sell = (
            it.get("price")
            or it.get("sell_price")
            or it.get("sellPrice")
            or it.get("selling_price")
            or it.get("sellingPrice")
        )
        sell = to_int(sell)

        if gram and sell:
            rows.append({"gram": gram, "berat": weight, "harga_jual": sell})

    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("product-variants: items ada tapi harga_jual kosong (field beda)")

    return df

# ======================
# BUYBACK: page-data (ROBUST + DEBUG)
# ======================
def fetch_buyback_from_page_data():
    last_err = None
    for url in PAGE_DATA_CANDIDATES:
        try:
            r = http_get(url)

            with st.expander(f"🧾 Debug: page-data response ({url})"):
                st.write("Status:", r.status_code)
                st.write("Final URL:", r.url)
                st.write("Content-Type:", r.headers.get("content-type", ""))
                st.code(r.text[:2500])

            if r.status_code != 200:
                last_err = f"{url} -> {r.status_code}"
                continue

            payload = r.json()
            rows = []
            walk_find_rows(payload, rows)

            if rows:
                # dedup by gram (ambil terakhir yang non-null)
                m = {}
                for row in rows:
                    m[row["gram"]] = row["harga_buyback"]
                return m

            last_err = f"{url} -> JSON ok tapi pola berat/jual/buyback tidak ketemu"
        except Exception as e:
            last_err = f"{url} -> {e}"

    return {}, last_err

# ======================
# BUYBACK fallback: scan HTML text for buybackPrice (opsional)
# ======================
def fetch_buyback_from_html_scan():
    r = http_get(PAGE_URL)

    with st.expander("🧾 Debug: /harga-emas (HTML head)"):
        st.write("Status:", r.status_code)
        st.write("Final URL:", r.url)
        st.write("Content-Type:", r.headers.get("content-type", ""))
        st.write("HTML length:", len(r.text))
        st.code(r.text[:2500])

    if r.status_code != 200:
        return {}

    text = r.text

    # Heuristik: cari pasangan (gram, buyback) dalam bentuk string Rp / angka
    # (kalau memang ada)
    pattern = re.compile(r'(?i)(?:^|[^\d])(\d+(?:\.\d+)?)\s*(?:gr|gram)[^0-9]{0,80}Rp\.?\s*([\d\.\,]+)', re.MULTILINE)
    # Ini sering false-positive; hanya fallback terakhir
    out = {}
    for g, val in pattern.findall(text):
        gram = norm_gram(g)
        bb = to_int(val)
        if gram and bb:
            out[gram] = bb

    return out

# ======================
# UI
# ======================
st.set_page_config(page_title="Harga Emas Galeri 24", layout="wide")
st.title("📊 Harga Emas Galeri 24 (Jual + Buyback)")
st.caption("Jual: API product-variants | Buyback: API page-data (fallback scan HTML)")

try:
    df_sell = fetch_sell_prices()

    buyback_map, info = fetch_buyback_from_page_data()
    if not buyback_map:
        st.warning("Buyback belum ketemu dari page-data. Coba fallback scan HTML (kemungkinan kecil).")
        if info:
            st.info(f"Info terakhir: {info}")
        buyback_map = fetch_buyback_from_html_scan()

    df = df_sell.copy()
    df["harga_buyback"] = df["gram"].map(buyback_map)

    df["tanggal"] = datetime.now().strftime("%Y-%m-%d")
    df["produk"] = "GALERI 24"
    df_out = df[["tanggal", "produk", "berat", "harga_jual", "harga_buyback"]]

    st.success("✅ Data berhasil diambil (buyback akan terisi jika sumber ditemukan)")
    st.dataframe(df_out, use_container_width=True)

    col1, col2, col3 = st.columns(3)
    col1.metric("Jumlah Varian", len(df_out))

    one = df[df["gram"] == "1"]
    if not one.empty:
        col2.metric("Harga Jual 1 gr", f"Rp {int(one.iloc[0]['harga_jual']):,}")
        bb = one.iloc[0]["harga_buyback"]
        col3.metric("Buyback 1 gr", f"Rp {int(bb):,}" if pd.notna(bb) else "—")
    else:
        col2.metric("Harga Jual 1 gr", "—")
        col3.metric("Buyback 1 gr", "—")

    if df_out["harga_buyback"].isna().all():
        st.error("Buyback masih kosong. Ini berarti endpoint page-data yang benar belum kita temukan / pola JSON-nya berbeda.")
        st.info("Solusi pasti: kirim 1 Request URL XHR 'page-data?...' yang kamu lihat di Network (yang Response-nya mengandung buyback).")

except Exception as e:
    st.error("❌ Gagal ambil data")
    st.exception(e)
