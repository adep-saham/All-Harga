# app.py
import streamlit as st
import requests
import pandas as pd
import re
from io import BytesIO

from scrapers.galeri24 import parse_galeri24, URL_GALERI24
from scrapers.stargold import parse_stargold, URL_STARGOLD
from scrapers.anekalogam import parse_anekalogam, URL_ANEKALOGAM
from scrapers.hrta import parse_hrta, URL_HRTA
from scrapers.indogold import parse_indogold, URL_INDOGOLD


# =========================
# Helpers UI / Formatting
# =========================
def format_rp(x: int) -> str:
    try:
        return f"Rp{int(x):,}".replace(",", ".")
    except Exception:
        return "Rp0"


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
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/144.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


# =========================
# App
# =========================
st.set_page_config(page_title="All Harga Emas", layout="wide")
st.title("All Harga Emas")

# Source selector
source = st.sidebar.radio(
    "Sumber",
    ["Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold"],
    index=0,
)

URLS = {
    "Galeri24": URL_GALERI24,
    "StarGold": URL_STARGOLD,
    "AnekaLogam": URL_ANEKALOGAM,
    "HRTA": URL_HRTA,
    "IndoGold": URL_INDOGOLD,
}

st.caption(URLS[source])
st.write("")

# =========================
# Main Action
# =========================
if st.button("Ambil data sekarang"):
    try:
        # =====================
        # PARSE PER SOURCE
        # =====================
        if source == "IndoGold":
            # IMPORTANT:
            # IndoGold TIDAK pakai HTML
            # langsung hit API JSON
            df, update_label = parse_indogold()

        else:
            url = URLS[source]
            html = fetch_html(url)

            if source == "Galeri24":
                df, update_label = parse_galeri24(html)
            elif source == "StarGold":
                df, update_label = parse_stargold(html)
            elif source == "AnekaLogam":
                df, update_label = parse_anekalogam(html)
            else:  # HRTA
                df, update_label = parse_hrta("")

        st.subheader(update_label)
        st.success(f"Berhasil: {len(df)} baris")

        # =====================
        # GUARD: DF WAJIB VALID
        # =====================
        if df.empty or "vendor" not in df.columns:
            st.warning("Data kosong atau struktur berubah.")
            st.stop()

        # =====================
        # Vendor Filter
        # =====================
        vendors = sorted(df["vendor"].unique().tolist())
        selected = st.sidebar.multiselect(
            "Pilih Vendor", vendors, default=vendors
        )

        # =====================
        # Render Tables
        # =====================
        for v in selected:
            st.markdown(f"## Harga {v}")
            sub = df[df["vendor"] == v].copy()

            if "weight_g" in sub.columns:
                sub = sub.sort_values("weight_g")

            display = pd.DataFrame({
                "Berat": sub["weight_g"].apply(
                    lambda x: int(x) if float(x).is_integer() else x
                ),
                "Harga Jual": sub["sell_idr"].apply(format_rp),
                "Harga Buyback": sub["buyback_idr"].apply(format_rp),
            })

            st.table(display)

        # =====================
        # DOWNLOAD CSV
        # =====================
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Download CSV (long)",
            data=csv,
            file_name=f"{source.lower()}_harga_emas_long.csv",
            mime="text/csv",
        )

        # =====================
        # DOWNLOAD EXCEL
        # =====================
        output = BytesIO()
        used = set()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="long")
            used.add("long")

            for v in vendors:
                sub = df[df["vendor"] == v].copy()
                if "weight_g" in sub.columns:
                    sub = sub.sort_values("weight_g")

                sub_out = pd.DataFrame({
                    "Berat": sub["weight_g"].apply(
                        lambda x: int(x) if float(x).is_integer() else x
                    ),
                    "Harga Jual": sub["sell_idr"].apply(format_rp),
                    "Harga Buyback": sub["buyback_idr"].apply(format_rp),
                })

                sub_out.to_excel(
                    writer,
                    index=False,
                    sheet_name=safe_sheet_name(v, used),
                )

        st.download_button(
            "Download Excel (.xlsx)",
            data=output.getvalue(),
            file_name=f"{source.lower()}_harga_emas.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

    except Exception as e:
        st.error("Gagal ambil data")
        st.exception(e)

else:
    st.info("Pilih sumber di sidebar lalu klik **Ambil data sekarang**.")
