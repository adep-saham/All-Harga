import requests
import pandas as pd
import streamlit as st
from datetime import datetime

API_URL = "https://galeri24.co.id/api/product-variants?take=100"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

def scrape_galeri24():
    r = requests.get(API_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()

    data = r.json()

    records = []
    for item in data.get("data", []):
        records.append({
            "tanggal": datetime.now().strftime("%Y-%m-%d"),
            "produk": item.get("vendor", {}).get("name", "Galeri 24"),
            "berat": item.get("weight"),
            "harga_jual": item.get("price"),
            "harga_buyback": item.get("buyback_price"),
        })

    if not records:
        raise ValueError("Data kosong dari API product-variants")

    return pd.DataFrame(records)

# ======================
# STREAMLIT
# ======================
st.title("📊 Harga Emas Galeri 24 (XHR API)")

try:
    df = scrape_galeri24()
    st.success("✅ Data berhasil diambil dari API backend")
    st.dataframe(df, use_container_width=True)

except Exception as e:
    st.error("❌ Gagal ambil data")
    st.exception(e)
