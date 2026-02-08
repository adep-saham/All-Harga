import streamlit as st
import requests
import pandas as pd
from io import BytesIO
import plotly.express as px

# =========================================================
# 1. IMPORT SCRAPERS & UTILS
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
# 2. CONFIG & HELPERS
# =========================================================
st.set_page_config(page_title="Monitor Harga Emas", layout="wide")

def format_rp(x):
    """Format angka ke Rupiah dengan pemisah titik."""
    try: return f"Rp{int(x):,}".replace(",", ".")
    except: return "Rp0"

@st.cache_data(ttl=300)
def fetch_html(url: str) -> str:
    """Fetcher HTML umum dengan penanganan error."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=30)
        return r.text or ""
    except: return ""

def get_all_comparison_100g():
    """Mengumpulkan data 100g dari semua sumber untuk Summary."""
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
            df_tmp, _ = func()
            if df_tmp is not None and not df_tmp.empty:
                # Filter multi-brand vs single-brand
                if name in ["Galeri 24", "StarGold", "IndoGold"]:
                    mask = (df_tmp['vendor'].str.contains('ANTAM', case=False)) & (df_tmp['weight_g'] == 100)
                else:
                    mask = (df_tmp['weight_g'] == 100)
                
                filtered = df_tmp[mask].copy()
                if not filtered.empty:
                    row = filtered.sort_values("sell_idr").iloc[0]
                    results.append({
                        "vendor": name, 
                        "weight_g": 100, 
                        "sell_idr": row['sell_idr'], 
                        "buyback_idr": row['buyback_idr']
                    })
        except: continue
    return pd.DataFrame(results)

# =========================================================
# 3. UI SIDEBAR
# =========================================================
st.sidebar.title("⚙️ Kontrol Database")
mode = st.sidebar.radio("Mode Tampilan", ["📊 Perbandingan 100g (All)", "🏪 Detail Per Toko"])

# Tentukan target sheet berdasarkan mode atau pilihan toko
if mode == "🏪 Detail Per Toko":
    source_opt = st.sidebar.selectbox("Pilih Toko", ["Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK Logam Mulia", "Agung Jewellery"])
    target_sheet = source_opt.replace(" ", "_") # Bersihkan nama untuk worksheet
else:
    source_opt = "All 100g"
    target_sheet = "Summary_100g"

# Tombol Tarik Data - Menggunakan sintaks 2026 width='stretch'
btn_fetch = st.sidebar.button("🚀 Tarik Data Terbaru", width='stretch', type="primary")

st.sidebar.divider()
render_uploader_sidebar() # Sidebar untuk upload TXT StarGold

# =========================================================
# 4. MAIN CONTENT
# =========================================================
st.title("📈 Sistem Monitoring Harga Emas")
tab1, tab2 = st.tabs(["🕒 Harga Realtime", "📜 Histori & Grafik"])

with tab1:
    # --- LOGIKA AMBIL DATA ---
    if btn_fetch:
        st.cache_data.clear()
        if mode == "📊 Perbandingan 100g (All)":
            with st.spinner("Menyelaraskan harga 100g seluruh toko..."):
                st.session_state['current_df'] = get_all_comparison_100g()
        else:
            with st.spinner(f"Mengambil data lengkap {source_opt}..."):
                df_detail = pd.DataFrame()
                if source_opt == "HK Logam Mulia": df_detail, _ = parse_hakabegold()
                elif source_opt == "StarGold": df_detail, _ = parse_stargold("")
                elif source_opt == "Agung Jewellery": df_detail, _ = parse_agungjewellery()
                elif source_opt == "HRTA": df_detail, _ = parse_hrta("")
                else:
                    target_url = {"Galeri24": URL_GALERI24, "AnekaLogam": URL_ANEKALOGAM, "IndoGold": URL_INDOGOLD}.get(source_opt)
                    html = fetch_html(target_url)
                    if source_opt == "Galeri24": df_detail, _ = parse_galeri24(html)
                    elif source_opt == "AnekaLogam": df_detail, _ = parse_anekalogam(html)
                    elif source_opt == "IndoGold": df_detail, _ = parse_indogold(html)
                st.session_state['current_df'] = df_detail

    # --- TAMPILAN DATA & TOMBOL SIMPAN ---
    if 'current_df' in st.session_state and not st.session_state['current_df'].empty:
        df_active = st.session_state['current_df']
        
        # Tombol Simpan (Sekarang mengirim parameter target_sheet)
        if st.button(f"💾 Simpan ke Google Sheet: {target_sheet}", width='stretch'):
            if save_to_history(df_active, worksheet_name=target_sheet):
                st.success(f"✅ Data berhasil dicatat di tab '{target_sheet}'")

        st.divider()

        if mode == "📊 Perbandingan 100g (All)":
            st.subheader("📋 Tabel Perbandingan Antam 100 gr")
            df_table = df_active.sort_values("sell_idr").reset_index(drop=True)
            
            # Persiapkan tampilan tabel bersih tanpa double index
            display_data = pd.DataFrame({
                "No": range(1, len(df_table) + 1),
                "Nama Toko Emas": df_table["vendor"],
                "Harga Jual": df_table["sell_idr"].apply(format_rp),
                "Harga Beli": df_table["buyback_idr"].apply(format_rp)
            })
            st.dataframe(display_data, width='stretch', hide_index=True)
            
            # Info Rekomendasi
            best = df_table.iloc[0]
            st.info(f"💡 Rekomendasi: **{best['vendor']}** menawarkan harga termurah hari ini: **{format_rp(best['sell_idr'])}**")
        else:
            # Tampilan Detail Per Toko
            for v_name in df_active["vendor"].unique():
                st.subheader(f"🏢 {v_name}")
                sub_data = df_active[df_active["vendor"] == v_name].sort_values("weight_g")
                
                table_detail = pd.DataFrame({
                    "Berat": sub_data["weight_g"].apply(lambda x: f"{x:g} gr"),
                    "Harga Jual": sub_data["sell_idr"].apply(format_rp),
                    "Harga Beli": sub_data["buyback_idr"].apply(format_rp)
                })
                st.table(table_detail)
    elif btn_fetch:
        st.warning("Data kosong. Silakan cek koneksi atau upload source StarGold.")

with tab2:
    st.subheader("📈 Analisis Grafik dari Google Sheets")
    
    # Pilih tab mana yang ingin dilihat grafiknya
    sheet_to_view = st.selectbox("Pilih Sumber Data Grafik", ["Summary_100g", "Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK_Logam_Mulia", "Agung_Jewellery"])
    
    df_hist = get_full_history(worksheet_name=sheet_to_view)
    
    if not df_hist.empty:
        c1, c2 = st.columns(2)
        with c1:
            v_plot = st.selectbox("Pilih Vendor di Tab Ini", df_hist['vendor'].unique())
        with c2:
            w_plot = st.selectbox("Pilih Berat Emas", sorted(df_hist['weight_g'].unique()), key="w_plot")
            
        plot_df = df_hist[(df_hist['vendor'] == v_plot) & (df_hist['weight_g'] == w_plot)]
        
        if not plot_df.empty:
            fig = px.line(plot_df, x="timestamp", y="sell_idr", markers=True, 
                          title=f"Tren Harga {v_plot} {w_plot}g (Sumber: {sheet_to_view})")
            st.plotly_chart(fig, width='stretch')
        
        with st.expander("📂 Lihat Data Mentah di Google Sheets"):
            st.dataframe(df_hist.sort_values("timestamp", ascending=False), width='stretch')
    else:
        st.info(f"Tab '{sheet_to_view}' di Google Sheets masih kosong. Silakan simpan data terlebih dahulu.")
