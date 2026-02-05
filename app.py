import requests
import pandas as pd
import streamlit as st
from datetime import datetime
import re
import json

URL = "https://galeri24.co.id/harga-emas"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

def extract_prices_from_script(html: str):
    """
    Galeri24 inject data harga via JavaScript.
    Kita tarik JSON-nya dari <script>.
    """

    # cari pola array harga
    pattern = re.compile(r"var\s+hargaEmas\s*=\s*(\[.*?\]);", re.S)
    match = pattern.search(html)

    if not match:
        raise ValueError("Data harga tidak ditemukan di script")

    raw_json = match.group(1)

    # parse JSON
    data = json.loads(raw_json)

    records = []
    for item in data:
        records.append({
            "tanggal": datetime.now().strftime("%Y-%m-%d"),
            "produk": "Galeri 24",
            "berat": item.get("berat"),
            "harga_jual": int(item.get("hargaJual", 0)),
            "harga_buyback": int(item.get("hargaBuyback", 0))
        })

    return pd.DataFrame(records)

def scrape_galeri24():
    r = requests.get(URL, headers=HEADERS, timeout=20)
    r.raise_for_status()

    html = r.text
    return extract_prices_from_script(html)

# ======================
# STREAMLIT UI
# ======================
st.set_page_config(page_title="Harga Emas Galeri 24", layout="wide")
st.title("📊 Harga Emas Galeri 24 (Live)")
st.caption("Sumber: galeri24.co.id – data diambil dari script JS")

try:
    df = scrape_galeri24()

    st.success("✅ Data berhasil diambil")
    st.dataframe(df, use_container_width=True)

    st.subheader("🔎 Ringkasan")
    col1, col2 = st.columns(2)
    col1.metric("Jumlah Varian", len(df))

    harga_1g = df[df["berat"].astype(str).str.contains("1")]["harga_jual"].iloc[0]
    col2.metric("Harga Jual 1 gr", f"Rp {harga_1g:,}")

except Exception as e:
    st.error("❌ Terjadi error saat scraping")
    st.exception(e)
