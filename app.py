import streamlit as st
import requests
import pandas as pd
from io import BytesIO
import plotly.express as px

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
    results = []
    # Galeri 24
    try:
        df, lbl = parse_galeri24()
        row = df[df['weight_g'] == 100].iloc[0]
        results.append({"vendor": "Galeri 24", "sell": row['sell_idr'], "buy": row['buyback_idr'], "update": lbl})
    except: pass
    
    # Aneka Logam
    try:
        df, lbl = parse_anekalogam(fetch_html(URL_ANEKALOGAM))
        row = df[df['weight_g'] == 100].iloc[0]
        results.append({"vendor": "Aneka Logam", "sell": row['sell_idr'], "buy": row['buyback_idr'], "update": lbl})
    except: pass

    # StarGold
    try:
        df, lbl = parse_stargold("")
        row = df[df['weight_g'] == 100].iloc[0]
        results.append({"vendor": "StarGold", "sell": row['sell_idr'], "buy": row['buyback_idr'], "update": lbl})
    except: pass

    # HK Logam Mulia
    try:
        df, lbl = parse_hakabegold()
        row = df[df['weight_g'] == 100].iloc[0]
        results.append({"vendor": "HK Logam Mulia", "sell": row['sell_idr'], "buy": row['buyback_idr'], "update": lbl})
    except: pass

    return pd.DataFrame(results)

def get_all_active_data():
    all_rows = []
    try:
        df, lbl = parse_galeri24()
        df['source_update'], df['vendor'] = lbl, "Galeri 24"
        all_rows.append(df)
    except: pass
    try:
        df, lbl = parse_anekalogam(fetch_html(URL_ANEKALOGAM))
        df['source_update'], df['vendor'] = lbl, "Aneka Logam"
        all_rows.append(df)
    except: pass
    try:
        df, lbl = parse_stargold("")
        df['source_update'], df['vendor'] = lbl, "StarGold"
        all_rows.append(df)
    except: pass
    try:
        df, lbl = parse_hakabegold()
        df['source_update'], df['vendor'] = lbl, "HK Logam Mulia"
        all_rows.append(df)
    except: pass
    
    if not all_rows: return pd.DataFrame()
    return pd.concat(all_rows, ignore_index=True)

# =========================================================
# SIDEBAR (KONTROL PANEL TETAP SAMA)
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
        view_mode = st.radio("Pilih Mode Tampilan:", ["Ringkasan 100g", "Detail per Toko"], horizontal=True)
        
        if view_mode == "Ringkasan 100g":
            st.subheader("🏆 Perbandingan Pecahan 100g")
            df_table = df_active[df_active['weight_g'] == 100].copy()
            display_data = pd.DataFrame({
                "Vendor": df_table["vendor"],
                "Harga Jual": df_table["sell_idr"].apply(format_rp),
                "Harga Beli": df_table["buyback_idr"].apply(format_rp),
                "Update di Web": df_table["source_update"]
            })
            st.dataframe(display_data, use_container_width=True, hide_index=True)
        else:
            for v_name in df_active["vendor"].unique():
                st.subheader(f"🏢 {v_name}")
                sub = df_active[df_active["vendor"] == v_name].sort_values("weight_g")
                st.table(pd.DataFrame({
                    "Berat": sub["weight_g"].apply(lambda x: f"{x:g} gr"),
                    "Harga Jual": sub["sell_idr"].apply(format_rp),
                    "Harga Beli": sub["buyback_idr"].apply(format_rp)
                }))

# =========================================================
# PERBAIKAN KHUSUS PADA TAB 2 (GRAFIK HISTORI)
# =========================================================
with tab2:
    st.subheader("📈 Grafik Histori")
    sheet_to_view = st.selectbox("Pilih Sumber Data Grafik", ["Summary_100g", "Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK_Logam_Mulia", "Agung_Jewellery"])
    
    # Mengambil data histori (Tanpa cache agar selalu update)
    df_hist = get_full_history(worksheet_name=sheet_to_view)
    
    if not df_hist.empty:
        # 1. Pastikan timestamp dalam format waktu agar urutan sumbu X benar
        df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'])
        
        c1, c2 = st.columns(2)
        v_list = sorted(df_hist['vendor'].unique())
        v_plot = c1.selectbox("Pilih Vendor", v_list)
        
        # 2. Filter berat yang tersedia hanya untuk vendor tersebut
        available_weights = sorted(df_hist[df_hist['vendor'] == v_plot]['weight_g'].unique())
        w_plot = c2.selectbox("Pilih Berat (gram)", available_weights, key="w_plot")
        
        # 3. Filter data dan WAJIB urutkan berdasarkan waktu (timestamp) agar garis tidak berantakan
        plot_df = df_hist[(df_hist['vendor'] == v_plot) & (df_hist['weight_g'] == w_plot)].sort_values("timestamp")
        
        if not plot_df.empty:
            # Membuat grafik
            fig = px.line(
                plot_df, 
                x="timestamp", 
                y="sell_idr", 
                markers=True, 
                title=f"Tren Harga Jual {v_plot} {w_plot}g",
                labels={"timestamp": "Waktu", "sell_idr": "Harga Jual (Rp)"}
            )
            
            # 4. Format angka pada sumbu Y agar mudah dibaca (Rupiah)
            fig.update_layout(yaxis_tickformat=',.0f')
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Data tidak ditemukan.")
            
        with st.expander("📂 Lihat Data Mentah"):
            st.dataframe(df_hist.sort_values("timestamp", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("Belum ada data histori untuk ditampilkan.")
