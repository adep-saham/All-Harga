import streamlit as st
import requests
import pandas as pd
import re
from datetime import datetime
from bs4 import BeautifulSoup

URL = "https://galeri24.co.id/harga-emas"

st.set_page_config(page_title="Harga Emas Galeri24", layout="wide")
st.title("Harga Emas Galeri24")
st.caption(URL)

# ======================
# HELPERS
# ======================
def rupiah_to_int(s):
    s = s.replace("Rp", "").replace(".", "").replace(" ", "")
    return int(s) if s.isdigit() else 0

def format_rp(x):
    return f"Rp{int(x):,}".replace(",", ".")

WEIGHT_ORDER = [0.5, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000]
WEIGHT_RANK = {w: i for i, w in enumerate(WEIGHT_ORDER)}

def weight_sort_key(w):
    return WEIGHT_RANK.get(w, 999), w

def parse_update_label(text):
    m = re.search(r"(Diperbarui\s+[A-Za-z]+,\s*\d+\s+[A-Za-z]+\s+\d{4})", text)
    return m.group(1) if m else "Diperbarui"

# ======================
# FETCH
# ======================
@st.cache_data(ttl=300)
def fetch_html():
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "id-ID,id;q=0.9",
    }
    r = requests.get(URL, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text

# ======================
# PARSER (REGEX BLOCK)
# ======================
def scrape_prices(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    update_label = parse_update_label(text)

    vendors = [
        "GALERI 24", "DINAR G24", "BABY GALERI 24", "ANTAM",
        "UBS", "ANTAM MULIA RETRO", "ANTAM NON PEGADAIAN",
        "LOTUS ARCHI", "UBS DISNEY", "UBS ELSA", "UBS ANNA",
        "UBS MICKEY FULLBODY", "LOTUS ARCHI GIFT",
        "UBS HELLO KITTY", "BABY SERIES", "TUMBUHAN",
        "BABY SERIES INVESTASI", "BATIK SERIES"
    ]

    rows = []

    for v in vendors:
        pattern_block = rf"Harga {v}(.*?)(Diperbarui|Harga [A-Z])"
        m = re.search(pattern_block, text)
        if not m:
            continue

        block = m.group(1)

        # Pattern: weight + Rp jual + Rp buyback
        matches = re.findall(
            r"(\d+(?:\.\d+)?)\s+Rp([\d\.]+)\s+Rp([\d\.]+)",
            block
        )

        for w, sell, buyback in matches:
            w = float(w)
            if not (0.5 <= w <= 1000):
                continue

            rows.append({
                "vendor": v,
                "weight_g": w,
                "sell_idr": rupiah_to_int("Rp" + sell),
                "buyback_idr": rupiah_to_int("Rp" + buyback),
            })

    if not rows:
        raise RuntimeError("Parser gagal: tidak menemukan pasangan berat + harga")

    df = pd.DataFrame(rows).drop_duplicates()
    df["sort"] = df["weight_g"].apply(weight_sort_key)
    df = df.sort_values(["vendor", "sort"]).drop(columns="sort")

    return df, update_label

# ======================
# UI
# ======================
if st.button("Ambil data sekarang"):
    try:
        html = fetch_html()
        df, update_label = scrape_prices(html)

        st.subheader(update_label)

        vendors = df["vendor"].unique().tolist()
        st.sidebar.header("Vendor")
        selected = st.sidebar.multiselect("Pilih Vendor", vendors, default=vendors)

        for v in selected:
            st.markdown(f"## Harga {v}")
            sub = df[df["vendor"] == v]

            display = pd.DataFrame({
                "Berat": sub["weight_g"],
                "Harga Jual": sub["sell_idr"].apply(format_rp),
                "Harga Buyback": sub["buyback_idr"].apply(format_rp),
            })

            st.table(display)

        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Download CSV", csv, "galeri24_harga_emas.csv")

        st.success(f"Berhasil: {len(df)} baris")

    except Exception as e:
        st.error("Gagal ambil data")
        st.exception(e)
else:
    st.info("Klik tombol untuk memuat harga emas.")
