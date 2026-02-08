import streamlit as st
import requests
import pandas as pd
import re
import os
import subprocess
import sys
from io import BytesIO

# =========================================================
# 1. PLAYWRIGHT SETUP (Hanya jalan 1x saat App Start)
# =========================================================
@st.cache_resource
def setup_playwright():
    """Menginstal browser Chromium di server Streamlit Cloud."""
    try:
        # Perintah ini wajib untuk mendownload binary browser di Linux
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    except Exception as e:
        st.error(f"Setup Browser Gagal: {e}")

setup_playwright()

# =========================================================
# 2. IMPORT SCRAPERS
# =========================================================
from scrapers.galeri24 import parse_galeri24, URL_GALERI24
from scrapers.stargold import parse_stargold, URL_STARGOLD
from scrapers.anekalogam import parse_anekalogam, URL_ANEKALOGAM
from scrapers.hrta import parse_hrta, URL_HRTA
from scrapers.indogold import parse_indogold, URL_INDOGOLD
from scrapers.hakabegold import parse_hakabegold, URL_HAKABEGOLD

# =========================================================
# 3. HELPERS
# =========================================================
def format_rp(x: int) -> str:
    try:
        return f"Rp{int(x):,}".replace(",", ".")
    except:
        return "Rp0"

def safe_sheet_name(name: str, used: set) -> str:
    cleaned = re.sub(r"[:\\/?*\[\]]", " ", str(name))
    cleaned = re.sub(r"\s+", " ", cleaned).strip() or "Sheet"
    base = cleaned[:31]
    candidate = base
    idx = 2
    while candidate in used:
        suffix = f"_{idx}"
        candidate = (base[:31 - len(suffix)] + suffix)[:31]
        idx += 1
    used.add(candidate)
    return candidate

@st.cache_data(ttl=180)
def fetch_html(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text

# =========================================================
# 4. APLIKASI UTAMA (UI)
# =========================================================
st.set_page_config(page_title="All Harga Emas", layout="wide")
st.title("📊 Monitoring Harga Emas")

source = st.sidebar.radio(
    "Pilih Sumber",
    ["Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK Logam Mulia"],
    index=0
)

URLS = {
    "Galeri24": URL_GALERI24,
    "StarGold": URL_STARGOLD,
    "AnekaLogam": URL_ANEKALOGAM,
    "HRTA": URL_HRTA,
    "IndoGold": URL_INDOGOLD,
    "HK Logam Mulia": URL_HAKABEGOLD,
}
st.caption(f"Target: {URLS[source]}")

if st.button("🚀 Ambil Data Sekarang"):
    try:
        url = URLS[source]
        with st.spinner(f"Menarik data dari {source}..."):
            if source == "HK Logam Mulia":
                df, update_label = parse_hakabegold("")
            elif source == "HRTA":
                df, update_label = parse_hrta("")
            else:
                html = fetch_html(url)
                if source == "Galeri24": df, update_label = parse_galeri24(html)
                elif source == "StarGold": df, update_label = parse_stargold(html)
                elif source == "AnekaLogam": df, update_label = parse_anekalogam(html)
                elif source == "IndoGold": df, update_label = parse_indogold(html)

        st.subheader(update_label)
        
        # Multiselect Vendor
        vendors = df["vendor"].unique().tolist()
        selected = st.sidebar.multiselect("Pilih Vendor", vendors, default=vendors)

        for v in selected:
            st.markdown(f"### {v}")
            sub = df[df["vendor"] == v].copy()
            if "weight_g" in sub.columns:
                sub = sub.sort_values("weight_g")

            display = pd.DataFrame({
                "Berat (gr)": sub["weight_g"].apply(lambda x: int(x) if float(x).is_integer() else x),
                "Harga Jual": sub["sell_idr"].apply(format_rp),
                "Harga Buyback": sub["buyback_idr"].apply(format_rp),
            })
            if "stock" in sub.columns:
                display["Stok"] = sub["stock"]
            st.table(display)

        # DOWNLOAD SECTION
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("📥 CSV", data=csv, file_name=f"{source}.csv", use_container_width=True)
        with col2:
            output = BytesIO()
            used_sheets = set()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="All_Data")
                for v in vendors:
                    sub_v = df[df["vendor"] == v].copy()
                    sub_v.to_excel(writer, index=False, sheet_name=safe_sheet_name(v, used_sheets))
            st.download_button("📥 Excel", data=output.getvalue(), file_name=f"{source}.xlsx", use_container_width=True)

    except Exception as e:
        st.error(f"Gagal mengambil data: {str(e)}")
        st.exception(e)
else:
    st.info("💡 Pilih sumber di sidebar lalu klik tombol di atas.")
