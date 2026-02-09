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
from utils.history_manager import get_full_history, save_to_history, save_batch_to_history

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

# --- Fungsi utama penarikan data (Seluruh Vendor & Seluruh Pecahan) ---
def get_all_active_data():
    all_rows = []
    
    def process_df(df, lbl, name):
        if df is not None and not df.empty:
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

    # 3. StarGold
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

    # 6. HK Logam Mulia
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
# 3. SIDEBAR (KONTROL PANEL)
# =========================================================
with st.sidebar:
    st.title("⚙️ Kontrol Panel")
    if st.button("🚀 Tarik Data Sekarang", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    # Fungsi uploader dari uploader.py
    render_uploader_sidebar()

# =========================================================
# 4. TAMPILAN UTAMA
# =========================================================
tab1, tab2 = st.tabs(["📊 Perbandingan & Detail", "📈 Grafik Histori"])

with tab1:
    st.header("Harga Emas Hari Ini")
    
    df_active = get_all_active_data()
    
    if not df_active.empty:
        # Tombol Simpan Masal (Summary, Detail, & Log Harian)
        if st.button("📦 SIMPAN MASAL (Sekali Klik untuk Semua Tab)", use_container_width=True, type="primary"):
            if save_batch_to_history(df_active):
                st.success(f"✅ Berhasil! Data disimpan ke Summary, Detail Toko, dan Log Harian ({datetime.now().strftime('%d%b%y')})")
        
        st.divider()
        
        # Pilihan Mode Tampilan
        view_mode = st.radio("Pilih Mode Tampilan:", ["Ringkasan 100g", "Detail per Toko"], horizontal=True)
        
        if view_mode == "Ringkasan 100g":
            st.subheader("🏆 Perbandingan Pecahan 100g")
            df_100 = df_active[df_active['weight_g'] == 100].copy()
            
            if not df_100.empty:
                display_data = pd.DataFrame({
                    "Vendor": df_100["vendor"],
                    "Harga Jual": df_100["sell_idr"].apply(format_rp),
                    "Harga Beli": df_100["buyback_idr"].apply(format_rp),
                    "Update di Web": df_100["source_update"]
                })
                st.dataframe(display_data, use_container_width=True, hide_index=True)
            else:
                st.warning("Pecahan 100g tidak ditemukan.")
                
        else: # Detail per Toko
            st.subheader("🏢 Detail Lengkap Seluruh Pecahan")
            for v_name in df_active["vendor"].unique():
                df_v = df_active[df_active["vendor"] == v_name].sort_values("weight_g")
                lbl_v = df_v["source_update"].iloc[0]
                
                with st.expander(f"🔍 {v_name} - {lbl_v}"):
                    st.table(pd.DataFrame({
                        "Berat": df_v["weight_g"].apply(lambda x: f"{x:g} gr"),
                        "Harga Jual": df_v["sell_idr"].apply(format_rp),
                        "Harga Beli": df_v["buyback_idr"].apply(format_rp)
                    }))
    else:
        st.info("Klik 'Tarik Data Sekarang' di sidebar untuk menarik harga terbaru.")

# =========================================================
# 5. TAB GRAFIK HISTORI (PERBAIKAN LOGIKA)
# =========================================================
with tab2:
    st.subheader("📈 Grafik Histori")
    
    # List tab yang bisa dipantau
    sheet_list = ["Summary_100g", "StarGold", "Aneka_Logam", "HK_Logam_Mulia", "Galeri_24", "HRTA", "IndoGold", "Agung_Jewellery"]
    # Menambah opsi log harian jika ada (Opsional: Anda bisa ketik manual tab harian di sini)
    sheet_to_view = st.selectbox("Pilih Sumber Data Grafik", sheet_list)
    
    # Ambil data histori (ttl=0 untuk realtime)
    df_hist = get_full_history(worksheet_name=sheet_to_view)
    
    if not df_hist.empty:
        # 1. Pastikan timestamp format datetime agar urutan sumbu X benar
        df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'])
        
        c1, c2 = st.columns(2)
        v_list = sorted(df_hist['vendor'].unique())
        v_plot = c1.selectbox("Pilih Vendor", v_list)
        
        # 2. Filter berat yang hanya tersedia untuk vendor tersebut
        available_weights = sorted(df_hist[df_hist['vendor'] == v_plot]['weight_g'].unique())
        w_plot = c2.selectbox("Pilih Berat (gram)", available_weights, key="w_plot")
        
        # 3. Filter data dan urutkan berdasarkan waktu (Kronologis)
        plot_df = df_hist[(df_hist['vendor'] == v_plot) & (df_hist['weight_g'] == w_plot)].sort_values("timestamp")
        
        if not plot_df.empty:
            # Membuat grafik plotly
            fig = px.line(
                plot_df, 
                x="timestamp", 
                y="sell_idr", 
                markers=True, 
                title=f"Tren Harga Jual {v_plot} {w_plot}g",
                labels={"timestamp": "Tanggal & Waktu", "sell_idr": "Harga Jual (Rp)"}
            )
            
            # 4. Format angka sumbu Y menjadi ribuan agar mudah dibaca
            fig.update_layout(yaxis_tickformat=',.0f')
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Data tidak ditemukan untuk kriteria tersebut.")
            
        with st.expander("📂 Lihat Data Mentah (Terbaru di Atas)"):
            st.dataframe(df_hist.sort_values("timestamp", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info(f"Belum ada data histori di tab '{sheet_to_view}'.")
