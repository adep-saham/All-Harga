import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

# IMPORT SCRAPERS & UTILS
from scrapers.galeri24 import parse_galeri24
from scrapers.stargold import parse_stargold
from scrapers.anekalogam import parse_anekalogam
from scrapers.hrta import parse_hrta
from scrapers.indogold import parse_indogold
from scrapers.hakabegold import parse_hakabegold
from scrapers.agungjewellery import parse_agungjewellery

from utils.uploader import render_uploader_sidebar
from utils.history_manager import get_full_history, save_to_history

# KONFIGURASI HALAMAN
st.set_page_config(page_title="Monitor Harga Emas", layout="wide")

def format_rp(x):
    try: return f"Rp{int(x):,}".replace(",", ".")
    except: return "Rp0"

# --- FUNGSI UTAMA PENARIKAN DATA ---
def get_all_comparison_100g():
    results = []
    
    # 1. Galeri 24 (100g)
    try:
        df_g, lbl_g = parse_galeri24()
        d_g = df_g[df_g['weight_g'] == 100].iloc[0]
        results.append({"vendor": "Galeri 24", "sell": d_g['sell_idr'], "buy": d_g['buyback_idr'], "update": lbl_g})
    except: pass

    # 2. Aneka Logam (100g)
    try:
        # Gunakan HTML fetcher jika perlu, atau panggil langsung jika scraper menangani URL
        df_a, lbl_a = parse_anekalogam() # Sesuaikan jika scraper butuh input HTML
        d_a = df_a[df_a['weight_g'] == 100].iloc[0]
        results.append({"vendor": "Aneka Logam", "sell": d_a['sell_idr'], "buy": d_a['buyback_idr'], "update": lbl_a})
    except: pass

    # 3. StarGold (100g dari file source web.txt)
    try:
        df_s, lbl_s = parse_stargold("")
        d_s = df_s[df_s['weight_g'] == 100].iloc[0]
        results.append({"vendor": "StarGold", "sell": d_s['sell_idr'], "buy": d_s['buyback_idr'], "update": lbl_s})
    except: pass

    # Tambahkan vendor lainnya di sini...

    return pd.DataFrame(results)

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚙️ Kontrol Panel")
    if st.button("🚀 Tarik Data Sekarang", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    # Fungsi upload file TXT StarGold
    render_uploader_sidebar()

# --- TAMPILAN UTAMA ---
tab1, tab2 = st.tabs(["📊 Perbandingan Harga", "📈 Histori & Grafik"])

with tab1:
    st.header("Harga Emas Hari Ini (Pecahan 100g)")
    df_compare = get_all_comparison_100g()
    
    if not df_compare.empty:
        # Tampilkan Tabel Perbandingan
        view_df = pd.DataFrame({
            "Vendor": df_compare["vendor"],
            "Harga Jual": df_compare["sell"].apply(format_rp),
            "Harga Beli (Buyback)": df_compare["buy"].apply(format_rp),
            "Update di Web": df_compare["update"]
        })
        st.dataframe(view_df, use_container_width=True, hide_index=True)
        
        if st.button("💾 Simpan Semua ke Histori (Summary_100g)"):
            # Mapping ke struktur history
            df_to_save = pd.DataFrame({
                "vendor": df_compare["vendor"],
                "weight_g": 100,
                "sell_idr": df_compare["sell"],
                "buyback_idr": df_compare["buy"],
                "source_update": df_compare["update"]
            })
            if save_to_history(df_to_save, "Summary_100g"):
                st.success("Berhasil disimpan ke tab Summary_100g!")
    else:
        st.info("Klik tombol 'Tarik Data' di sidebar untuk memulai.")

with tab2:
    st.header("Analisis Tren Harga")
    sheet_opt = st.selectbox("Pilih Tab Data", ["Summary_100g", "StarGold", "AnekaLogam", "HK_Logam_Mulia"])
    
    df_hist = get_full_history(sheet_opt)
    
    if not df_hist.empty:
        df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'])
        
        # FILTER GRAFIK
        c1, c2 = st.columns(2)
        v_sel = c1.selectbox("Pilih Vendor", df_hist['vendor'].unique())
        w_sel = c2.selectbox("Pilih Berat (gr)", sorted(df_hist['weight_g'].unique()))
        
        plot_df = df_hist[(df_hist['vendor'] == v_sel) & (df_hist['weight_g'] == w_sel)].sort_values("timestamp")
        
        if not plot_df.empty:
            fig = px.line(plot_df, x="timestamp", y="sell_idr", markers=True, title=f"Tren Harga {v_sel} {w_sel}g")
            st.plotly_chart(fig, use_container_width=True)
        
        # TABEL DATA MENTAH
        with st.expander("📂 Lihat Data Mentah (Terbaru di Atas)"):
            st.dataframe(df_hist.sort_values("timestamp", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.warning("Belum ada data histori untuk ditampilkan.")
