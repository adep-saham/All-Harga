import streamlit as st
import requests
import pandas as pd
import re
import os
import subprocess
import sys
from io import BytesIO

# =========================================================
# 1. PLAYWRIGHT AUTO-INSTALLER (Mencegah Error di Cloud)
# =========================================================
@st.cache_resource
def setup_playwright():
    """Menginstal binary browser Chromium untuk bypass OneDrive."""
    try:
        # Cek apakah playwright sudah terinstall
        subprocess.run(["playwright", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Jika belum ada, install library dan browsernya
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"])
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])

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
# 3. HELPERS UI / DOWNLOAD
# =========================================================
def format_rp(x: int) -> str:
    try:
        if x == 0: return "Rp0"
        return f"Rp{int(x):,}".replace(",", ".")
    except Exception:
        return "Rp0"

def safe_sheet_name(name: str, used: set) -> str:
    # Excel forbidden chars: : \ / ? * [ ]
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
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text

# =========================================================
# 4. APLIKASI UTAMA
# =========================================================
st.set_page_config(page_title="All Harga Emas", layout="wide")
st.title("📊 All Harga Emas")

# Sidebar Selector
source = st.sidebar.radio(
    "Sumber Data",
    ["Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK Logam Mulia"],
    index=0
)

# URL mapping
URLS = {
    "Galeri24": URL_GALERI24,
    "StarGold": URL_STARGOLD,
    "AnekaLogam": URL_ANEKALOGAM,
    "HRTA": URL_HRTA,
    "IndoGold": URL_INDOGOLD,
    "HK Logam Mulia": URL_HAKABEGOLD,
}
st.caption(f"Target URL: {URLS[source]}")

st.write("") 

if st.button("🚀 Ambil data sekarang"):
    try:
        url = URLS[source]

        # PROSES SCRAPING
        with st.spinner(f"Mengambil data dari {source}..."):
            if source == "HK Logam Mulia":
                # HK Logam Mulia punya logika fetch sendiri via OneDrive API
                df, update_label = parse_hakabegold("")
            elif source == "HRTA":
                # HRTA biasanya butuh session khusus atau tanpa HTML input
                df, update_label = parse_hrta("")
            else:
                html = fetch_html(url)
                if source == "Galeri24":
                    df, update_label = parse_galeri24(html)
                elif source == "StarGold":
                    df, update_label = parse_stargold(html)
                elif source == "AnekaLogam":
                    df, update_label = parse_anekalogam(html)
                elif source == "IndoGold":
                    df, update_label = parse_indogold(html)

        # TAMPILAN HASIL
        st.subheader(update_label)
        st.success(f"Berhasil menarik {len(df)} baris data.")

        # Multiselect Vendor (untuk filter tampilan)
        vendors = df["vendor"].unique().tolist()
        selected = st.sidebar.multiselect("Pilih Vendor untuk Ditampilkan", vendors, default=vendors)

        # Render Tabel per Vendor
        for v in selected:
            st.markdown(f"### Harga {v}")
            sub = df[df["vendor"] == v].copy()

            if "weight_g" in sub.columns:
                sub = sub.sort_values("weight_g")

            # Format tabel untuk user
            display = pd.DataFrame({
                "Berat (gr)": sub["weight_g"].apply(lambda x: int(x) if float(x).is_integer() else x),
                "Harga Jual": sub["sell_idr"].apply(format_rp),
                "Harga Buyback": sub["buyback_idr"].apply(format_rp),
            })
            
            # Tambahkan kolom stok jika tersedia (khusus HK/StarGold)
            if "stock" in sub.columns:
                display["Stok"] = sub["stock"]

            st.table(display)

        # =========================
        # DOWNLOAD SECTION
        # =========================
        st.divider()
        c1, c2 = st.columns(2)
        
        with c1:
            # DOWNLOAD CSV
            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "📥 Download CSV (Long Format)",
                data=csv,
                file_name=f"{source.lower().replace(' ', '_')}_harga_emas_long.csv",
                mime="text/csv",
                use_container_width=True
            )

        with c2:
            # DOWNLOAD EXCEL
            output = BytesIO()
            used_sheets = set()

            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                # Sheet Gabungan
                df.to_excel(writer, index=False, sheet_name="Semua_Data")
                used_sheets.add("Semua_Data")

                # Sheet Per Vendor
                for v in vendors:
                    sub_v = df[df["vendor"] == v].copy()
                    if "weight_g" in sub_v.columns:
                        sub_v = sub_v.sort_values("weight_g")

                    sub_out = pd.DataFrame({
                        "Berat": sub_v["weight_g"],
                        "Harga Jual": sub_v["sell_idr"].apply(format_rp),
                        "Harga Buyback": sub_v["buyback_idr"].apply(format_rp),
                    })
                    if "stock" in sub_v.columns:
                        sub_out["Stok"] = sub_v["stock"]

                    sub_out.to_excel(writer, index=False, sheet_name=safe_sheet_name(v, used_sheets))

            st.download_button(
                "📥 Download Excel (.xlsx)",
                data=output.getvalue(),
                file_name=f"{source.lower().replace(' ', '_')}_harga_emas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    except Exception as e:
        st.error(f"Terjadi kesalahan saat mengambil data {source}")
        st.exception(e)
else:
    st.info("💡 Pilih sumber di sidebar lalu klik **Ambil data sekarang**.")
