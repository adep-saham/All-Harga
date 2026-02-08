import streamlit as st
import requests
import pandas as pd
import re
from io import BytesIO

# =========================================================
# 1. IMPORT SCRAPERS
# =========================================================
# Pastikan file-file ini ada di folder 'scrapers' dan folder tersebut memiliki file kosong '__init__.py'
from scrapers.galeri24 import parse_galeri24, URL_GALERI24
from scrapers.stargold import parse_stargold, URL_STARGOLD
from scrapers.anekalogam import parse_anekalogam, URL_ANEKALOGAM
from scrapers.hrta import parse_hrta, URL_HRTA
from scrapers.indogold import parse_indogold, URL_INDOGOLD
# Import yang sebelumnya error sekarang seharusnya aman:
from scrapers.hakabegold import parse_hakabegold, URL_HAKABEGOLD

# =========================================================
# 2. KONFIGURASI HALAMAN (Wajib di awal)
# =========================================================
st.set_page_config(page_title="All Harga Emas", layout="wide")

# =========================================================
# 3. HELPERS
# =========================================================
def format_rp(x: int) -> str:
    try:
        if x == 0: return "Rp0"
        return f"Rp{int(x):,}".replace(",", ".")
    except: return "Rp0"

@st.cache_data(ttl=180)
def fetch_html(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        return r.text
    except Exception as e:
        st.error(f"Gagal mengambil HTML dari {url}: {e}")
        return ""

# =========================================================
# 4. UI APLIKASI
# =========================================================
st.title("📊 Monitoring Harga Emas")

source = st.sidebar.radio(
    "Sumber Data",
    ["Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK Logam Mulia"],
    index=5
)

# Mapping URL Source
URLS = {
    "Galeri24": URL_GALERI24,
    "StarGold": URL_STARGOLD,
    "AnekaLogam": URL_ANEKALOGAM,
    "HRTA": URL_HRTA,
    "IndoGold": URL_INDOGOLD,
    "HK Logam Mulia": URL_HAKABEGOLD,
}

current_url = URLS.get(source, "")
st.caption(f"Target: {current_url}")

if st.button("🚀 Ambil Data"):
    try:
        with st.spinner(f"Mengambil data {source}..."):
            df = pd.DataFrame()
            update_label = ""
            
            # Logika Pemilihan Scraper
            if source == "HK Logam Mulia":
                # HK Logam Mulia menggunakan Direct Download (tidak butuh HTML)
                df, update_label = parse_hakabegold("")
                
            elif source == "HRTA":
                # HRTA biasanya API atau Direct (sesuaikan dengan logika scraper Anda)
                df, update_label = parse_hrta("")
                
            else:
                # Scraper berbasis HTML Parsing
                html = fetch_html(current_url)
                if html:
                    if source == "Galeri24": df, update_label = parse_galeri24(html)
                    elif source == "StarGold": df, update_label = parse_stargold(html)
                    elif source == "AnekaLogam": df, update_label = parse_anekalogam(html)
                    elif source == "IndoGold": df, update_label = parse_indogold(html)

        # Tampilkan Hasil
        if df is not None and not df.empty and "vendor" in df.columns:
            st.subheader(update_label)
            st.success(f"Sukses! {len(df)} data ditemukan.")

            vendors = df["vendor"].unique().tolist()
            if len(vendors) > 1:
                selected = st.sidebar.multiselect("Filter Vendor", vendors, default=vendors)
            else:
                selected = vendors

            for v in selected:
                st.markdown(f"**{v}**")
                sub = df[df["vendor"] == v].copy()
                if "weight_g" in sub.columns: 
                    sub = sub.sort_values("weight_g")

                # Format Tabel Tampilan
                display = pd.DataFrame()
                display["Berat"] = sub["weight_g"].apply(lambda x: f"{x:g} gr")
                display["Harga Jual"] = sub["sell_idr"].apply(format_rp)
                display["Harga Buyback"] = sub["buyback_idr"].apply(format_rp)
                if "stock" in sub.columns: display["Stok"] = sub["stock"]
                
                st.table(display)
            
            # Download Area
            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                st.download_button("📥 Download CSV", df.to_csv(index=False).encode("utf-8-sig"), f"{source}.csv", "text/csv", use_container_width=True)
            with c2:
                out = BytesIO()
                with pd.ExcelWriter(out, engine="openpyxl") as w:
                    df.to_excel(w, index=False, sheet_name="Data")
                st.download_button("📥 Download Excel", out.getvalue(), f"{source}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        else:
            st.warning(f"Data kosong atau gagal diambil: {update_label}")

    except Exception as e:
        st.error(f"Terjadi kesalahan fatal: {e}")
