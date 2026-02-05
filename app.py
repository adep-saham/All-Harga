import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from datetime import datetime
import re

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
    )
}

# ======================
# UTIL
# ======================
def to_int(text):
    if text is None:
        return None
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else None

def norm_gram(x):
    s = str(x).lower()
    s = s.replace("gram", "").replace("gr", "").strip()
    return s.split()[0]

# ======================
# 1️⃣ HARGA JUAL (API)
# ======================
def fetch_sell_prices():
    r = requests.get(API_VARIANTS, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()

    items = data.get("data", [])
    rows = []

    for it in items:
        name = it.get("name", "")
        weight = it.get("weight") or name
        price = it.get("price") or it.get("sell_price")

        if not price:
            continue

        rows.append({
            "gram": norm_gram(weight),
            "berat": weight,
            "harga_jual": int(price)
        })

    return pd.DataFrame(rows)

# ======================
# 2️⃣ HARGA BUYBACK (HTML TABLE)
# ======================
def fetch_buyback_prices():
    r = requests.get(PAGE_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    table = soup.find("table")
    if not table:
        raise ValueError("Tabel harga tidak ditemukan di HTML")

    rows = table.find_all("tr")[1:]  # skip header
    data = []

    for tr in rows:
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) < 3:
            continue

        gram = norm_gram(tds[0])
        buyback = to_int(tds[2])

        data.append({
            "gram": gram,
            "harga_buyback": buyback
        })

    return pd.DataFrame(data)

# ======================
# STREAMLIT UI
# ======================
st.set_page_config(page_title="Harga Emas Galeri 24", layout="wide")
st.title("📊 Harga Emas Galeri 24 (FINAL)")
st.caption("Harga Jual dari API + Buyback dari HTML resmi Galeri24")

try:
    df_sell = fetch_sell_prices()
    df_buy = fetch_buyback_prices()

    df = df_sell.merge(df_buy, on="gram", how="left")
    df["tanggal"] = datetime.now().strftime("%Y-%m-%d")
    df["produk"] = "GALERI 24"

    df = df[["tanggal", "produk", "berat", "harga_jual", "harga_buyback"]]

    st.success("✅ Harga jual & buyback berhasil diambil")
    st.dataframe(df, use_container_width=True)

    # Ringkasan
    col1, col2, col3 = st.columns(3)
    col1.metric("Jumlah Varian", len(df))

    one = df[df["berat"].astype(str).str.startswith("1")]
    if not one.empty:
        col2.metric("Harga Jual 1 gr", f"Rp {int(one.iloc[0]['harga_jual']):,}")
        col3.metric("Buyback 1 gr", f"Rp {int(one.iloc[0]['harga_buyback']):,}")

except Exception as e:
    st.error("❌ Gagal ambil data")
    st.exception(e)
