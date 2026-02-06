import streamlit as st
import requests
import pandas as pd
import re
from datetime import datetime
from bs4 import BeautifulSoup

URL = "https://galeri24.co.id/harga-emas"

# =========================
# UI
# =========================
st.set_page_config(page_title="Harga Emas Galeri24", layout="wide")
st.title("Harga Emas Galeri24")
st.write(URL)

# =========================
# Helpers
# =========================
def rupiah_to_int(s: str) -> int:
    # input examples: "Rp1.560.000", "Rp 1.560.000"
    s = s.replace("Rp", "").replace(" ", "").strip()
    s = s.replace(".", "").replace(",", "")
    return int(s) if s.isdigit() else 0

def format_rp(x: int) -> str:
    try:
        return f"Rp{int(x):,}".replace(",", ".")
    except Exception:
        return "Rp0"

def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def parse_update_label(text: str) -> str:
    # capture full "Diperbarui ...."
    m = re.search(r"(Diperbarui\s+[A-Za-z]+,\s*\d{1,2}\s+[A-Za-z]+\s+\d{4})", text)
    if m:
        return m.group(1)
    return f"Diperbarui {datetime.now().strftime('%Y-%m-%d')}"

# Urutan berat persis seperti tabel umum Galeri24
WEIGHT_ORDER = [0.5, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000]
WEIGHT_RANK = {w: i for i, w in enumerate(WEIGHT_ORDER)}

def weight_sort_key(w: float):
    if w in WEIGHT_RANK:
        return (0, WEIGHT_RANK[w])
    return (1, w)

# =========================
# Fetch
# =========================
@st.cache_data(ttl=180)
def fetch_html() -> str:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    r = requests.get(URL, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text

# =========================
# Parser (dynamic blocks)
# =========================
def scrape_prices(html: str) -> tuple[pd.DataFrame, str]:
    soup = BeautifulSoup(html, "html.parser")
    raw_text = soup.get_text(" ", strip=True)
    text = normalize_spaces(raw_text)

    update_label = parse_update_label(text)

    # 1) Ambil semua blok vendor secara dinamis dengan anchor yang stabil:
    #    "Harga <vendor> Berat Harga Jual Harga Buyback <isi...> (sampai vendor berikutnya / Diperbarui / end)"
    block_pattern = re.compile(
        r"Harga\s+(?P<vendor>.+?)\s+Berat\s+Harga\s+Jual\s+Harga\s+Buyback\s+(?P<body>.+?)"
        r"(?=(?:\s+Harga\s+.+?\s+Berat\s+Harga\s+Jual\s+Harga\s+Buyback)|(?:\s+Diperbarui)|\Z)",
        re.IGNORECASE,
    )

    blocks = list(block_pattern.finditer(text))
    if not blocks:
        # Debug minimal biar kamu bisa lihat teksnya kalau berubah lagi
        preview = text[:800]
        raise RuntimeError("Tidak menemukan blok vendor. Preview: " + preview)

    rows = []

    # 2) Di dalam masing-masing body, cari pasangan: weight + Rp + Rp (berulang)
    #    contoh: "0.5 Rp1.560.000 Rp1.394.000"
    pair_pattern = re.compile(
        r"(?P<w>\d+(?:\.\d+)?)\s+Rp\s*(?P<sell>[\d\.\,]+)\s+Rp\s*(?P<buy>[\d\.\,]+)",
        re.IGNORECASE,
    )

    for b in blocks:
        vendor = normalize_spaces(b.group("vendor")).upper()
        body = b.group("body")

        pairs = list(pair_pattern.finditer(body))
        if not pairs:
            continue

        for p in pairs:
            w = float(p.group("w"))
            # Filter noise (buang 0.001 dll)
            if not (0.5 <= w <= 1000):
                continue

            sell = rupiah_to_int("Rp" + p.group("sell"))
            buyb = rupiah_to_int("Rp" + p.group("buy"))

            rows.append({
                "vendor": vendor,
                "weight_g": w,
                "sell_idr": sell,
                "buyback_idr": buyb,
                "source": URL
            })

    if not rows:
        raise RuntimeError("Parser gagal: tidak menemukan pasangan berat + harga dari blok yang terdeteksi.")

    df = pd.DataFrame(rows).drop_duplicates(subset=["vendor", "weight_g", "sell_idr", "buyback_idr"])

    # Sort: vendor (sesuai kemunculan di halaman, bukan alfabet) + urutan berat persis
    # Bikin map order vendor berdasarkan urutan blocks
    vendor_order = []
    for b in blocks:
        v = normalize_spaces(b.group("vendor")).upper()
        if v not in vendor_order:
            vendor_order.append(v)
    vendor_rank = {v: i for i, v in enumerate(vendor_order)}

    df["__vr"] = df["vendor"].map(lambda x: vendor_rank.get(x, 9999))
    df["__w0"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[0])
    df["__w1"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[1])

    df = df.sort_values(["__vr", "vendor", "__w0", "__w1"]).drop(columns=["__vr", "__w0", "__w1"])

    return df, update_label

# =========================
# UI action
# =========================
if st.button("Ambil data sekarang"):
    try:
        html = fetch_html()

        st.caption(f"Panjang HTML: {len(html)} | Ada kata 'Harga ANTAM'?: {'Harga ANTAM' in html}")

        df, update_label = scrape_prices(html)

        st.subheader(update_label)

        vendors = df["vendor"].unique().tolist()
        st.sidebar.header("Vendor Emas")
        selected = st.sidebar.multiselect("Pilih Vendor", vendors, default=vendors)

        st.success(f"Berhasil: {len(df)} baris")

        for v in selected:
            st.markdown(f"## Harga {v}")
            sub = df[df["vendor"] == v].copy()

            # ensure weight order exact
            sub["__w0"] = sub["weight_g"].map(lambda x: weight_sort_key(float(x))[0])
            sub["__w1"] = sub["weight_g"].map(lambda x: weight_sort_key(float(x))[1])
            sub = sub.sort_values(["__w0", "__w1"]).drop(columns=["__w0", "__w1"])

            display = pd.DataFrame({
                "Berat": sub["weight_g"].apply(lambda x: int(x) if float(x).is_integer() else x),
                "Harga Jual": sub["sell_idr"].apply(format_rp),
                "Harga Buyback": sub["buyback_idr"].apply(format_rp),
            })
            st.table(display)

        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Download CSV (long)", csv, "galeri24_harga_emas_long.csv", "text/csv")

     # --- EXCEL ---
        from io import BytesIO
        output = BytesIO()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            # Sheet 1: data mentah (long)
            df.to_excel(writer, index=False, sheet_name="long")

            # Sheet 2+: per vendor
            for v in df["vendor"].unique():
                sub = df[df["vendor"] == v].copy()
                sub = sub.sort_values("weight_g")

                sub_out = pd.DataFrame({
                    "Berat": sub["weight_g"],
                    "Harga Jual": sub["sell_idr"],
                    "Harga Buyback": sub["buyback_idr"],
                })

                sheet_name = v[:31]  # limit Excel
                sub_out.to_excel(writer, index=False, sheet_name=sheet_name)

        st.download_button(
            "Download Excel (.xlsx)",
            data=output.getvalue(),
            file_name="galeri24_harga_emas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    
    except Exception as e:
        st.error("Gagal ambil data")
        st.exception(e)
else:
    st.info("Klik **Ambil data sekarang** untuk menampilkan tabel harga per vendor seperti di Galeri24.")
