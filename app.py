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

# Mengimpor fungsi manajemen histori dari folder utils
try:
    from utils.uploader import render_uploader_sidebar
    from utils.history_manager import get_full_history, save_to_history
except ImportError:
    # Fallback jika file utils belum tersedia
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
    """Format angka ke Rupiah dengan pemisah titik."""
    try:
        return f"Rp{int(x):,}".replace(",", ".")
    except Exception:
        return "Rp0"

@st.cache_data(ttl=300)
def fetch_html(url: str) -> str:
    """Fetcher HTML umum dengan penanganan error."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        return r.text or ""
    except Exception:
        return ""

def get_all_comparison_100g():
    """Mengumpulkan data 100g dari semua sumber dengan filter brand yang tepat."""
    results = []
    # Urutan vendor sesuai permintaan gambar
    scrapers = [
        ("Stargold", lambda: parse_stargold("")),
        ("Galeri 24", lambda: parse_galeri24(fetch_html(URL_GALERI24))),
        ("Aneka Logam", lambda: parse_anekalogam(fetch_html(URL_ANEKALOGAM))),
        ("HRTA", lambda: parse_hrta("")),
        ("Indogold", lambda: parse_indogold(fetch_html(URL_INDOGOLD))),
        ("Hakabe Gold", lambda: parse_hakabegold()),
        ("Agung Jewellery", lambda: parse_agungjewellery()),
    ]

    for source_name, func in scrapers:
        try:
            df_tmp, _ = func()
            if df_tmp is not None and not df_tmp.empty:
                # Filter Antam hanya untuk toko yang multi-brand
                if source_name in ["Galeri 24", "Stargold", "Indogold"]:
                    mask = (df_tmp['vendor'].str.contains('ANTAM', case=False, na=False)) & \
                           (df_tmp['weight_g'] == 100)
                else:
                    # Untuk toko brand tunggal, langsung ambil 100g
                    mask = (df_tmp['weight_g'] == 100)
                
                filtered = df_tmp[mask].copy()
                if not filtered.empty:
                    row = filtered.sort_values("sell_idr").iloc[0]
                    results.append({
                        "vendor": source_name, # Nama bersih untuk tabel
                        "weight_g": 100,
                        "sell_idr": row['sell_idr'],
                        "buyback_idr": row['buyback_idr']
                    })
        except Exception:
            continue
            
    return pd.DataFrame(results)

# =========================================================
# SIDEBAR
# =========================================================
st.sidebar.title("⚙️ Kontrol")

mode = st.sidebar.radio(
    "Mode Tampilan",
    ["📊 Perbandingan 100g (All)", "🏪 Detail Per Toko"],
    index=0
)

# Pilihan toko hanya muncul jika mode Detail dipilih
if mode == "🏪 Detail Per Toko":
    source = st.sidebar.selectbox(
        "Pilih Toko",
        ["Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK Logam Mulia", "Agung Jewellery"]
    )
else:
    source = "All 100g"

btn_fetch = st.sidebar.button("🚀 Tarik Data Sekarang", use_container_width=True, type="primary")

st.sidebar.divider()
render_uploader_sidebar() # Jalankan fitur upload manual

# =========================================================
# MAIN CONTENT
# =========================================================
st.title("📊 Monitoring Harga Emas")

tab1, tab2 = st.tabs(["🕒 Harga Realtime", "📈 Grafik Histori"])

with tab1:
    # 1. LOGIKA TARIK DATA (Disimpan ke Session State agar bisa disimpan ke Histori)
    if btn_fetch:
        st.cache_data.clear()
        if mode == "📊 Perbandingan 100g (All)":
            with st.spinner("Menyelaraskan harga 100g seluruh toko..."):
                st.session_state['current_df'] = get_all_comparison_100g()
        else:
            with st.spinner(f"Mengambil data lengkap {source}..."):
                df_detail = pd.DataFrame()
                if source == "HK Logam Mulia": df_detail, _ = parse_hakabegold()
                elif source == "StarGold": df_detail, _ = parse_stargold("")
                elif source == "Agung Jewellery": df_detail, _ = parse_agungjewellery()
                elif source == "HRTA": df_detail, _ = parse_hrta("")
                else:
                    url = {"Galeri24": URL_GALERI24, "AnekaLogam": URL_ANEKALOGAM, "IndoGold": URL_INDOGOLD}.get(source)
                    html = fetch_html(url)
                    if source == "Galeri24": df_detail, _ = parse_galeri24(html)
                    elif source == "AnekaLogam": df_detail, _ = parse_anekalogam(html)
                    elif source == "IndoGold": df_detail, _ = parse_indogold(html)
                st.session_state['current_df'] = df_detail

    # 2. TAMPILAN DATA & TOMBOL SIMPAN HISTORI
    if 'current_df' in st.session_state and not st.session_state['current_df'].empty:
        df_active = st.session_state['current_df']
        
        # Tombol simpan muncul di bawah penarikan data
        if st.button("💾 Simpan Data ke Histori CSV", use_container_width=True):
            save_to_history(df_active)
            st.success("✅ Berhasil menyimpan data ke dalam histori!")

        st.divider()

        if mode == "📊 Perbandingan 100g (All)":
            st.subheader("📋 Tabel Perbandingan Emas 100 gr")
            
            # Pengolahan tabel agar rapi dan urut harga termurah
            df_table = df_active.sort_values("sell_idr").reset_index(drop=True)
            
            # Membuat DataFrame tampilan persis seperti gambar
            display_data = pd.DataFrame({
                "No": range(1, len(df_table) + 1),
                "Nama Toko Emas": df_table["vendor"],
                "Harga Jual": df_table["sell_idr"].apply(format_rp),
                "Harga Beli": df_table["buyback_idr"].apply(format_rp)
            })
            
            # Menggunakan hide_index agar tidak ada kolom index bawaan streamlit yang double
            st.dataframe(display_data, use_container_width=True, hide_index=True)
            
        else:
            # Tampilan Detail Per Toko (Mode Lama)
            for v_name in df_active["vendor"].unique():
                st.subheader(f"🏢 {v_name}")
                sub_data = df_active[df_active["vendor"] == v_name].sort_values("weight_g")
                
                table_detail = pd.DataFrame({
                    "Berat": sub_data["weight_g"].apply(lambda x: f"{x:g} gr"),
                    "Harga Jual": sub_data["sell_idr"].apply(format_rp),
                    "Harga Buyback": sub_data["buyback_idr"].apply(format_rp)
                })
                st.table(table_detail)

    elif btn_fetch:
        st.warning("Data tidak tersedia. Coba cek koneksi atau upload file source.")

with tab2:
    st.subheader("📈 Grafik Pergerakan Harga")
    df_hist = get_full_history()
    if not df_hist.empty:
        c1, c2 = st.columns(2)
        with c1:
            v_plot = st.selectbox("Pilih Toko", df_hist['vendor'].unique(), key="v")
        with c2:
            w_plot = st.selectbox("Pilih Berat", sorted(df_hist['weight_g'].unique()), key="w")
            
        plot_df = df_hist[(df_hist['vendor'] == v_plot) & (df_hist['weight_g'] == w_plot)]
        if not plot_df.empty:
            fig = px.line(plot_df, x="timestamp", y="sell_idr", markers=True, 
                          title=f"Tren Harga {v_plot} {w_plot}g")
            st.plotly_chart(fig, use_container_width=True)
        
        with st.expander("📂 Database Histori (CSV)"):
            st.dataframe(df_hist.sort_values("timestamp", ascending=False), use_container_width=True)
    else:
        st.info("Belum ada histori. Klik 'Simpan Data' pada Tab Harga Realtime.")
