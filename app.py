import requests
import pandas as pd
import streamlit as st
from datetime import datetime

# ======================
# CONFIG
# ======================
API_URL = "https://galeri24.co.id/api/emas/harga"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

# ======================
# SCRAPER VIA API
# ======================
def scrape_galeri24():
    r = requests.get(API_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()

    json_data = r.json()

    if not json_data or "data" not in json_data:
        raise ValueError("Format API tidak sesuai")

    records = []
    for item in json_data["data"]:
        records.append({
            "tanggal": datetime.now().strftime("%Y-%m-%d"),
            "produk": "Galeri 24",
            "berat": item.get("weight"),
            "harga_jual": int(item.get("sell_price", 0)),
            "harga_buyback": int(item.get("buyback_price", 0))
        })

    if not records:
        raise ValueError("Data kosong dari API")

    return pd.DataFrame(records)

# ======================
# STREAMLIT UI
# ======================
st.set_page_config(page_title="Harga Emas Galeri 24", layout="wide")
st.title("📊 Harga Emas Galeri 24 (Live)")
st.caption("Sumber: galeri24.co.id – data via API internal")

try:
    df = scrape_galeri24()

    st.success("✅ Data berhasil diambil")
    st.dataframe(df, use_container_width=True)

    st.subheader("🔎 Ringkasan")
    col1, col2 = st.columns(2)

    col1.metric("Jumlah Varian", len(df))

    harga_1g = df[df["berat"] == "1"]["harga_jual"].iloc[0]
    col2.metric("Harga Jual 1 gr", f"Rp {harga_1g:,}")

except Exception as e:
    st.error("❌ Terjadi error saat scraping")
    st.exception(e)
