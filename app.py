import streamlit as st
import requests
import pandas as pd
from io import BytesIO
import plotly.express as px

# =========================================================
# IMPORT SCRAPERS
# =========================================================
from scrapers.galeri24 import parse_galeri24, URL_GALERI24
from scrapers.stargold import parse_stargold, URL_STARGOLD
from scrapers.anekalogam import parse_anekalogam, URL_ANEKALOGAM
from scrapers.hrta import parse_hrta, URL_HRTA
from scrapers.indogold import parse_indogold, URL_INDOGOLD
from scrapers.hakabegold import parse_hakabegold, URL_HAKABEGOLD
from scrapers.agungjewellery import parse_agungjewellery

# === UTILS UNTUK HISTORI & UPLOAD ===
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
    """Format angka ke Rupiah dengan pemisah titik."""
    try:
        # Perbaikan Syntax: Menghapus backslash yang merusak string literal
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
    source = st.selectbox(
        "Pilih Sumber Data",
        ["StarGold", "Galeri24", "Aneka Logam", "HRTA", "IndoGold", "Hakabe Gold", "Agung Jewellery"]
    )
    
    refresh = st.button("🔄 Tarik Data Sekarang", use_container_width=True)
    
    # Fitur Upload Manual (utils/uploader.py)
    render_uploader_sidebar()

# =========================================================
# MAIN CONTENT
# =========================================================
st.title("📊 Monitoring Harga Emas")

# Navigasi Tab
tab1, tab2 = st.tabs(["🕒 Harga Realtime", "📈 Grafik Histori"])

with tab1:
    if refresh:
        st.cache_data.clear()

    try:
        df = pd.DataFrame()
        update_label = ""

        # Logic Penarikan Data
        if source == "StarGold":
            # StarGold menggunakan radar file internal
            df, update_label = parse_stargold("") 
        elif source == "Galeri24":
            html = fetch_html(URL_GALERI24)
            df, update_label = parse_galeri24(html)
        elif source == "Aneka Logam":
            html = fetch_html(URL_ANEKALOGAM)
            df, update_label = parse_anekalogam(html)
        elif source == "HRTA":
            html = fetch_html(URL_HRTA)
            df, update_label = parse_hrta(html)
        elif source == "IndoGold":
            html = fetch_html(URL_INDOGOLD)
            df, update_label = parse_indogold(html)
        elif source == "Hakabe Gold":
            html = fetch_html(URL_HAKABEGOLD)
            df, update_label = parse_hakabegold(html)
        elif source == "Agung Jewellery":
            df, update_label = parse_agungjewellery()

        if not df.empty:
            st.info(f"💡 {update_label}")

            # Tampilan per Vendor
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

            # Ekspor Data
            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                st.download_button("📥 Download CSV", df.to_csv(index=False).encode("utf-8-sig"), f"{source}.csv", "text/csv", use_container_width=True)
            with c2:
                out = BytesIO()
                with pd.ExcelWriter(out, engine="openpyxl") as w:
                    df.to_excel(w, index=False, sheet_name="Data")
                st.download_button("📥 Download Excel", out.getvalue(), f"{source}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        else:
            st.warning(f"Data kosong atau gagal diambil: {update_label}")

    except Exception as e:
        st.error(f"Terjadi kesalahan fatal: {e}")

with tab2:
    st.subheader("📈 Tren Pergerakan Harga")
    # Ambil histori dari utils/history_manager.py
    df_hist = get_full_history()
    
    if not df_hist.empty:
        col1, col2 = st.columns(2)
        with col1:
            v_plot = st.selectbox("Pilih Vendor", df_hist['vendor'].unique())
        with col2:
            w_plot = st.selectbox("Pilih Berat (gr)", sorted(df_hist['weight_g'].unique()))
        
        filtered_hist = df_hist[(df_hist['vendor'] == v_plot) & (df_hist['weight_g'] == w_plot)]
        
        if not filtered_hist.empty:
            fig = px.line(
                filtered_hist, 
                x="timestamp", 
                y="sell_idr", 
                markers=True, 
                title=f"Pergerakan Harga {v_plot} {w_plot} gr"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander("Lihat Log Seluruh Data"):
                st.dataframe(df_hist.sort_values("timestamp", ascending=False), use_container_width=True)
        else:
            st.info("Data histori untuk kombinasi ini belum tersedia.")
    else:
        st.info("Belum ada histori tersimpan. Silakan upload file source web di sidebar.")
