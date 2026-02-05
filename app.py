import requests
import pandas as pd
import streamlit as st
from datetime import datetime

# ======================
# STREAMLIT CONFIG
# ======================
st.set_page_config(page_title="Harga Emas Galeri 24 (XHR)", layout="wide")
st.title("📊 Harga Emas Galeri 24 (XHR API)")
st.caption("Sumber: galeri24.co.id – data dari Network (Fetch/XHR)")

st.markdown("""
**Cara pakai:**
1. Buka `galeri24.co.id/harga-emas`
2. DevTools → Network → Fetch/XHR
3. Klik request `page-data` / `product-variants`
4. Copy **Request URL**
5. Paste di bawah
""")

# ======================
# INPUT URL
# ======================
api_url = st.text_input(
    "Paste Request URL (XHR) dari Network tab",
    placeholder="https://galeri24.co.id/...."
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest"
}

# ======================
# FETCH DATA
# ======================
def fetch_xhr_data(url: str):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()

def parse_galeri24(json_data: dict):
    """
    Parser fleksibel:
    - page-data
    - product-variants
    """

    records = []

    # CASE 1: product-variants
    if "data" in json_data and isinstance(json_data["data"], list):
        items = json_data["data"]

    # CASE 2: page-data (nested)
    elif "data" in json_data and "items" in json_data["data"]:
        items = json_data["data"]["items"]

    else:
        raise ValueError("Struktur JSON tidak dikenali")

    for item in items:
        berat = (
            item.get("weight")
            or item.get("variant_name")
            or item.get("name")
        )

        harga_jual = (
            item.get("price")
            or item.get("sell_price")
            or item.get("harga_jual")
        )

        harga_buyback = (
            item.get("buyback_price")
            or item.get("harga_buyback")
        )

        # skip kalau bukan emas batangan
        if not berat or not harga_jual:
            continue

        records.append({
            "tanggal": datetime.now().strftime("%Y-%m-%d"),
            "produk": "Galeri 24",
            "berat": str(berat),
            "harga_jual": int(harga_jual),
            "harga_buyback": int(harga_buyback) if harga_buyback else None
        })

    if not records:
        raise ValueError("Data kosong setelah parsing")

    return pd.DataFrame(records)

# ======================
# ACTION
# ======================
if api_url:
    try:
        json_data = fetch_xhr_data(api_url)
        df = parse_galeri24(json_data)

        st.success("✅ Data berhasil diambil dari XHR API")
        st.dataframe(df, use_container_width=True)

        st.subheader("🔎 Ringkasan")
        col1, col2 = st.columns(2)
        col1.metric("Jumlah Varian", len(df))

        if "1" in df["berat"].astype(str).values:
            harga_1g = df[df["berat"].astype(str) == "1"]["harga_jual"].iloc[0]
            col2.metric("Harga Jual 1 gr", f"Rp {harga_1g:,}")

    except Exception as e:
        st.error("❌ Gagal ambil / parse data")
        st.exception(e)
