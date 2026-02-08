import streamlit as st
import requests
import pandas as pd
import re
import os
import subprocess
import sys
from io import BytesIO

# =========================================================
# 1. PLAYWRIGHT AUTO-INSTALLER (Wajib untuk bypass OneDrive)
# =========================================================
@st.cache_resource
def setup_playwright():
    """
    Menginstal binary browser Chromium di server Linux (Streamlit Cloud).
    Hanya berjalan sekali saat aplikasi pertama kali start.
    """
    try:
        # Cek apakah browser chromium sudah ada
        subprocess.run(["playwright", "--version"], check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Jika error/tidak ada, install library dan browsernya
        st.warning("Sedang menginstal browser pendukung... Mohon tunggu sebentar.")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"])
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
        st.success("Instalasi browser selesai!")

# Jalankan setup sebelum memuat halaman
setup_playwright()

# =========================================================
# 2. IMPORT SCRAPERS
# =========================================================
# Pastikan folder 'scrapers' ada dan berisi file-file ini
from scrapers.galeri24 import parse_galeri24, URL_GALERI24
from scrapers.stargold import parse_stargold, URL_STARGOLD
from scrapers.anekalogam import parse_anekalogam, URL_ANEKALOGAM
from scrapers.hrta import parse_hrta, URL_HRTA
from scrapers.indogold import parse_indogold, URL_INDOGOLD
from scrapers.hakabegold import parse_hakabegold, URL_HAKABEGOLD

# =========================================================
# 3. HELPERS (Format & Utility)
# =========================================================
def format_rp(x: int) -> str:
    """Format angka ke Rupiah (cth: Rp1.000.000)"""
    try:
        return f"Rp{int(x):,}".replace(",", ".")
    except Exception:
        return "Rp0"

def safe_sheet_name(name: str, used: set) -> str:
    """Membersihkan nama sheet Excel dari karakter ilegal"""
    cleaned = re.sub(r"[:\\/?*\[\]]", " ", str(name))
    cleaned = re.sub(r"\s+", " ", cleaned).strip() or "Sheet"
    base = cleaned[:31] # Max 31 karakter
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
    """Mengambil HTML untuk scraper standar (non-playwright)"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8"
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text

# =========================================================
# 4. APLIKASI UTAMA (UI Streamlit)
# =========================================================
st.set_page_config(page_title="All Harga Emas", layout="wide")
st.title("📊 Monitoring Harga Emas")

# Sidebar
st.sidebar.header("Pengaturan")
source = st.sidebar.radio(
    "Pilih Sumber Data:",
    ["Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK Logam Mulia"],
    index=5 # Default ke HK Logam Mulia (sesuai fokus Anda)
)

# Mapping URL untuk info
URLS = {
    "Galeri24": URL_GALERI24,
    "StarGold": URL_STARGOLD,
    "AnekaLogam": URL_ANEKALOGAM,
    "HRTA": URL_HRTA,
    "IndoGold": URL_INDOGOLD,
    "HK Logam Mulia": URL_HAKABEGOLD,
}
st.caption(f"Target URL: {URLS[source]}")
st.divider()

if st.button("🚀 Ambil Data Sekarang", use_container_width=True):
    try:
        url = URLS[source]
        
        # --- PROSES SCRAPING ---
        with st.spinner(f"Sedang mengambil data dari {source}..."):
            if source == "HK Logam Mulia":
                # Menggunakan Playwright (tanpa input HTML, dia fetch sendiri)
                df, update_label = parse_hakabegold("")
            elif source == "HRTA":
                # HRTA fetch internal
                df, update_label = parse_hrta("")
            else:
                # Scraper standar pakai requests
                html = fetch_html(url)
                if source == "Galeri24":
                    df, update_label = parse_galeri24(html)
                elif source == "StarGold":
                    df, update_label = parse_stargold(html)
                elif source == "AnekaLogam":
                    df, update_label = parse_anekalogam(html)
                elif source == "IndoGold":
                    df, update_label = parse_indogold(html)

        # --- TAMPILAN HASIL ---
        st.subheader(update_label)
        
        if df is not None and not df.empty and "vendor" in df.columns:
            st.success(f"Berhasil menarik {len(df)} baris data.")
            
            # Filter Vendor (Multiselect)
            all_vendors = df["vendor"].unique().tolist()
            selected_vendors = st.sidebar.multiselect("Filter Tampilan Vendor", all_vendors, default=all_vendors)
            
            # Tampilkan Tabel per Vendor
            for v in selected_vendors:
                st.markdown(f"### {v}")
                sub_df = df[df["vendor"] == v].copy()
                
                # Sort by berat
                if "weight_g" in sub_df.columns:
                    sub_df = sub_df.sort_values("weight_g")
                
                # Format tabel UI
                display_cols = {
                    "weight_g": "Berat (gr)",
                    "sell_idr": "Harga Jual",
                    "buyback_idr": "Harga Buyback",
                    "stock": "Stok"
                }
                
                # Siapkan dataframe untuk display
                display_df = pd.DataFrame()
                if "weight_g" in sub_df.columns:
                    display_df["Berat (gr)"] = sub_df["weight_g"].apply(lambda x: int(x) if float(x).is_integer() else x)
                if "sell_idr" in sub_df.columns:
                    display_df["Harga Jual"] = sub_df["sell_idr"].apply(format_rp)
                if "buyback_idr" in sub_df.columns:
                    display_df["Harga Buyback"] = sub_df["buyback_idr"].apply(format_rp)
                if "stock" in sub_df.columns:
                    display_df["Stok"] = sub_df["stock"]
                
                st.table(display_df)

            # --- DOWNLOAD SECTION ---
            st.divider()
            st.write("### 📥 Download Data")
            c1, c2 = st.columns(2)
            
            with c1:
                # CSV Download
                csv_data = df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="Download CSV",
                    data=csv_data,
                    file_name=f"{source.replace(' ', '_')}_harga.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            with c2:
                # Excel Download
                excel_buffer = BytesIO()
                used_sheets = set()
                with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                    # Sheet Master
                    df.to_excel(writer, index=False, sheet_name="Master Data")
                    used_sheets.add("Master Data")
                    
                    # Sheet per Vendor
                    for v in all_vendors:
                        sub_v = df[df["vendor"] == v].copy()
                        clean_v = safe_sheet_name(v, used_sheets)
                        sub_v.to_excel(writer, index=False, sheet_name=clean_v)
                        
                st.download_button(
                    label="Download Excel",
                    data=excel_buffer.getvalue(),
                    file_name=f"{source.replace(' ', '_')}_harga.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        else:
            st.warning("Data kosong atau format tidak sesuai. Coba ulangi lagi.")

    except Exception as e:
        st.error(f"Terjadi kesalahan: {str(e)}")
        # Tampilkan detail error hanya di expander supaya tidak memenuhi layar
        with st.expander("Lihat Detail Error"):
            st.exception(e)

else:
    st.info("💡 Pilih sumber data di sebelah kiri, lalu klik tombol **Ambil Data Sekarang**.")
