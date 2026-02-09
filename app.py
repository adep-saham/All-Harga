import streamlit as st
import pandas as pd
import plotly.express as px
import requests
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

# =========================================================
# 3. FUNGSI PENARIKAN DATA SEMUA VENDOR (100G)
# =========================================================
def get_all_comparison_100g():
    results = []
    
    # --- 1. Galeri 24 ---
    try:
        df, lbl = parse_galeri24()
        d = df[df['weight_g'] == 100].iloc[0]
        results.append({"vendor": "Galeri 24", "sell": d['sell_idr'], "buy": d['buyback_idr'], "update": lbl})
    except: pass

    # --- 2. Aneka Logam ---
    try:
        html = fetch_html(URL_ANEKALOGAM)
        df, lbl = parse_anekalogam(html)
        d = df[df['weight_g'] == 100].iloc[0]
        results.append({"vendor": "Aneka Logam", "sell": d['sell_idr'], "buy": d['buyback_idr'], "update": lbl})
    except: pass

    # --- 3. StarGold ---
    try:
        df, lbl = parse_stargold("") # Membaca file source web.txt
        d = df[df['weight_g'] == 100].iloc[0]
        results.append({"vendor": "StarGold", "sell": d['sell_idr'], "buy": d['buyback_idr'], "update": lbl})
    except: pass

    # --- 4. HRTA ---
    try:
        html = fetch_html(URL_HRTA)
        df, lbl = parse_hrta(html)
        d = df[df['weight_g'] == 100].iloc[0]
        results.append({"vendor": "HRTA", "sell": d['sell_idr'], "buy": d['buyback_idr'], "update": lbl})
    except: pass

    # --- 5. IndoGold ---
    try:
        html = fetch_html(URL_INDOGOLD)
        df, lbl = parse_indogold(html)
        d = df[df['weight_g'] == 100].iloc[0]
        results.append({"vendor": "IndoGold", "sell": d['sell_idr'], "buy": d['buyback_idr'], "update": lbl})
    except: pass

    # --- 6. Hakabe Gold ---
    try:
        df, lbl = parse_hakabegold()
        d = df[df['weight_g'] == 100].iloc[0]
        results.append({"vendor": "HK Logam Mulia", "sell": d['sell_idr'], "buy": d['buyback_idr'], "update": lbl})
    except: pass

    # --- 7. Agung Jewellery ---
    try:
        df, lbl = parse_agungjewellery()
        d = df[df['weight_g'] == 100].iloc[0]
        results.append({"vendor": "Agung Jewellery", "sell": d['sell_idr'], "buy": d['buyback_idr'], "update": lbl})
    except: pass

    return pd.DataFrame(results)

# =========================================================
# 4. SIDEBAR & CONTROL
# =========================================================
with st.sidebar:
    st.title("⚙️ Kontrol Panel")
    if st.button("🚀 Tarik Data Sekarang", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    # Fungsi upload file TXT StarGold
    render_uploader_sidebar()

# =========================================================
# 5. TAMPILAN TAB
# =========================================================
tab1, tab2 = st.tabs(["📊 Perbandingan Harga", "📈 Histori & Grafik"])

with tab1:
    st.header("Harga Emas Hari Ini (Pecahan 100g)")
    df_compare = get_all_comparison_100g()
    
    if not df_compare.empty:
        # Menampilkan Tabel Perbandingan
        view_df = pd.DataFrame({
            "Vendor": df_compare["vendor"],
            "Harga Jual": df_compare["sell"].apply(format_rp),
            "Harga Beli (Buyback)": df_compare["buy"].apply(format_rp),
            "Update di Web": df_compare["update"]
        })
        st.dataframe(view_df, use_container_width=True, hide_index=True)
        
        # Tombol Simpan Masal ke Tab Summary_100g
        if st.button("💾 Simpan Semua ke Histori (Summary_100g)"):
            df_to_save = pd.DataFrame({
                "vendor": df_compare["vendor"],
                "weight_g": 100,
                "sell_idr": df_compare["sell"],
                "buyback_idr": df_compare["buy"],
                "source_update": df_compare["update"]
            })
            if save_to_history(df_to_save, "Summary_100g"):
                st.success("✅ Berhasil disimpan ke tab Summary_100g!")
    else:
        st.info("Klik tombol 'Tarik Data' di sidebar untuk menarik data dari semua vendor.")

with tab2:
    st.header("Analisis Tren Harga")
    # Pilihan sumber data histori
    sheet_opt = st.selectbox("Pilih Tab Data", ["Summary_100g", "StarGold", "AnekaLogam", "HK_Logam_Mulia", "Agung_Jewellery", "Galeri24", "HRTA", "IndoGold"])
    
    # Ambil histori dengan ttl=0 agar realtime
    df_hist = get_full_history(sheet_opt)
    
    if not df_hist.empty:
        # Konversi timestamp ke datetime
        df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'])
        
        # Layout Filter Grafik
        c1, c2 = st.columns(2)
        v_list = sorted(df_hist['vendor'].unique())
        v_sel = c1.selectbox("Pilih Vendor", v_list)
        
        w_list = sorted(df_hist[df_hist['vendor'] == v_sel]['weight_g'].unique())
        w_sel = c2.selectbox("Pilih Berat (gr)", w_list)
        
        # Filter data untuk grafik
        plot_df = df_hist[(df_hist['vendor'] == v_sel) & (df_hist['weight_g'] == w_sel)].sort_values("timestamp")
        
        if not plot_df.empty:
            fig = px.line(
                plot_df, 
                x="timestamp", 
                y="sell_idr", 
                markers=True, 
                title=f"Tren Harga Jual: {v_sel} {w_sel}g",
                labels={"timestamp": "Waktu", "sell_idr": "Harga Jual (Rp)"}
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Tampilkan Data Mentah di bawah grafik
        with st.expander("📂 Lihat Data Mentah di Google Sheets (Terbaru di Atas)"):
            # Urutkan berdasarkan waktu terbaru agar mudah dicek
            st.dataframe(df_hist.sort_values("timestamp", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.warning(f"Belum ada data histori di tab '{sheet_opt}'.")
