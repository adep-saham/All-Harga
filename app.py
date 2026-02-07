import streamlit as st
import requests
import pandas as pd
import re
from io import BytesIO

from scrapers.galeri24 import parse_galeri24, URL_GALERI24
from scrapers.stargold import parse_stargold, URL_STARGOLD
from scrapers.anekalogam import parse_anekalogam, URL_ANEKALOGAM


# =========================
# Helpers UI/Download
# =========================
def format_rp(x: int) -> str:
    try:
        return f"Rp{int(x):,}".replace(",", ".")
    except Exception:
        return "Rp0"

def safe_sheet_name(name: str, used: set) -> str:
    # Excel forbidden: : \ / ? * [ ]
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
        "User-Agent": "Mozilla/5.0",
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
source = st.sidebar.radio("Sumber", ["Galeri24", "StarGold", "AnekaLogam"], index=0)

# URL mapping (FIX: ini yang bikin caption selalu benar)
URLS = {
    "Galeri24": URL_GALERI24,
    "StarGold": URL_STARGOLD,
    "AnekaLogam": URL_ANEKALOGAM,
}
st.caption(URLS[source])

st.write("")  # spacer

if st.button("Ambil data sekarang"):
    try:
        url = URLS[source]
        html = fetch_html(url)

        # parse sesuai source
        if source == "Galeri24":
            df, update_label = parse_galeri24(html)
        elif source == "StarGold":
            df, update_label = parse_stargold(html)
        else:
            df, update_label = parse_anekalogam(html)

        st.subheader(update_label)
        st.success(f"Berhasil: {len(df)} baris")

        # vendor list
        vendors = df["vendor"].unique().tolist()
        selected = st.sidebar.multiselect("Pilih Vendor", vendors, default=vendors)

        # render per vendor
        for v in selected:
            st.markdown(f"## Harga {v}")
            sub = df[df["vendor"] == v].copy()

            # urutkan berat numeric
            if "weight_g" in sub.columns:
                sub = sub.sort_values("weight_g")

            display = pd.DataFrame({
                "Berat": sub["weight_g"].apply(lambda x: int(x) if float(x).is_integer() else x),
                "Harga Jual": sub["sell_idr"].apply(format_rp),
                "Harga Buyback": sub["buyback_idr"].apply(format_rp),
            })
            st.table(display)

        # =========================
        # DOWNLOAD CSV (LONG)
        # =========================
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Download CSV (long)",
            data=csv,
            file_name=f"{source.lower()}_harga_emas_long.csv",
            mime="text/csv",
        )

        # =========================
        # DOWNLOAD EXCEL
        # =========================
        output = BytesIO()
        used = set()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            # sheet raw
            df.to_excel(writer, index=False, sheet_name="long")
            used.add("long")

            # per vendor sheet
            for v in vendors:
                sub = df[df["vendor"] == v].copy()
                if "weight_g" in sub.columns:
                    sub = sub.sort_values("weight_g")

                sub_out = pd.DataFrame({
                    "Berat": sub["weight_g"].apply(lambda x: int(x) if float(x).is_integer() else x),
                    "Harga Jual": sub["sell_idr"].apply(format_rp),
                    "Harga Buyback": sub["buyback_idr"].apply(format_rp),
                })

                sub_out.to_excel(writer, index=False, sheet_name=safe_sheet_name(v, used))

        st.download_button(
            "Download Excel (.xlsx)",
            data=output.getvalue(),
            file_name=f"{source.lower()}_harga_emas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except Exception as e:
        st.error("Gagal ambil data")
        st.exception(e)
else:
    st.info("Pilih sumber di sidebar lalu klik **Ambil data sekarang**.")
