
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
    """Mengumpulkan data 100g dari semua sumber + Waktu Update Web."""
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
            df_tmp, update_label = func() # Menangkap label waktu dari scraper
            if df_tmp is not None and not df_tmp.empty:
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
                        "buyback_idr": row['buyback_idr'],
                        "source_update": update_label # Simpan waktu update dari web
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
    target_sheet = source_opt.replace(" ", "_")
else:
    source_opt = "All 100g"
    target_sheet = "Summary_100g"

btn_fetch = st.sidebar.button("🚀 Tarik Data Sekarang", width='stretch', type="primary")

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
            df_detail = pd.DataFrame()
            # Logika detail per toko (tetap menyertakan update_label)
            if source_opt == "HK Logam Mulia": df_detail, ul = parse_hakabegold()
            elif source_opt == "StarGold": df_detail, ul = parse_stargold("")
            elif source_opt == "Agung Jewellery": df_detail, ul = parse_agungjewellery()
            elif source_opt == "HRTA": df_detail, ul = parse_hrta("")
            else:
                url = {"Galeri24": URL_GALERI24, "AnekaLogam": URL_ANEKALOGAM, "IndoGold": URL_INDOGOLD}.get(source_opt)
                html = fetch_html(url)
                if source_opt == "Galeri24": df_detail, ul = parse_galeri24(html)
                elif source_opt == "AnekaLogam": df_detail, ul = parse_anekalogam(html)
                elif source_opt == "IndoGold": df_detail, ul = parse_indogold(html)
            
            # Tambahkan kolom source_update ke df_detail agar bisa masuk ke Sheet Toko
            if not df_detail.empty:
                df_detail['source_update'] = ul
            st.session_state['current_df'] = df_detail

    if 'current_df' in st.session_state and not st.session_state['current_df'].empty:
        df_active = st.session_state['current_df']
        
        if st.button(f"💾 Simpan ke Google Sheet: {target_sheet}", width='stretch'):
            if save_to_history(df_active, worksheet_name=target_sheet):
                st.success(f"✅ Data berhasil dicatat di tab '{target_sheet}'")

        if mode == "📊 Perbandingan 100g (All)":
            st.subheader("📋 Tabel Perbandingan Antam 100 gr")
            df_table = df_active.sort_values("sell_idr").reset_index(drop=True)
            display_data = pd.DataFrame({
                "No": range(1, len(df_table) + 1),
                "Nama Toko Emas": df_table["vendor"],
                "Harga Jual": df_table["sell_idr"].apply(format_rp),
                "Harga Beli": df_table["buyback_idr"].apply(format_rp),
                "Update di Web": df_table["source_update"]
            })
            st.dataframe(display_data, width='stretch', hide_index=True)
        else:
            for v_name in df_active["vendor"].unique():
                st.subheader(f"🏢 {v_name}")
                sub = df_active[df_active["vendor"] == v_name].sort_values("weight_g")
                st.table(pd.DataFrame({
                    "Berat": sub["weight_g"].apply(lambda x: f"{x:g} gr"),
                    "Harga Jual": sub["sell_idr"].apply(format_rp),
                    "Harga Beli": sub["buyback_idr"].apply(format_rp)
                }))

with tab2:
    st.subheader("📈 Grafik Histori")
    sheet_to_view = st.selectbox("Pilih Sumber Data Grafik", ["Summary_100g", "Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK_Logam_Mulia", "Agung_Jewellery"])
    df_hist = get_full_history(worksheet_name=sheet_to_view)
    
    if not df_hist.empty:
        c1, c2 = st.columns(2)
        v_plot = c1.selectbox("Pilih Vendor", df_hist['vendor'].unique())
        w_plot = c2.selectbox("Pilih Berat", sorted(df_hist['weight_g'].unique()), key="w_plot")
        
        plot_df = df_hist[(df_hist['vendor'] == v_plot) & (df_hist['weight_g'] == w_plot)]
        if not plot_df.empty:
            st.plotly_chart(px.line(plot_df, x="timestamp", y="sell_idr", markers=True, title=f"Tren {v_plot} {w_plot}g"), width='stretch')
        st.expander("📂 Lihat Data Mentah").dataframe(df_hist.sort_values("timestamp", ascending=False), width='stretch')
