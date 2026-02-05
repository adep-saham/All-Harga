import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from datetime import datetime
import re
import json

# ======================
# CONFIG
# ======================
VENDOR_ID_GALERI24 = "d0fd1d95-ac0a-48d8-95f8-98bd9c5f9197"
API_VARIANTS = f"https://galeri24.co.id/api/product-variants?take=200&vendor_id={VENDOR_ID_GALERI24}"
PAGE_URL = "https://galeri24.co.id/harga-emas"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/144.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://galeri24.co.id/",
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
    s = str(x).lower()
    s = s.replace(",", ".")
    s = s.replace("gram", "").replace("gr", "").replace("g", "").strip()
    token = s.split()[0] if s.split() else ""
    token = "".join(ch for ch in token if (ch.isdigit() or ch == "."))
    return token if token else None

def find_items(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ["data", "items", "results", "result"]:
            v = payload.get(k)
            if isinstance(v, list):
                return v
        d = payload.get("data")
        if isinstance(d, dict):
            for k in ["items", "results", "result"]:
                v = d.get(k)
                if isinstance(v, list):
                    return v
    return None

# ======================
# SELL FROM product-variants (sudah OK di kamu)
# ======================
def fetch_sell_prices():
    r = requests.get(API_VARIANTS, headers=HEADERS, timeout=30)
    r.raise_for_status()
    payload = r.json()

    items = find_items(payload)
    if not isinstance(items, list):
        raise ValueError("Response product-variants tidak berformat list (cek struktur JSON)")

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
        raise ValueError("Harga jual kosong setelah parsing product-variants")
    return df

# ======================
# BUYBACK FROM Nuxt payload in /harga-emas
# ======================
def extract_buyback_from_any(obj, out):
    """
    Rekursif: cari dict yang punya (weight/berat) dan (buyback*)
    """
    if isinstance(obj, dict):
        keys = {k.lower(): k for k in obj.keys()}

        # cari key weight/berat
        weight_key = None
        for cand in ["weight", "berat", "gram"]:
            if cand in keys:
                weight_key = keys[cand]
                break

        # cari key buyback
        buy_key = None
        for k in obj.keys():
            if "buyback" in str(k).lower():
                buy_key = k
                break

        if weight_key and buy_key:
            gram = norm_gram(obj.get(weight_key))
            bb = to_int(obj.get(buy_key))
            if gram and bb:
                out[gram] = bb

        for v in obj.values():
            extract_buyback_from_any(v, out)

    elif isinstance(obj, list):
        for v in obj:
            extract_buyback_from_any(v, out)

def fetch_buyback_map_from_nuxt():
    r = requests.get(PAGE_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()

    html = r.text
    soup = BeautifulSoup(html, "html.parser")

    # 1) Nuxt 3: __NUXT_DATA__ (JSON)
    nuxt_data = soup.find("script", id="__NUXT_DATA__")
    if nuxt_data and (nuxt_data.string or "").strip():
        jd = json.loads(nuxt_data.string)
        out = {}
        extract_buyback_from_any(jd, out)
        if out:
            return out

    # 2) Nuxt 2: window.__NUXT__ = {...}
    # (coba regex, kadang JSON-compatible)
    scripts = soup.find_all("script")
    for sc in scripts:
        txt = sc.string or ""
        if "window.__NUXT__" in txt:
            m = re.search(r"window\.__NUXT__\s*=\s*(\{.*\})\s*;?\s*$", txt.strip(), re.DOTALL)
            if m:
                raw = m.group(1)
                # perapihan minimal (undefined -> null)
                raw = raw.replace("undefined", "null")
                try:
                    jd = json.loads(raw)
                    out = {}
                    extract_buyback_from_any(jd, out)
                    if out:
                        return out
                except Exception:
                    pass

    # kalau tidak ketemu
    return {}

# ======================
# STREAMLIT UI
# ======================
st.set_page_config(page_title="Harga Emas Galeri 24", layout="wide")
st.title("📊 Harga Emas Galeri 24 (Jual + Buyback)")
st.caption("Jual: product-variants | Buyback: Nuxt payload dari /harga-emas")

with st.expander("🔧 Debug URL"):
    st.code(API_VARIANTS)
    st.code(PAGE_URL)

try:
    df_sell = fetch_sell_prices()

    buyback_map = fetch_buyback_map_from_nuxt()

    with st.expander("🧾 Debug: buyback_map sample"):
        # tampilkan 20 item pertama
        st.write(dict(list(buyback_map.items())[:20]))

    df_sell["harga_buyback"] = df_sell["gram"].map(buyback_map)

    df_sell["tanggal"] = datetime.now().strftime("%Y-%m-%d")
    df_sell["produk"] = "GALERI 24"

    df = df_sell[["tanggal", "produk", "berat", "harga_jual", "harga_buyback"]]

    st.success("✅ Data berhasil diambil")
    st.dataframe(df, use_container_width=True)

    col1, col2, col3 = st.columns(3)
    col1.metric("Jumlah Varian", len(df))

    one = df_sell[df_sell["gram"] == "1"]
    if not one.empty:
        col2.metric("Harga Jual 1 gr", f"Rp {int(one.iloc[0]['harga_jual']):,}")
        bb = one.iloc[0]["harga_buyback"]
        col3.metric("Buyback 1 gr", f"Rp {int(bb):,}" if pd.notna(bb) else "—")
    else:
        col2.metric("Harga Jual 1 gr", "—")
        col3.metric("Buyback 1 gr", "—")

    if df["harga_buyback"].isna().all():
        st.warning(
            "Buyback masih kosong. Ini berarti payload Nuxt di server tidak memuat data buyback "
            "(kemungkinan buyback diambil dari XHR lain setelah load)."
        )
        st.info("Kalau ini terjadi, kita ambil buyback dari request XHR yang kamu lihat di Network (yang berisi tabel buyback).")

except Exception as e:
    st.error("❌ Gagal ambil data")
    st.exception(e)
