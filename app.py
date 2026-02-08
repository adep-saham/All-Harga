import streamlit as st
import requests
import pandas as pd
import re
from io import BytesIO

# =========================================================
# 1. IMPORT SCRAPERS
# =========================================================
from scrapers.galeri24 import parse_galeri24, URL_GALERI24
from scrapers.stargold import parse_stargold, URL_STARGOLD
from scrapers.anekalogam import parse_anekalogam, URL_ANEKALOGAM
from scrapers.hrta import parse_hrta, URL_HRTA
from scrapers.indogold import parse_indogold, URL_INDOGOLD
from scrapers.hakabegold import parse_hakabegold, URL_HAKABEGOLD

# =========================================================
# 2. HELPERS
# =========================================================
def format_rp(x: int) -> str:
    try:
        if x == 0: return "Rp0"
        return f"Rp{int(x):,}".replace(",", ".")
    except: return "Rp0"

def safe_sheet_name(name: str, used: set) -> str:
    cleaned = re.sub(r"[:\\/?*\[\]]", " ", str(name))
    cleaned = re.sub(r"\s+", " ", cleaned).strip() or "Sheet"
    base = cleaned[:31]
    candidate = base
    idx = 2
    while candidate in used:
        suffix = f"_{idx}"
        candidate = (base[:31 - len(suffix)] + suffix)[:31]
        idx += 1
    used.add(candidate)
    return candidate

@st.cache_data(ttl=180)
def fetch_html(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text

# =========================================================
# 3. UI APLIKASI
# =========================================================
st.set_page_config(page_title="All Harga Emas", layout="wide")
st.title("📊 Monitoring Harga Emas")

source = st.sidebar.radio(
    "Sumber Data",
    ["Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK Logam Mulia"],
    index=5
)

URLS = {
    "Galeri24": URL_GALERI24,
    "StarGold": URL_STARGOLD,
    "AnekaLogam": URL_ANEKALOGAM,
    "HRTA": URL_HRTA,
    "IndoGold": URL_INDOGOLD,
    "HK Logam Mulia": URL_HAKABEGOLD,
}
st.caption(f"Target: {URLS[source]}")

if st.button("🚀 Ambil Data"):
    try:
        url = URLS[source]
        with st.spinner(f"Mengambil data {source}..."):
            # Logika Pemilihan Scraper
            if source == "HK Logam Mulia":
                df, update_label = parse_hakabegold("")
            elif source == "HRTA":
                df, update_label = parse_hrta("")
            else:
                html = fetch_html(url)
                if source == "Galeri24": df, update_label = parse_galeri24(html)
                elif source == "StarGold": df, update_label = parse_stargold(html)
                elif source == "AnekaLogam": df, update_label = parse_anekalogam(html)
                elif source == "IndoGold": df, update_label = parse_indogold(html)

        # Tampilkan Hasil
        if df is not None and not df.empty and "vendor" in df.columns:
            st.subheader(update_label)
            st.success(f"Sukses! {len(df)} data ditemukan.")

            vendors = df["vendor"].unique().tolist()
            selected = st.sidebar.multiselect("Filter", vendors, default=vendors)

            for v in selected:
                st.markdown(f"**{v}**")
                sub = df[df["vendor"] == v].copy()
                if "weight_g" in sub.columns: sub = sub.sort_values("weight_g")

                # Format Tabel Tampilan
                display = pd.DataFrame()
                display["Berat"] = sub["weight_g"].apply(lambda x: f"{x:g} gr")
                display["Harga Jual"] = sub["sell_idr"].apply(format_rp)
                display["Harga Buyback"] = sub["buyback_idr"].apply(format_rp)
                if "stock" in sub.columns: display["Stok"] = sub["stock"]
                
                st.table(display)
            
            # Download Area
            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                st.download_button("📥 CSV", df.to_csv(index=False).encode("utf-8-sig"), f"{source}.csv", "text/csv", use_container_width=True)
            with c2:
                out = BytesIO()
                with pd.ExcelWriter(out, engine="openpyxl") as w:
                    df.to_excel(w, index=False, sheet_name="Data")
                st.download_button("📥 Excel", out.getvalue(), f"{source}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        else:
            st.warning(f"Data kosong: {update_label}")

    except Exception as e:
        st.error(f"Terjadi kesalahan: {e}")
