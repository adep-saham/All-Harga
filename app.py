import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
import time
from io import BytesIO

# =========================================================
# IMPORT SCRAPERS & UTILS
# =========================================================
from scrapers.galeri24 import parse_galeri24, URL_GALERI24
from scrapers.stargold import parse_stargold, URL_STARGOLD
from scrapers.anekalogam import parse_anekalogam, URL_ANEKALOGAM
from scrapers.hrta import parse_hrta, URL_HRTA
from scrapers.indogold import parse_indogold, URL_INDOGOLD
from scrapers.hakabegold import parse_hakabegold, URL_HAKABEGOLD
from scrapers.agungjewellery import parse_agungjewellery

from utils.uploader import render_uploader_sidebar
from utils.history_manager import get_full_history, save_to_history

# =========================================================
# CONFIG & HELPERS
# =========================================================
st.set_page_config(page_title="Monitor Harga Emas", layout="wide")

def format_rp(x):
    try: return f"Rp{int(x):,}".replace(",", ".")
    except: return "Rp0"

@st.cache_data(ttl=300)
def fetch_html(url: str) -> str:
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        return r.text or ""
    except: return ""

def get_all_comparison_100g():
    """Mengambil data perbandingan khusus 100gr untuk semua sumber"""
    results = []
    scrapers = [
        ("StarGold", lambda: parse_stargold("")),
        ("Galeri 24", lambda: parse_galeri24(fetch_html(URL_GALERI24))),
        ("Aneka Logam", lambda: parse_anekalogam(fetch_html(URL_ANEKALOGAM))),
        ("HRTA GOLD", lambda: parse_hrta("")),
        ("IndoGold", lambda: parse_indogold(fetch_html(URL_INDOGOLD))),
        ("HK Logam Mulia", lambda: parse_hakabegold()),
        ("Agung Jewellery", lambda: parse_agungjewellery()),
    ]
    for name, func in scrapers:
        try:
            df_tmp, update_label = func() 
            if df_tmp is not None and not df_tmp.empty:
                # Filter 100gr untuk perbandingan global
                mask = (df_tmp['vendor'].str.contains('ANTAM|STARGOLD', case=False)) & (df_tmp['weight_g'] == 100)
                filtered = df_tmp[mask].copy()
                if not filtered.empty:
                    row = filtered.sort_values("sell_idr").iloc[0]
                    results.append({
                        "vendor": name, "weight_g": 100, 
                        "sell_idr": row['sell_idr'], "buyback_idr": row['buyback_idr'],
                        "source_update": update_label 
                    })
        except: continue
    return pd.DataFrame(results)

# =========================================================
# UI SIDEBAR
# =========================================================
st.sidebar.title("⚙️ Kontrol")
mode = st.sidebar.radio("Mode Tampilan", ["📊 Perbandingan 100g (All)", "🏪 Detail Per Toko"])

if mode == "🏪 Detail Per Toko":
    source_opt = st.sidebar.selectbox("Pilih Toko", ["Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK Logam Mulia", "Agung Jewellery"])
else:
    source_opt = "All 100g"

btn_fetch = st.sidebar.button("🚀 Ambil Data Terbaru", width='stretch')

st.sidebar.divider()
render_uploader_sidebar()

# =========================================================
# MAIN CONTENT
# =========================================================
st.title("📊 Monitoring Harga Emas")
tab1, tab2 = st.tabs(["🕒 Harga Realtime", "📈 Grafik Histori"])

with tab1:
    if btn_fetch:
        st.cache_data.clear()
        if mode == "📊 Perbandingan 100g (All)":
            st.session_state['current_df'] = get_all_comparison_100g()
        else:
            # Scraping detail per toko
            df_detail = pd.DataFrame()
            ul = "N/A"
            if source_opt == "StarGold": 
                df_detail, ul = parse_stargold("")
                if not df_detail.empty:
                    # LOGIKA KHUSUS STARGOLD: 
                    # 1. Jika Brand ANTAM -> Ambil gramasi 100 saja
                    # 2. Jika Brand LAIN (UBS, Lotus, dll) -> Biarkan asli (semua gramasi)
                    mask_antam_100 = (df_detail['vendor'].str.contains('ANTAM', case=False)) & (df_detail['weight_g'] == 100)
                    mask_others = ~(df_detail['vendor'].str.contains('ANTAM', case=False))
                    df_detail = df_detail[mask_antam_100 | mask_others].copy()
            
            elif source_opt == "HK Logam Mulia": df_detail, ul = parse_hakabegold()
            elif source_opt == "Agung Jewellery": df_detail, ul = parse_agungjewellery()
            elif source_opt == "HRTA": df_detail, ul = parse_hrta("")
            else:
                url = {"Galeri24": URL_GALERI24, "AnekaLogam": URL_ANEKALOGAM, "IndoGold": URL_INDOGOLD}.get(source_opt)
                html = fetch_html(url)
                if source_opt == "Galeri24": df_detail, ul = parse_galeri24(html)
                elif source_opt == "AnekaLogam": df_detail, ul = parse_anekalogam(html)
                elif source_opt == "IndoGold": df_detail, ul = parse_indogold(html)
            
            if not df_detail.empty: 
                df_detail['source_update'] = ul
                if 'vendor' not in df_detail.columns: df_detail['vendor'] = source_opt
            
            st.session_state['current_df'] = df_detail.reset_index(drop=True)

    # TAMPILAN DATA
    if 'current_df' in st.session_state and not st.session_state['current_df'].empty:
        df_active = st.session_state['current_df']
        
        if mode == "📊 Perbandingan 100g (All)":
            st.subheader("📋 Ringkasan Antam 100 gr")
            if st.button(f"💾 Simpan Histori Summary 100g ke Sheets", type="primary"):
                if save_to_history(df_active, worksheet_name="Summary_100g"):
                    st.success("Berhasil disimpan ke Summary_100g")
                else: st.error("Gagal simpan.")

            df_table = df_active.sort_values("sell_idr").reset_index(drop=True)
            st.dataframe(pd.DataFrame({
                "No": range(1, len(df_table) + 1),
                "Nama Toko": df_table["vendor"],
                "Jual": df_table["sell_idr"].apply(format_rp),
                "Beli": df_table["buyback_idr"].apply(format_rp),
                "Update": df_table["source_update"]
            }), width='stretch', hide_index=True)
            
        else:
            # Halaman Detail Toko
            vendor_now = source_opt
            st.subheader(f"🏢 Detail Toko: {vendor_now}")
            
            ws_target = str(vendor_now).replace(" ", "_")
            if st.button(f"💾 Simpan Histori {vendor_now} ke Sheets", type="primary"):
                with st.spinner(f"Menyimpan data..."):
                    if save_to_history(df_active, worksheet_name=ws_target):
                        st.success(f"Data {vendor_now} berhasil dicatat!")
                    else: st.error("Gagal menyimpan.")

            # Menampilkan Tabel yang sudah bersih
            # Kita kelompokkan per Brand (Vendor) agar rapi jika ada banyak brand
            for brand in df_active['vendor'].unique():
                st.markdown(f"**Brand: {brand}**")
                sub = df_active[df_active['vendor'] == brand].sort_values("weight_g")
                st.table(pd.DataFrame({
                    "Berat": sub["weight_g"].apply(lambda x: f"{x:g} gr"),
                    "Harga Jual": sub["sell_idr"].apply(format_rp),
                    "Harga Beli": sub["buyback_idr"].apply(format_rp)
                }))

with tab2:
    st.subheader("📈 Grafik Histori")
    # ... (logika grafik tetap sama)
