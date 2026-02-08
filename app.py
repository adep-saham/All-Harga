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
from utils.history_manager import get_full_history

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
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception as e:
        return f"ERROR: {e}"

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.title("⚙️ Kontrol")
    
    # FITUR BARU: Mode Dashboard
    mode = st.radio(
        "Pilih Mode Tampilan",
        ["Monitoring Antam 100g", "Detail Vendor (Lama)"]
    )
    
    st.divider()
    
    if mode == "Detail Vendor (Lama)":
        source = st.selectbox(
            "Pilih Sumber Data",
            ["StarGold", "Galeri24", "Aneka Logam", "HRTA", "IndoGold", "Hakabe Gold", "Agung Jewellery"]
        )
    
    refresh = st.button("🔄 Tarik / Refresh Data", use_container_width=True, type="primary")
    
    # Jalankan uploader sidebar
    render_uploader_sidebar()

# =========================================================
# MAIN CONTENT
# =========================================================
st.title("📊 Monitoring Harga Emas")

tab1, tab2 = st.tabs(["🕒 Harga Realtime", "📈 Grafik Histori"])

with tab1:
    if refresh:
        st.cache_data.clear()

    try:
        if mode == "Monitoring Antam 100g":
            st.subheader("🏆 Perbandingan Khusus: Antam 100 Gram")
            with st.spinner("Menarik data dari seluruh vendor..."):
                all_results = []
                
                # List fungsi tarik data
                # 1. StarGold (File)
                df_sg, _ = parse_stargold("")
                if not df_sg.empty: all_results.append(df_sg)
                
                # 2. Galeri24 (Live)
                df_g24, _ = parse_galeri24(fetch_html(URL_GALERI24))
                if not df_g24.empty: all_results.append(df_g24)
                
                # 3. Hakabe (Live)
                df_hk, _ = parse_hakabegold(fetch_html(URL_HAKABEGOLD))
                if not df_hk.empty: all_results.append(df_hk)
                
                # 4. Aneka Logam (Live)
                df_al, _ = parse_anekalogam(fetch_html(URL_ANEKALOGAM))
                if not df_al.empty: all_results.append(df_al)

                if all_results:
                    master_df = pd.concat(all_results, ignore_index=True)
                    # Filter: Vendor mengandung ANTAM & Berat 100
                    mask = (master_df['vendor'].str.contains('ANTAM', case=False, na=False)) & (master_df['weight_g'] == 100)
                    df_100 = master_df[mask].copy()
                    
                    if not df_100.empty:
                        df_100 = df_100.sort_values("sell_idr", ascending=True)
                        
                        # Metrics
                        c1, c2, c3 = st.columns(3)
                        best = df_100.iloc[0]
                        c1.metric("Harga Termurah", format_rp(best['sell_idr']), best['vendor'])
                        c2.metric("Rata-rata Pasar", format_rp(df_100['sell_idr'].mean()))
                        c3.metric("Jumlah Vendor", f"{len(df_100)} Toko")

                        st.divider()
                        
                        # Tabel
                        disp = pd.DataFrame({
                            "Vendor": df_100["vendor"],
                            "Harga Jual": df_100["sell_idr"].apply(format_rp),
                            "Harga Buyback": df_100["buyback_idr"].apply(format_rp),
                            "Spread": (df_100["sell_idr"] - df_100["buyback_idr"]).apply(format_rp)
                        })
                        st.table(disp)
                    else:
                        st.warning("Data Antam 100g belum tersedia di sumber yang ditarik.")
                else:
                    st.error("Gagal mendapatkan data.")

        else:
            # === LOGIKA LAMA (Detail Vendor) ===
            df = pd.DataFrame()
            update_label = ""

            if source == "StarGold":
                df, update_label = parse_stargold("") 
            elif source == "Galeri24":
                df, update_label = parse_galeri24(fetch_html(URL_GALERI24))
            elif source == "Aneka Logam":
                df, update_label = parse_anekalogam(fetch_html(URL_ANEKALOGAM))
            elif source == "HRTA":
                df, update_label = parse_hrta(fetch_html(URL_HRTA))
            elif source == "IndoGold":
                df, update_label = parse_indogold(fetch_html(URL_INDOGOLD))
            elif source == "Hakabe Gold":
                df, update_label = parse_hakabegold(fetch_html(URL_HAKABEGOLD))
            elif source == "Agung Jewellery":
                df, update_label = parse_agungjewellery()

            if not df.empty:
                st.info(f"💡 {update_label}")
                vendors = df["vendor"].unique()
                for v in vendors:
                    st.subheader(f"🏢 {v}")
                    sub = df[df["vendor"] == v]
                    display = pd.DataFrame({
                        "Berat": sub["weight_g"].apply(lambda x: f"{x:g} gr"),
                        "Harga Jual": sub["sell_idr"].apply(format_rp),
                        "Harga Buyback": sub["buyback_idr"].apply(format_rp),
                        "Stok": sub.get("stock", "Ready"),
                    })
                    st.table(display)
            else:
                st.warning(f"Data kosong: {update_label}")

    except Exception as e:
        st.error(f"Kesalahan: {e}")

with tab2:
    st.subheader("📈 Tren Harga Antam 100g")
    df_hist = get_full_history()
    if not df_hist.empty:
        # Filter histori khusus 100g antam untuk grafik default
        df_hist_100 = df_hist[
            (df_hist['vendor'].str.contains('ANTAM', case=False, na=False)) & 
            (df_hist['weight_g'] == 100)
        ]
        
        if not df_hist_100.empty:
            fig = px.line(df_hist_100, x="timestamp", y="sell_idr", color="vendor", markers=True)
            st.plotly_chart(fig, use_container_width=True)
        
        with st.expander("Lihat Log Semua Data"):
            st.dataframe(df_hist, use_container_width=True)
    else:
        st.info("Belum ada data histori.")
