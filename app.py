import streamlit as st
import requests
import pandas as pd
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
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Monitoring Harga Emas",
    layout="wide"
)

# =========================================================
# HELPERS
# =========================================================
def format_rp(x):
    try:
        return f"Rp{int(x):,}".replace(",", ".")
    except Exception:
        return "Rp0"

@st.cache_data(ttl=300)
def fetch_html(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        return r.text or ""
    except Exception:
        return ""

def get_all_comparison_100g():
    results = []
    scrapers = [
        ("StarGold", lambda: parse_stargold("")),
        ("Galeri 24", lambda: parse_galeri24(fetch_html(URL_GALERI24))),
        ("Aneka Logam", lambda: parse_anekalogam(fetch_html(URL_ANEKALOGAM))),
        ("HRTA", lambda: parse_hrta("")),
        ("IndoGold", lambda: parse_indogold(fetch_html(URL_INDOGOLD))),
        ("Hakabe Gold", lambda: parse_hakabegold()),
        ("Agung Jewellery", lambda: parse_agungjewellery()),
    ]
    for source_name, func in scrapers:
        try:
            df_tmp, _ = func()
            if df_tmp is not None and not df_tmp.empty:
                # Logika Filter Brand Antam atau Utama
                if source_name in ["Galeri 24", "StarGold", "IndoGold"]:
                    mask = (df_tmp['vendor'].str.contains('ANTAM', case=False, na=False)) & (df_tmp['weight_g'] == 100)
                else:
                    mask = (df_tmp['weight_g'] == 100)
                
                filtered = df_tmp[mask].copy()
                if not filtered.empty:
                    row = filtered.sort_values("sell_idr").iloc[0]
                    # Pastikan kolom vendor tetap ada untuk database
                    results.append({
                        "vendor": row['vendor'] if 'vendor' in row else source_name,
                        "weight_g": 100,
                        "sell_idr": row['sell_idr'],
                        "buyback_idr": row['buyback_idr']
                    })
        except Exception: continue
    return pd.DataFrame(results)

# =========================================================
# UI SIDEBAR
# =========================================================
st.sidebar.title("⚙️ Kontrol")

mode = st.sidebar.radio(
    "Mode Tampilan",
    ["📊 Perbandingan 100g (All)", "🏪 Detail Per Toko"],
    index=0
)

if mode == "🏪 Detail Per Toko":
    source = st.sidebar.selectbox(
        "Pilih Toko",
        ["Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK Logam Mulia", "Agung Jewellery"]
    )
else:
    source = "All 100g"

btn_fetch = st.sidebar.button("🚀 Tarik Data", use_container_width=True, type="primary")

st.sidebar.divider()
render_uploader_sidebar()

# =========================================================
# MAIN CONTENT
# =========================================================
st.title("📊 Monitoring Harga Emas")

tab1, tab2 = st.tabs(["🕒 Harga Realtime", "📈 Grafik Histori"])

with tab1:
    # 1. LOGIKA TARIK DATA
    if btn_fetch:
        st.cache_data.clear()
        if mode == "📊 Perbandingan 100g (All)":
            with st.spinner("Menyelaraskan harga 100g..."):
                st.session_state['current_df'] = get_all_comparison_100g()
        else:
            with st.spinner(f"Mengambil data {source}..."):
                # Mapping Scraper Detail
                df_detail = pd.DataFrame()
                if source == "HK Logam Mulia": df_detail, _ = parse_hakabegold()
                elif source == "StarGold": df_detail, _ = parse_stargold("")
                elif source == "Agung Jewellery": df_detail, _ = parse_agungjewellery()
                elif source == "HRTA": df_detail, _ = parse_hrta("")
                else:
                    html = fetch_html({"Galeri24": URL_GALERI24, "AnekaLogam": URL_ANEKALOGAM, "IndoGold": URL_INDOGOLD}.get(source))
                    if source == "Galeri24": df_detail, _ = parse_galeri24(html)
                    elif source == "AnekaLogam": df_detail, _ = parse_anekalogam(html)
                    elif source == "IndoGold": df_detail, _ = parse_indogold(html)
                st.session_state['current_df'] = df_detail

    # 2. TAMPILAN DATA & TOMBOL SIMPAN
    if 'current_df' in st.session_state and not st.session_state['current_df'].empty:
        df_show = st.session_state['current_df']
        
        # Tombol Simpan ke Histori
        if st.button("💾 Simpan Data ke Histori CSV", use_container_width=True):
            save_to_history(df_show)
            st.success("✅ Data berhasil dicatat ke dalam database histori!")

        st.divider()

        if mode == "📊 Perbandingan 100g (All)":
            st.subheader("🏆 Tabel Perbandingan Emas 100 gr")
            df_table = df_show.sort_values("sell_idr").reset_index(drop=True)
            df_table.index += 1
            
            display = pd.DataFrame({
                "No": df_table.index,
                "Nama Toko Emas": df_table["vendor"],
                "Harga Jual": df_table["sell_idr"].apply(format_rp),
                "Harga Beli": df_table["buyback_idr"].apply(format_rp)
            })
            st.table(display)
        else:
            for vendor in df_show["vendor"].unique():
                st.subheader(f"🏢 {vendor}")
                sub = df_show[df_show["vendor"] == vendor].sort_values("weight_g")
                display = pd.DataFrame({
                    "Berat": sub["weight_g"].apply(lambda x: f"{x:g} gr"),
                    "Harga Jual": sub["sell_idr"].apply(format_rp),
                    "Harga Buyback": sub["buyback_idr"].apply(format_rp)
                })
                st.table(display)
    elif btn_fetch:
        st.warning("Data tidak ditemukan atau gagal dimuat.")

with tab2:
    st.subheader("📈 Visualisasi Pergerakan Harga")
    df_hist = get_full_history()
    if not df_hist.empty:
        # Pilihan Grafik
        v_list = df_hist['vendor'].unique()
        v_sel = st.selectbox("Pilih Vendor untuk Grafik", v_list)
        w_sel = st.selectbox("Pilih Berat", sorted(df_hist['weight_g'].unique()), index=0)
        
        plot_df = df_hist[(df_hist['vendor'] == v_sel) & (df_hist['weight_g'] == w_sel)]
        if not plot_df.empty:
            import plotly.express as px
            fig = px.line(plot_df, x="timestamp", y="sell_idr", markers=True, title=f"Tren Harga {v_sel} {w_sel}g")
            st.plotly_chart(fig, use_container_width=True)
        
        with st.expander("📂 Lihat Database Mentah"):
            st.dataframe(df_hist.sort_values("timestamp", ascending=False))
    else:
        st.info("Belum ada data histori. Klik 'Simpan Data ke Histori' di Tab Harga Realtime.")
