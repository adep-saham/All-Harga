import streamlit as st
import requests
import pandas as pd
import re
from datetime import datetime
from bs4 import BeautifulSoup

URL = "https://galeri24.co.id/harga-emas"

# ===== UI CONFIG =====
st.set_page_config(page_title="Harga Emas Galeri24", layout="wide")
st.title("Harga Emas Galeri24")
st.caption(URL)

# ===== HELPERS =====
def rupiah_to_int(s: str) -> int:
    """Convert 'Rp1.546.000' -> 1546000"""
    if s is None:
        return 0
    s = str(s).strip()
    s = s.replace("Rp", "").replace(" ", "").replace(".", "").replace(",", "")
    return int(s) if s.isdigit() else 0

def format_rp(x: int) -> str:
    try:
        return f"Rp{int(x):,}".replace(",", ".")
    except Exception:
        return "Rp0"

def parse_update_label(text: str) -> str:
    """
    Try to extract 'Diperbarui Selasa, 3 Februari 2026'
    If not found, fallback to today.
    """
    # Capture entire "Diperbarui ...." line if exists
    m = re.search(r"(Diperbarui\s+[A-Za-z]+\s*,\s*\d{1,2}\s+[A-Za-z]+\s+\d{4})", text)
    if m:
        return m.group(1).strip()
    return f"Diperbarui {datetime.now().strftime('%Y-%m-%d')}"

def parse_update_date(text: str) -> str:
    """
    Extract Indonesian date like '3 Februari 2026' -> '2026-02-03'
    """
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
    if not m:
        return datetime.now().strftime("%Y-%m-%d")

    day = int(m.group(1))
    mon_name = m.group(2).lower()
    year = int(m.group(3))
    months = {
        "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
        "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12
    }
    month = months.get(mon_name)
    if not month:
        return datetime.now().strftime("%Y-%m-%d")
    return f"{year:04d}-{month:02d}-{day:02d}"

def normalize_vendor(v: str):
    if not v:
        return None
    v = v.strip()
    # remove accidental tokens
    blacklist = {"BUYBACK", "HARGA", "BERAT", "HARGA BUYBACK", "HARGA JUAL"}
    if v.strip().upper() in blacklist:
        return None
    # keep original capitalization style like website (mostly uppercase in sidebar)
    return v.strip().upper()

# Urutan berat yang umum dipakai di tabel Galeri24
WEIGHT_ORDER = [0.5, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000]
WEIGHT_RANK = {w: i for i, w in enumerate(WEIGHT_ORDER)}

def weight_sort_key(w: float):
    # weights in WEIGHT_ORDER come first in exact order, others after sorted ascending
    if w in WEIGHT_RANK:
        return (0, WEIGHT_RANK[w])
    return (1, w)

def is_weight_token(x: str) -> bool:
    x = x.replace(",", ".").strip()
    return bool(re.fullmatch(r"\d+(\.\d+)?", x))

def is_rp_token(x: str) -> bool:
    return "Rp" in x

# ===== FETCH & SCRAPE =====
@st.cache_data(ttl=300)
def fetch_html() -> str:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,*/*",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    r = requests.get(URL, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text

def scrape_prices(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    update_date = parse_update_date(text)

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    rows = []
    vendor = None
    i = 0

    while i < len(lines):
        ln = lines[i]

        # Vendor section begins
        if ln.startswith("Harga "):
            vendor_raw = ln.replace("Harga ", "").strip()
            vendor = normalize_vendor(vendor_raw)
            i += 1
            continue

        # Skip header tokens
        if ln.lower() in {"berat", "harga jual", "harga buyback"}:
            i += 1
            continue

        # Parse triplet: weight, Rp sell, Rp buyback
        if vendor and is_weight_token(ln):
            w = float(ln.replace(",", "."))
            j = i + 1
            rp_vals = []
            while j < len(lines) and len(rp_vals) < 2:
                # stop if next vendor encountered
                if lines[j].startswith("Harga "):
                    break
                if is_rp_token(lines[j]):
                    rp_vals.append(lines[j])
                j += 1

            if len(rp_vals) == 2:
                sell = rupiah_to_int(rp_vals[0])
                buyback = rupiah_to_int(rp_vals[1])
                # guard: sometimes parser catches unrelated Rp; ensure not zero-ish too often
                rows.append({
                    "date": update_date,
                    "vendor": vendor,
                    "weight_g": w,
                    "sell_idr": sell,
                    "buyback_idr": buyback,
                    "source": URL
                })
                i = j
                continue

        i += 1

    if not rows:
        raise RuntimeError("Tidak menemukan data harga. HTML yang didapat kemungkinan bukan konten harga.")

    df = pd.DataFrame(rows).drop_duplicates(
        subset=["date", "vendor", "weight_g", "sell_idr", "buyback_idr"]
    )

    # clean vendor None
    df = df[df["vendor"].notna()]

    # sort per vendor + weight order
    df["__wkey0"] = df["weight_g"].apply(lambda x: weight_sort_key(float(x))[0])
    df["__wkey1"] = df["weight_g"].apply(lambda x: weight_sort_key(float(x))[1])
    df = df.sort_values(["vendor", "__wkey0", "__wkey1"]).drop(columns=["__wkey0", "__wkey1"])

    return df

# ===== UI =====
col_left, col_right = st.columns([1, 1])

with col_left:
    run = st.button("Ambil data sekarang")

with col_right:
    st.write("")

if run:
    try:
        html = fetch_html()

        # Debug kecil (boleh kamu hide nanti)
        st.caption(f"Panjang HTML: {len(html)} | Ada kata 'Harga ANTAM'?: {'Harga ANTAM' in html}")

        df = scrape_prices(html)

        # Update label mirip website
        update_label = parse_update_label(BeautifulSoup(html, "html.parser").get_text("\n", strip=True))
        st.subheader(update_label)

        vendors = sorted(df["vendor"].unique().tolist())

        st.sidebar.header("Vendor Emas")
        selected = st.sidebar.multiselect("Pilih Vendor", options=vendors, default=vendors)

        st.success(f"Berhasil: {len(df)} baris")

        # Render per vendor seperti website
        for v in selected:
            st.markdown(f"## Harga {v}")

            sub = df[df["vendor"] == v].copy()
            # ensure weight order exact
            sub["__wkey0"] = sub["weight_g"].apply(lambda x: weight_sort_key(float(x))[0])
            sub["__wkey1"] = sub["weight_g"].apply(lambda x: weight_sort_key(float(x))[1])
            sub = sub.sort_values(["__wkey0", "__wkey1"]).drop(columns=["__wkey0", "__wkey1"])

            display_df = pd.DataFrame({
                "Berat": sub["weight_g"].apply(lambda x: int(x) if float(x).is_integer() else x),
                "Harga Jual": sub["sell_idr"].apply(format_rp),
                "Harga Buyback": sub["buyback_idr"].apply(format_rp),
            })

            st.table(display_df)

        # Download CSV
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Download CSV (raw long)", csv, "galeri24_harga_emas_long.csv", "text/csv")

    except Exception as e:
        st.error("Gagal ambil data")
        st.exception(e)
else:
    st.info("Klik **Ambil data sekarang** untuk menampilkan tabel harga per vendor seperti di Galeri24.")
