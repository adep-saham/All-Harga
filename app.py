import streamlit as st
import requests
import pandas as pd
from io import BytesIO

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

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="All Harga Emas",
    layout="wide"
)

# =========================================================
# HELPERS
# =========================================================
def format_rp(x) -> str:
    try:
        return f"Rp{int(x):,}".replace(",", ".")
    except:
        return "Rp0"

@st.cache_data(ttl=300)
def fetch_html(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        return r.text
    except:
        return ""

# =========================================================
# UI
# =========================================================
st.title("📊 Monitoring Harga Emas")

source = st.sidebar.radio(
    "Sumber Data",
    [
        "Galeri24",
        "StarGold",
        "AnekaLogam",
        "HRTA",
        "IndoGold",
        "HK Logam Mulia",
        "Agung Jewellery"
    ],
    index=6
)

URLS = {
    "Galeri24": URL_GALERI24,
    "StarGold": URL_STARGOLD,
    "AnekaLogam": URL_ANEKALOGAM,
    "HRTA": URL_HRTA,
    "IndoGold": URL_INDOGOLD,
    "HK Logam Mulia": URL_HAKABEGOLD,
    "Agung Jewellery": "https://agungjewellery.com/harga-lm-2/",
}

current_url = URLS.get(source, "")
st.caption(f"Target: {current_url}")

# =========================================================
# ACTION
# =========================================================
if st.button("🚀 Ambil Data"):
    try:
        with st.spinner(f"Mengambil data {source}..."):
            df = pd.DataFrame()
            update_label = ""

            # ===== GOOGLE SHEETS BASED =====
            if source == "HK Logam Mulia":
                df, update_label = parse_hakabegold()

            # ===== AGUNG JEWELLERY =====
            elif source == "Agung Jewellery":
                df, update_label = parse_agungjewellery()

            # ===== HRTA =====
            elif source == "HRTA":
                df, update_label = parse_hrta("")

            # ===== HTML BASED SCRAPERS =====
            else:
                html = fetch_html(current_url)
                if not html:
                    st.warning("HTML kosong / gagal diambil.")
                else:
                    if source == "Galeri24":
                        df, update_label = parse_galeri24(html)
                    elif source == "StarGold":
                        df, update_label = parse_stargold(html)
                    elif source == "AnekaLogam":
                        df, update_label = parse_anekalogam(html)
                    elif source == "IndoGold":
                        df, update_label = parse_indogold(html)

        # =====================================================
        # DISPLAY RESULT
        # =====================================================
        if df is not None and not df.empty:
            st.subheader(update_label)
            st.success(f"Sukses! {len(df)} data ditemukan.")

            for vendor in df["vendor"].unique():
                st.markdown(f"### {vendor}")
                sub = df[df["vendor"] == vendor].copy()

                if "weight_g" in sub.columns:
                    sub = sub.sort_values("weight_g")

                display = pd.DataFrame({
                    "Berat": sub["weight_g"].apply(lambda x: f"{x:g} gr"),
                    "Harga Jual": sub["sell_idr"].apply(format_rp),
                    "Harga Buyback": sub["buyback_idr"].apply(format_rp),
                    "Stok": sub.get("stock", "Ready")
                })

                st.table(display)

            # =================================================
            # DOWNLOAD
            # =================================================
            st.divider()
            c1, c2 = st.columns(2)

            with c1:
                st.download_button(
                    "📥 Download CSV",
                    df.to_csv(index=False).encode("utf-8-sig"),
                    f"{source}.csv",
                    "text/csv",
                    use_container_width=True
                )

            with c2:
                out = BytesIO()
                with pd.ExcelWriter(out, engine="openpyxl") as w:
                    df.to_excel(w, index=False, sheet_name="Data")
                st.download_button(
                    "📥 Download Excel",
                    out.getvalue(),
                    f"{source}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

        else:
            st.warning(f"Data kosong atau gagal diambil: {update_label}")

    except Exception as e:
        st.error(f"Terjadi kesalahan fatal: {e}")
