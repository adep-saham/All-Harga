import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime

# =========================================================
# 1. IMPORT SCRAPERS & UTILS
# =========================================================
from scrapers.galeri24 import parse_galeri24
from scrapers.stargold import parse_stargold
from scrapers.anekalogam import parse_anekalogam, URL_ANEKALOGAM
from scrapers.hrta import parse_hrta, URL_HRTA
from scrapers.indogold import parse_indogold, URL_INDOGOLD
from scrapers.hakabegold import parse_hakabegold
from scrapers.agungjewellery import parse_agungjewellery

from utils.uploader import render_uploader_sidebar
from utils.history_manager import get_full_history, save_to_history

# =========================================================
# 2. CONFIG & HELPERS
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

# --- Fungsi untuk mengambil SEMUA DATA dari SEMUA VENDOR ---
def get_all_active_data():
    all_rows = []
    labels = {}

    # Helper untuk memproses dataframe
    def process_df(df, lbl, name):
        if not df.empty:
            df['source_update'] = lbl
            df['vendor'] = name
            return df
        return pd.DataFrame()

    # 1. Galeri 24
    try:
        df, lbl = parse_galeri24()
        all_rows.append(process_df(df, lbl, "Galeri 24"))
    except: pass

    # 2. Aneka Logam
    try:
        df, lbl = parse_anekalogam(fetch_html(URL_ANEKALOGAM))
        all_rows.append(process_df(df, lbl, "Aneka Logam"))
    except: pass

    # 3. StarGold (Source TXT)
    try:
        df, lbl = parse_stargold("")
        all_rows.append(process_df(df, lbl, "StarGold"))
    except: pass

    # 4. HRTA
    try:
        df, lbl = parse_hrta(fetch_html(URL_HRTA))
        all_rows.append(process_df(df, lbl, "HRTA"))
    except: pass

    # 5. IndoGold
    try:
        df, lbl = parse_indogold(fetch_html(URL_INDOGOLD))
        all_rows.append(process_df(df, lbl, "IndoGold"))
    except: pass

    # 6. HK Logam Mulia (Hakabe)
    try:
        df, lbl = parse_hakabegold()
        all_rows.append(process_df(df, lbl, "HK Logam Mulia"))
    except: pass

    # 7. Agung Jewellery
    try:
        df, lbl = parse_agungjewellery()
        all_rows.append(process_df(df, lbl, "Agung Jewellery"))
    except: pass

    if not all_rows: return pd.DataFrame()
    return pd.concat(all_rows, ignore_index=True)

# =========================================================
# 3. SIDEBAR
# =========================================================
with st.sidebar:
    st.title("⚙️ Kontrol Panel")
    if st.button("🚀 Tarik Data Sekarang", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    render_uploader_sidebar()

# =========================================================
# 4. TAMPILAN UTAMA
# =========================================================
tab1, tab2 = st.tabs(["📊 Perbandingan & Detail", "📈 Histori & Grafik"])

with tab1:
    st.header("Harga Emas Hari Ini")
    
    # Menarik seluruh data (semua pecahan)
    df_all = get_all_active_data()
    
    if not df_all.empty:
        # Pilihan Mode Tampilan
        view_mode = st.radio("Pilih Mode Tampilan:", ["Ringkasan 100g", "Detail per Toko"], horizontal=True)
        
        if view_mode == "Ringkasan 100g":
            st.subheader("🏆 Perbandingan Pecahan 100g")
            df_100 = df_all[df_all['weight_g'] == 100].copy()
            
            if not df_100.empty:
                display_100 = pd.DataFrame({
                    "Vendor": df_100["vendor"],
                    "Harga Jual": df_100["sell_idr"].apply(format_rp),
                    "Harga Beli": df_100["buyback_idr"].apply(format_rp),
                    "Update di Web": df_100["source_update"]
                })
                st.dataframe(display_100, use_container_width=True, hide_index=True)
                
                if st.button("💾 Simpan Ringkasan 100g ke Histori"):
                    if save_to_history(df_100, "Summary_100g"):
                        st.success("✅ Histori Summary_100g diperbarui!")
            else:
                st.warning("Pecahan 100g tidak ditemukan pada beberapa vendor.")
                
        else: # Detail per Toko
            st.subheader("🏢 Detail Lengkap Seluruh Pecahan")
            for v_name in df_all["vendor"].unique():
                df_v = df_all[df_all["vendor"] == v_name].sort_values("weight_g")
                lbl_v = df_v["source_update"].iloc[0]
                
                with st.expander(f"🔍 {v_name} - {lbl_v}"):
                    # Tabel detail
                    st.table(pd.DataFrame({
                        "Berat": df_v["weight_g"].apply(lambda x: f"{x:g} gr"),
                        "Harga Jual": df_v["sell_idr"].apply(format_rp),
                        "Harga Beli": df_v["buyback_idr"].apply(format_rp)
                    }))
                    
                    # Tombol simpan per toko
                    if st.button(f"Simpan Histori Lengkap {v_name}", key=f"save_{v_name}"):
                        tab_name = v_name.replace(" ", "_")
                        if save_to_history(df_v, tab_name):
                            st.success(f"✅ Data {v_name} berhasil dicatat di tab {tab_name}!")
    else:
        st.info("Klik 'Tarik Data Sekarang' untuk mengambil harga terbaru.")

# =========================================================
# 5. TAB HISTORI & GRAFIK
# =========================================================
with tab2:
    st.header("📈 Analisis Histori")
    
    # List tab yang tersedia di Google Sheets
    sheet_list = ["Summary_100g", "StarGold", "Aneka_Logam", "HK_Logam_Mulia", "Galeri_24", "HRTA", "IndoGold", "Agung_Jewellery"]
    sheet_opt = st.selectbox("Pilih Sumber Data Histori", sheet_list)
    
    # Ambil data histori dengan ttl=0 agar selalu refresh
    df_hist = get_full_history(sheet_opt)
    
    if not df_hist.empty:
        # Konversi tipe data
        df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'])
        
        c1, c2 = st.columns(2)
        v_list = sorted(df_hist['vendor'].unique())
        v_sel = c1.selectbox("Pilih Vendor untuk Grafik", v_list)
        
        w_list = sorted(df_hist[df_hist['vendor'] == v_sel]['weight_g'].unique())
        w_sel = c2.selectbox("Pilih Berat (gram)", w_list)
        
        # Filter untuk grafik
        plot_df = df_hist[(df_hist['vendor'] == v_sel) & (df_hist['weight_g'] == w_sel)].sort_values("timestamp")
        
        if not plot_df.empty:
            fig = px.line(plot_df, x="timestamp", y="sell_idr", markers=True, 
                         title=f"Tren Harga Jual {v_sel} {w_sel}g",
                         labels={"timestamp": "Waktu Update", "sell_idr": "Harga (Rp)"})
            st.plotly_chart(fig, use_container_width=True)
            
        with st.expander("📂 Lihat Data Mentah di Google Sheets"):
            st.dataframe(df_hist.sort_values("timestamp", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.warning(f"Belum ada data di tab '{sheet_opt}'.")
