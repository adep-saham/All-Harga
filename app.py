import requests
import pandas as pd
import streamlit as st
from datetime import datetime

# ======================
# CONFIG
# ======================
API_URL = (
    "https://galeri24.co.id/api/product-variants"
    "?take=100"
    "&vendor_id=d0fd1d95-ac0a-48d8-95f8-98bd9c5f9197"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/144.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# ======================
# SCRAPER
# ======================
def scrape_galeri24():
    r = requests.get(API_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()

    json_data = r.json()

    if "data" not in json_data:
        raise ValueError("Field 'data' tidak ditemukan di response")

    records = []
    for item in json_data["data"]:
        # field umum product-variants
        berat = item.get("weight") or item.get("variant_name")
        harga_jual = item.get("price") or item.get("sell_price")
        harga_buyback = item.get("buyback_price")

        # skip item non-emas
        if not berat or not harga_jual:
            continue

        records.append({
            "tanggal": datetime.now().strftime("%Y-%m-%d"),
            "produk": "GALERI 24",
            "berat": str(berat),
            "harga_jual": int(harga_jual),
            "harga_buyback": int(harga_buyback) if harga_buyback else None
        })

    if not records:
        raise ValueError("Data kosong setelah parsing")

    return pd.DataFrame(records)

# ======================
# STREAMLIT UI
# ======================
st.set_page_config(page_title="Harga Emas Galeri 24", layout="wide")
st.title("📊 Harga Emas Galeri 24 (LIVE)")
st.caption("Sumber: galeri24.co.id – API product-variants")

try:
    df = scrape_galeri24()

    st.success("✅ Data harga GALERI 24 berhasil diambil")
    st.dataframe(df, use_container_width=True)

    st.subheader("🔎 Ringkasan")
    col1, col2 = st.columns(2)

    col1.metric("Jumlah Varian", len(df))

    if "1" in df["berat"].values:
        harga_1g = df[df["berat"] == "1"]["harga_jual"].iloc[0]
        col2.metric("Harga Jual 1 gr", f"Rp {harga_1g:,}")

except Exception as e:
    st.error("❌ Gagal ambil data harga")
    st.exception(e)
