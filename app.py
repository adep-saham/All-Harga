import streamlit as st
import requests
import pandas as pd
import plotly.express as px  # Perbaikan: Menghindari NameError saat memuat grafik
from datetime import datetime
import time # Perbaikan: Menghindari NameError saat menggunakan progress bar
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
    """Mengambil data perbandingan khusus 100gr dari semua sumber"""
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
                # Filter khusus untuk memastikan data 100gr (ANTAM/STARGOLD)
                if name == "StarGold":
                    mask = (df_tmp['vendor'].str.contains('ANTAM|STARGOLD', case=False)) & (df_tmp['weight_g'] == 100)
                elif name in ["Galeri 24", "IndoGold"]:
                    mask = (df_tmp['vendor'].str.contains('ANTAM', case=False)) & (df_tmp['weight_g'] == 100)
                else:
                    mask = (df_tmp['weight_g'] == 100)
                
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

def fetch_all_vendors_full():
    """Menarik semua data lengkap dari semua vendor"""
    all_data = []
    scrapers = [
        ("StarGold", lambda: parse_stargold("")),
        ("Galeri 24", lambda: parse_galeri24(fetch_html(URL_GALERI24))),
        ("Aneka Logam", lambda: parse_anekalogam(fetch_html(URL_ANEKALOGAM))),
        ("HRTA GOLD", lambda: parse_hrta("")),
        ("IndoGold", lambda: parse_indogold(fetch_html(URL_INDOGOLD))),
        ("HK Logam Mulia", lambda: parse_hakabegold()),
        ("Agung Jewellery", lambda: parse_agungjewellery()),
    ]
    my_bar = st.progress(0, text="Menarik data...")
    for i, (name, func) in enumerate(scrapers):
        my_bar.progress((i / len(scrapers)), text=f"Scraping: {name}...")
        try:
            df_tmp, update_label = func()
            if df_tmp is not None and not df_tmp.empty:
                df_tmp['source_update'] = update_label
                if 'vendor' not in df_tmp.columns: df_tmp['vendor'] = name
                all_data.append(df_tmp)
        except: pass
    my_bar.progress(1.0, text="Selesai.")
    time.sleep(0.5) 
    my_bar.empty()
    if all_data:
        full = pd.concat(all_data, ignore_index=True)
        full['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return full
    return pd.DataFrame()

def create_excel_bytes(df):
    """Fungsi pembuatan Excel lokal dengan proteksi nama sheet duplikat"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        used_names = set()
        df_100 = df[df['weight_g'] == 100].copy()
        if not df_100.empty:
            df_100.to_excel(writer, index=False, sheet_name="Summary_100g")
            used_names.add("SUMMARY_100G")
            
        for vendor in df['vendor'].unique():
            base_name = str(vendor).upper().replace(" ", "_").replace("/", "")[:25]
            clean_name = base_name
            counter = 1
            while clean_name in used_names:
                clean_name = f"{base_name}_{counter}"
                counter += 1
            used_names.add(clean_name)
            df[df['vendor'] == vendor].to_excel(writer, index=False, sheet_name=clean_name)
    output.seek(0)
    return output

# =========================================================
# UI SIDEBAR
# =========================================================
st.sidebar.title("⚙️ Kontrol")
mode = st.sidebar.radio("Mode Tampilan", ["📊 Perbandingan 100g (All)", "🏪 Detail Per Toko"])
if mode == "🏪 Detail Per Toko":
    source_opt = st.sidebar.selectbox("Pilih Toko", ["Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK Logam Mulia", "Agung Jewellery"])
else: source_opt = "All 100g"

btn_fetch = st.sidebar.button("🚀 Lihat Data Terbaru", width='stretch')

st.sidebar.divider()

# FITUR SIMPAN: Summary 100g & Detail Per Toko
if st.sidebar.button("💾 Simpan Semua ke Google Sheets", type="primary", width='stretch'):
    with st.spinner("Sedang scraping & menyimpan data lengkap..."):
        df_full = fetch_all_vendors_full() 
        if not df_full.empty:
            # Simpan Summary 100g
            df_100g = df_full[df_full['weight_g'] == 100].copy()
            if not df_100g.empty:
                save_to_history(df_100g, worksheet_name="Summary_100g")
            
            # Simpan Detail Per Toko ke Worksheet Masing-Masing
            for vendor in df_full['vendor'].unique():
                df_vendor = df_full[df_full['vendor'] == vendor].copy()
                ws_name = str(vendor).replace(" ", "_")
                save_to_history(df_vendor, worksheet_name=ws_name)
            
            st.sidebar.success("✅ Semua Data Berhasil Tersimpan!")
        else:
            st.sidebar.error("❌ Gagal menarik data.")

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
            if source_opt == "StarGold": df_detail, ul = parse_stargold("")
            elif source_opt == "HK Logam Mulia": df_detail, ul = parse_hakabegold()
            elif source_opt == "Agung Jewellery": df_detail, ul = parse_agungjewellery()
            elif source_opt == "HRTA": df_detail, ul = parse_hrta("")
            else:
                url = {"Galeri24": URL_GALERI24, "AnekaLogam": URL_ANEKALOGAM, "IndoGold": URL_INDOGOLD}.get(source_opt)
                html = fetch_html(url)
                if source_opt == "Galeri24": df_detail, ul = parse_galeri24(html)
                elif source_opt == "AnekaLogam": df_detail, ul = parse_anekalogam(html)
                elif source_opt == "IndoGold": df_detail, ul = parse_indogold(html)
            if not df_detail.empty: df_detail['source_update'] = ul
            st.session_state['current_df'] = df_detail

    if 'current_df' in st.session_state and not st.session_state['current_df'].empty:
        df_active = st.session_state['current_df']
        if mode == "📊 Perbandingan 100g (All)":
            st.subheader("📋 Tabel Perbandingan Antam 100 gr")
            df_table = df_active.sort_values("sell_idr").reset_index(drop=True)
            st.dataframe(pd.DataFrame({
                "No": range(1, len(df_table) + 1),
                "Nama Toko": df_table["vendor"],
                "Jual": df_table["sell_idr"].apply(format_rp),
                "Beli": df_table["buyback_idr"].apply(format_rp),
                "Update": df_table["source_update"]
            }), width='stretch', hide_index=True)
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
    sheet_to_view = st.selectbox("Sumber Data", ["Summary_100g", "Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK_Logam_Mulia", "Agung_Jewellery"])
    df_hist = get_full_history(worksheet_name=sheet_to_view)
    if not df_hist.empty:
        c1, c2 = st.columns(2)
        v_plot = c1.selectbox("Vendor", df_hist['vendor'].unique())
        w_plot = c2.selectbox("Berat", sorted(df_hist['weight_g'].unique()))
        plot_df = df_hist[(df_hist['vendor'] == v_plot) & (df_hist['weight_g'] == w_plot)]
        if not plot_df.empty:
            st.plotly_chart(px.line(plot_df, x="timestamp", y="sell_idr", markers=True, title=f"Tren Harga {v_plot} {w_plot}g"), width='stretch')
