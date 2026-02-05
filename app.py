import requests
import pandas as pd
import streamlit as st
from datetime import datetime
import re
import json

# ======================
# CONFIG
# ======================
PAGE_URL = "https://galeri24.co.id/harga-emas"
BASE_URL = "https://galeri24.co.id"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}

# ======================
# STEP 1: GET BUILD ID
# ======================
def get_build_id(html: str) -> str:
    match = re.search(r'"buildId":"([^"]+)"', html)
    if not match:
        raise ValueError("buildId Next.js tidak ditemukan")
    return match.group(1)

# ======================
# STEP 2: FETCH NEXT DATA JSON
# ======================
def fetch_next_data(build_id: str) -> dict:
    json_url = f"{BASE_URL}/_next/data/{build_id}/harga-emas.json"

    r = requests.get(json_url, headers=HEADERS, timeout=20)
    r.raise_for_status()

    return r.json()

# ======================
# STEP 3: PARSE DATA
# ======================
def scrape_galeri24():
    # ambil HTML awal
    r = requests.get(PAGE_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()

    build_id = get_build_id(r.text)

    next_data = fetch_next_data(build_id)

    try:
        products = next_data["pageProps"]["data"]["products"]
    except KeyError:
        raise ValueError("Struktur JSON Galeri24 berubah")

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
st.caption("Sumber: galeri24.co.id – Next.js pre-render JSON")

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
