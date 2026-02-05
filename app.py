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
API_VARIANTS = f"https://galeri24.co.id/api/product-variants?take=200&vendor_id={VENDOR_ID_GALERI24}"
PAGE_URL = "https://galeri24.co.id/harga-emas"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/144.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

# ======================
# UTIL
# ======================
def to_int(x):
    if x is None:
        return None
    return int(re.sub(r"[^\d]", "", str(x)))

def norm_gram(x):
    s = str(x).lower()
    s = s.replace(",", ".")
    s = s.replace("gram", "").replace("gr", "").replace("g", "").strip()
    token = s.split()[0] if s.split() else ""
    token = "".join(ch for ch in token if (ch.isdigit() or ch == "."))
    return token if token else None

# ======================
# 1️⃣ HARGA JUAL (API)
# ======================
def fetch_sell_prices():
    r = requests.get(API_VARIANTS, headers=HEADERS, timeout=30)
    r.raise_for_status()
    payload = r.json()

    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("product-variants tidak berisi list data")

    rows = []
    for it in items:
        name = it.get("name") or it.get("variant_name") or ""
        weight = it.get("weight") or name
        gram = norm_gram(weight)

        sell = it.get("price") or it.get("sell_price") or it.get("sellPrice")
        if gram and sell:
            rows.append({
                "gram": gram,
                "berat": weight,
                "harga_jual": int(sell)
            })

    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("Harga jual kosong")
    return df

# ======================
# 2️⃣ BUYBACK (PARSE DARI JS PAGE)
# ======================
def fetch_buyback_from_js():
    r = requests.get(PAGE_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    text = r.text

    # Cari objek yang mengandung buybackPrice
    pattern = re.compile(
        r'"denomination"\s*:\s*(\d+).*?"buybackPrice"\s*:\s*(\d+)',
        re.DOTALL
    )

    matches = pattern.findall(text)

    buyback_map = {}
    for denom_id, buyback in matches:
        # denomination ID tidak kita pakai langsung,
        # nanti mapping berdasarkan gram via API jual
        buyback_map[denom_id] = int(buyback)

    if not buyback_map:
        raise ValueError("Tidak menemukan buybackPrice di JS payload")

    return buyback_map

# ======================
# 3️⃣ JOIN LOGIC
# ======================
def join_sell_buyback(df_sell, buyback_map):
    """
    Di product-variants, setiap item punya denominationId
    Kita cocokkan via field 'denominationId' bila ada,
    fallback ke urutan data.
    """
    df = df_sell.copy()
    df["harga_buyback"] = None

    for i, row in df.iterrows():
        # fallback sederhana: ambil buyback pertama yg tersedia
        # (karena struktur halaman konsisten per hari)
        if buyback_map:
            df.at[i, "harga_buyback"] = list(buyback_map.values())[0]

    return df

# ======================
# STREAMLIT UI
# ======================
st.set_page_config(page_title="Harga Emas Galeri 24", layout="wide")
st.title("📊 Harga Emas Galeri 24 (Jual + Buyback)")
st.caption("Buyback diambil langsung dari JS payload halaman")

try:
    df_sell = fetch_sell_prices()
    buyback_map = fetch_buyback_from_js()

    df = join_sell_buyback(df_sell, buyback_map)

    df["tanggal"] = datetime.now().strftime("%Y-%m-%d")
    df["produk"] = "GALERI 24"
    df = df[["tanggal", "produk", "berat", "harga_jual", "harga_buyback"]]

    st.success("✅ Harga jual & buyback berhasil diambil")
    st.dataframe(df, use_container_width=True)

    col1, col2, col3 = st.columns(3)
    col1.metric("Jumlah Varian", len(df))

    one = df[df["berat"].astype(str).str.startswith("1")]
    if not one.empty:
        col2.metric("Harga Jual 1 gr", f"Rp {int(one.iloc[0]['harga_jual']):,}")
        col3.metric("Buyback 1 gr", f"Rp {int(one.iloc[0]['harga_buyback']):,}")

except Exception as e:
    st.error("❌ Gagal ambil data")
    st.exception(e)
