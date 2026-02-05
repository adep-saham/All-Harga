import requests
import pandas as pd
import streamlit as st
from datetime import datetime
import json
from bs4 import BeautifulSoup

# ======================
# CONFIG
# ======================
URL = "https://galeri24.co.id/harga-emas"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# ======================
# SCRAPER NEXT.JS
# ======================
def scrape_galeri24():
    r = requests.get(URL, headers=HEADERS, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    next_data = soup.find("script", id="__NEXT_DATA__")
    if not next_data:
        raise ValueError("__NEXT_DATA__ tidak ditemukan")

    json_data = json.loads(next_data.string)

    # 🔍 struktur data Galeri24 (Next.js props)
    try:
        products = (
            json_data["props"]["pageProps"]["data"]["products"]
        )
    except KeyError:
        raise ValueError("Struktur data Next.js berubah")

    records = []
    for item in products:
        records.append({
            "tanggal": datetime.now().strftime("%Y-%m-%d"),
            "produk": "Galeri 24",
            "berat": item.get("weight"),
            "harga_jual": int(item.get("sell_price", 0)),
            "harga_buyback": int(item.get("buyback_price", 0)),
        })

    if not records:
        raise ValueError("Data harga kosong")

    return pd.DataFrame(records)

# ======================
# STREAMLIT UI
# ======================
st.set_page_config(page_title="Harga Emas Galeri 24", layout="wide")
st.title("📊 Harga Emas Galeri 24 (Live)")
st.caption("Sumber: galeri24.co.id – data dari __NEXT_DATA__ (Next.js)")

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
