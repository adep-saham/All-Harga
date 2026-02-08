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

try:
    from utils.uploader import render_uploader_sidebar
    from utils.history_manager import get_full_history, save_to_history
except ImportError:
    def render_uploader_sidebar(): pass
    def get_full_history(): return pd.DataFrame()
    def save_to_history(df): pass

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
    """Mengumpulkan data 100g dengan nama toko yang bersih."""
    results = []
    # Daftar urutan vendor
    scrapers = [
        ("StarGold", lambda: parse_stargold("")),
        ("Galeri 24", lambda: parse_galeri24(fetch_html(URL_GALERI24))),
        ("Aneka Logam", lambda: parse_anekalogam(fetch_html(URL_ANEKALOGAM))),
        ("HRTA GOLD", lambda: parse_hrta("")),
        ("IndoGold", lambda: parse_indogold(fetch_html(URL_INDOGOLD))),
        ("HK Logam Mulia", lambda: parse_hakabegold()),
        ("Agung Jewellery", lambda: parse_agungjewellery()),
    ]

    for source_name, func in scrapers:
        try:
            df_tmp, _ = func()
            if df_tmp is not None and not df_tmp.empty:
                # Filter Antam atau produk utama 100g
                if source_name in ["Galeri 24", "StarGold", "IndoGold"]:
                    mask = (df_tmp['vendor'].str.contains('ANTAM', case=False, na=False)) & (df_tmp['weight_g'] == 100)
                else:
                    mask = (df_tmp['weight_g'] == 100)
                
                filtered = df_tmp[mask].copy()
                if not filtered.empty:
                    # Ambil satu baris termurah jika ada beberapa pilihan Antam
                    row = filtered.sort_values("sell_idr").iloc[0]
                    results.append({
                        "vendor": source_name, # Menggunakan nama bersih dari list kita
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

btn_fetch = st.sidebar.button("🚀 Tarik Data Sekarang", use_container_width=True, type="primary")

st.sidebar.divider()
render_uploader_sidebar()

# =========================================================
# MAIN CONTENT
# =========================================================
st.title("📊 Monitoring Harga Emas")

tab1, tab2 = st.tabs(["🕒 Harga Realtime", "📈 Grafik Histori"])

with tab1:
    # 1. LOGIKA AMBIL DATA
    if btn_fetch:
        st.cache_data.clear()
        if mode == "📊 Perbandingan 100g (All)":
            with st.spinner("Menyelaraskan harga 100g..."):
                st.session_state['current_df'] = get_all_comparison_100g()
        else:
            with st.spinner(f"Mengambil data {source}..."):
                df_detail = pd.DataFrame()
                if source == "HK Logam Mulia": df_detail, _ = parse_hakabegold()
                elif source == "StarGold": df_detail, _ = parse_stargold("")
                elif source == "Agung Jewellery": df_detail, _ = parse_agungjewellery()
                elif source == "HRTA": df_detail, _ = parse_hrta("")
                else:
                    target_url = {"Galeri24": URL_GALERI24, "AnekaLogam": URL_ANEKALOGAM, "IndoGold": URL_INDOGOLD}.get(source)
                    html = fetch_html(target_url)
                    if source == "Galeri24": df_detail, _ = parse_galeri24(html)
                    elif source == "AnekaLogam": df_detail, _ = parse_anekalogam(html)
                    elif source == "IndoGold": df_detail, _ = parse_indogold(html)
                st.session_state['current_df'] = df_detail

    # 2. TAMPILAN DATA & TOMBOL SIMPAN
    if 'current_df' in st.session_state and not st.session_state['current_df'].empty:
        df_active = st.session_state['current_df']
        
        # Tombol Simpan Histori
        if st.button("💾 Simpan Data ke Histori CSV", use_container_width=True):
            save_to_history(df_active)
            st.success("✅ Berhasil! Data telah dicatat ke database histori.")

        st.divider()

        if mode == "📊 Perbandingan 100g (All)":
            st.subheader("📋 Tabel Perbandingan Emas 100 gr")
            
            # Persiapkan tabel yang rapi
            df_table = df_active.sort_values("sell_idr").reset_index(drop=True)
            
            # Buat DataFrame tampilan agar tidak ada index ganda
            display_data = pd.DataFrame({
                "No": range(1, len(df_table) + 1),
                "Nama Toko Emas": df_table["vendor"],
                "Harga Jual": df_table["sell_idr"].apply(format_rp),
                "Harga Beli": df_table["buyback_idr"].apply(format_rp)
            })
            
            # Menggunakan dataframe dengan hide_index agar angka tidak double
            st.dataframe(display_data, use_container_width=True, hide_index=True)
            
            best_deal = df_table.iloc[0]
            st.info(f"💡 Rekomendasi: Harga termurah di **{best_deal['vendor']}** ({format_rp(best_deal['sell_idr'])})")

        else:
            # Tampilan per Toko (Detail)
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
        st.warning("Data tidak tersedia. Coba cek koneksi atau upload file source.")

with tab2:
    st.subheader("📈 Analisis Pergerakan Harga")
    df_hist = get_full_history()
    if not df_hist.empty:
        col1, col2 = st.columns(2)
        with col1:
            v_plot = st.selectbox("Pilih Toko", df_hist['vendor'].unique(), key="plot_v")
        with col2:
            w_plot = st.selectbox("Pilih Berat", sorted(df_hist['weight_g'].unique()), key="plot_w")
            
        plot_df = df_hist[(df_hist['vendor'] == v_plot) & (df_hist['weight_g'] == w_plot)]
        if not plot_df.empty:
            import plotly.express as px
            fig = px.line(plot_df, x="timestamp", y="sell_idr", markers=True, 
                          title=f"Tren Harga {v_plot} {w_plot}g")
            st.plotly_chart(fig, use_container_width=True)
        
        with st.expander("📂 Buka Database (CSV)"):
            st.dataframe(df_hist.sort_values("timestamp", ascending=False), use_container_width=True)
    else:
        st.info("Belum ada histori. Silakan klik 'Simpan Data' pada tab Harga Realtime.")
