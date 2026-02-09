import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime

# IMPORT SCRAPERS & UTILS
from scrapers.galeri24 import parse_galeri24
from scrapers.stargold import parse_stargold
from scrapers.anekalogam import parse_anekalogam, URL_ANEKALOGAM
from scrapers.hrta import parse_hrta, URL_HRTA
from scrapers.indogold import parse_indogold, URL_INDOGOLD
from scrapers.hakabegold import parse_hakabegold
from scrapers.agungjewellery import parse_agungjewellery

from utils.uploader import render_uploader_sidebar
from utils.history_manager import get_full_history, save_to_history, save_batch_to_history

# CONFIG
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

def get_all_active_data():
    all_rows = []
    def process_df(df, lbl, name):
        if df is not None and not df.empty:
            df['source_update'], df['vendor'] = lbl, name
            return df
        return pd.DataFrame()

    try:
        df, lbl = parse_galeri24()
        all_rows.append(process_df(df, lbl, "Galeri 24"))
    except: pass
    try:
        df, lbl = parse_anekalogam(fetch_html(URL_ANEKALOGAM))
        all_rows.append(process_df(df, lbl, "Aneka Logam"))
    except: pass
    try:
        df, lbl = parse_stargold("")
        all_rows.append(process_df(df, lbl, "StarGold"))
    except: pass
    try:
        df, lbl = parse_hakabegold()
        all_rows.append(process_df(df, lbl, "HK Logam Mulia"))
    except: pass

    return pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()

# =========================================================
# SIDEBAR (KONTROL PANEL)
# =========================================================
with st.sidebar:
    st.title("⚙️ Kontrol Panel")
    if st.button("🚀 Tarik Data Sekarang", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    render_uploader_sidebar()

# =========================================================
# TAMPILAN UTAMA
# =========================================================
tab1, tab2 = st.tabs(["📊 Perbandingan & Detail", "📈 Grafik Histori"])

with tab1:
    st.header("Harga Emas Hari Ini")
    df_active = get_all_active_data()
    
    if not df_active.empty:
        # Tombol Simpan Masal (Ditambahkan di atas tanpa mengubah struktur radio)
        if st.button("📦 SIMPAN MASAL (Ke Summary, Toko, & Log Harian)", use_container_width=True, type="primary"):
            if save_batch_to_history(df_active):
                st.success("✅ Berhasil! Data dicatat di seluruh tab tujuan.")
        
        st.divider()
        
        # STRUKTUR ASLI ANDA
        view_mode = st.radio("Pilih Mode Tampilan:", ["Ringkasan 100g", "Detail per Toko"], horizontal=True)
        
        if view_mode == "Ringkasan 100g":
            st.subheader("🏆 Perbandingan Pecahan 100g")
            df_100 = df_active[df_active['weight_g'] == 100].copy()
            if not df_100.empty:
                display_df = pd.DataFrame({
                    "Vendor": df_100["vendor"],
                    "Harga Jual": df_100["sell_idr"].apply(format_rp),
                    "Harga Beli": df_100["buyback_idr"].apply(format_rp),
                    "Update di Web": df_100["source_update"]
                })
                st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.subheader("🏢 Detail Lengkap Seluruh Pecahan")
            for v_name in df_active["vendor"].unique():
                with st.expander(f"🔍 {v_name}"):
                    sub = df_active[df_active["vendor"] == v_name].sort_values("weight_g")
                    st.table(pd.DataFrame({
                        "Berat": sub["weight_g"].apply(lambda x: f"{x:g} gr"),
                        "Harga Jual": sub["sell_idr"].apply(format_rp),
                        "Harga Beli": sub["buyback_idr"].apply(format_rp)
                    }))
    else:
        st.info("Klik Tarik Data Sekarang.")

# =========================================================
# TAB GRAFIK (DIPERBAIKI)
# =========================================================
with tab2:
    st.subheader("📈 Grafik Histori")
    sheet_list = ["Summary_100g", "StarGold", "Aneka_Logam", "HK_Logam_Mulia", "Galeri_24"]
    sheet_opt = st.selectbox("Pilih Sumber Data Grafik", sheet_list)
    
    df_hist = get_full_history(worksheet_name=sheet_opt)
    
    if not df_hist.empty:
        df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'])
        
        c1, c2 = st.columns(2)
        v_plot = c1.selectbox("Pilih Vendor", sorted(df_hist['vendor'].unique()))
        w_plot = c2.selectbox("Pilih Berat (gram)", sorted(df_hist[df_hist['vendor']==v_plot]['weight_g'].unique()), key="w_plot")
        
        # Filter & Sort agar garis grafik kronologis (dari kiri ke kanan)
        plot_df = df_hist[(df_hist['vendor'] == v_plot) & (df_hist['weight_g'] == w_plot)].sort_values("timestamp")
        
        if not plot_df.empty:
            fig = px.line(plot_df, x="timestamp", y="sell_idr", markers=True, title=f"Tren Harga {v_plot} {w_plot}g")
            fig.update_layout(yaxis_tickformat=',.0f')
            st.plotly_chart(fig, use_container_width=True)
            
        with st.expander("📂 Lihat Data Mentah"):
            st.dataframe(df_hist.sort_values("timestamp", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("Belum ada data histori.")
