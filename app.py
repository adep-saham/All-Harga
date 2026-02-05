import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import re
import streamlit as st

# ======================
# CONFIG
# ======================
URL = "https://galeri24.co.id/harga-emas"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

# ======================
# UTIL
# ======================
def clean_price(text):
    if not text:
        return None
    return int(re.sub(r"[^\d]", "", text))

# ======================
# SCRAPER
# ======================
def scrape_galeri24():
    res = requests.get(URL, headers=HEADERS, timeout=20)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")

    table = soup.find("table")
    if not table:
        raise ValueError("❌ Tabel harga emas tidak ditemukan")

    # tidak pakai <tbody> (AMAN)
    rows = table.find_all("tr")[1:]  # skip header

    data = []
    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) < 3:
            continue

        data.append({
            "tanggal": datetime.now().strftime("%Y-%m-%d"),
            "produk": "Galeri 24",
            "berat": cols[0],
            "harga_jual": clean_price(cols[1]),
            "harga_buyback": clean_price(cols[2])
        })

    if not data:
        raise ValueError("❌ Data kosong – kemungkinan struktur web berubah")

    return pd.DataFrame(data)

# ======================
# STREAMLIT UI
# ======================
st.set_page_config(page_title="Harga Emas Galeri 24", layout="wide")
st.title("📊 Harga Emas Galeri 24 (Live)")

st.caption("Sumber: galeri24.co.id – hanya ditampilkan, belum disimpan")

try:
    df = scrape_galeri24()

    st.success("✅ Data berhasil diambil")
    st.dataframe(df, use_container_width=True)

    # ringkasan cepat
    st.subheader("🔎 Ringkasan")
    col1, col2 = st.columns(2)
    col1.metric("Jumlah Varian", len(df))
    col2.metric(
        "Harga Jual 1 gr",
        f"Rp {df[df['berat'].str.contains('1')]['harga_jual'].iloc[0]:,}"
    )

except Exception as e:
    st.error("❌ Terjadi error saat scraping")
    st.exception(e)
