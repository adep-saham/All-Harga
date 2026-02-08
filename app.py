import streamlit as st
import requests
import pandas as pd
from io import BytesIO
import plotly.express as px # Tambahkan ini di requirements.txt

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

# === TAMBAHAN UTILS ===
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
        return f"Rp{int(x):,}\".replace(\",\", \".\")
    except Exception:
        return \"Rp0\"


@st.cache_data(ttl=300)
def fetch_html(url: str) -> str:
    try:
        headers = {
            \"User-Agent\": \"Mozilla/5.0\",
            \"Accept-Language\": \"id-ID,id;q=0.9,en-US;q=0.8\",
        }
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception as e:
        return f\"ERROR: {e}\"

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.title("⚙️ Kontrol")
    source = st.selectbox(
        "Pilih Sumber Data",
        ["StarGold", "Galeri24", "Aneka Logam", "HRTA", "IndoGold", "Hakabe Gold", "Agung Jewellery"]
    )
    
    # Tombol Refresh
    refresh = st.button("🔄 Tarik Data Sekarang", use_container_width=True)
    
    # === TAMBAHAN FITUR UPLOAD ===
    render_uploader_sidebar()

# =========================================================
# MAIN CONTENT
# =========================================================
st.title("📊 Monitoring Harga Emas")

# Gunakan Tabs untuk memisahkan Data Realtime dan Histori
tab1, tab2 = st.tabs(["🕒 Harga Realtime", "📈 Grafik Histori"])

with tab1:
    if refresh:
        st.cache_data.clear()

    try:
        df = pd.DataFrame()
        update_label = ""

        if source == "StarGold":
            # StarGold handle internal fetch/file
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

            # Group by vendor jika ada banyak vendor
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

            # DOWNLOAD SECTION
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
    df_hist = get_full_history()
    
    if not df_hist.empty:
        # Filter Grafik
        c1, c2 = st.columns(2)
        with c1:
            v_sel = st.selectbox("Filter Vendor", df_hist['vendor'].unique(), key="v_plot")
        with c2:
            w_sel = st.selectbox("Filter Berat (gr)", sorted(df_hist['weight_g'].unique()), key="w_plot")
        
        df_plot = df_hist[(df_hist['vendor'] == v_sel) & (df_hist['weight_g'] == w_sel)]
        
        if not df_plot.empty:
            fig = px.line(df_plot, x="timestamp", y="sell_idr", markers=True, 
                          title=f"Harga Jual {v_sel} {w_sel} gr",
                          labels={"timestamp": "Waktu Update", "sell_idr": "Harga Jual (IDR)"})
            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander("Lihat Tabel Histori"):
                st.dataframe(df_hist.sort_values("timestamp", ascending=False), use_container_width=True)
        else:
            st.info("Tidak ada data untuk kombinasi vendor dan berat ini.")
    else:
        st.info("Belum ada data histori. Silakan upload file source web di sidebar untuk mulai mencatat.")
