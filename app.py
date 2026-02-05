import streamlit as st
import requests
import pandas as pd
import re
from datetime import datetime
from bs4 import BeautifulSoup

URL = "https://galeri24.co.id/harga-emas"

# =========================
# UI CONFIG
# =========================
st.set_page_config(page_title="Harga Emas Galeri24", layout="wide")
st.title("Harga Emas Galeri24")
st.caption(URL)

# =========================
# HELPERS
# =========================
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
    Try to extract line like: 'Diperbarui Selasa, 3 Februari 2026'
    """
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
    blacklist = {"BUYBACK", "HARGA", "BERAT", "HARGA BUYBACK", "HARGA JUAL"}
    if v.upper() in blacklist:
        return None
    return v.upper()

# Urutan berat yang tampil umum di Galeri24
WEIGHT_ORDER = [0.5, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000]
WEIGHT_RANK = {w: i for i, w in enumerate(WEIGHT_ORDER)}

def weight_sort_key(w: float):
    if w in WEIGHT_RANK:
        return (0, WEIGHT_RANK[w])
    return (1, w)

# =========================
# FETCH
# =========================
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

# =========================
# SCRAPER (TOLERANT)
# =========================
def scrape_prices(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    update_date = parse_update_date(text)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    def is_weight_token(x: str) -> bool:
        x = x.replace(",", ".").strip()
        return bool(re.fullmatch(r"\d+(\.\d+)?", x))

    def parse_weight(x: str):
        try:
            return float(x.replace(",", "."))
        except Exception:
            return None

    def is_rp_token(x: str) -> bool:
        return "Rp" in x

    rows = []
    vendor = None
    i = 0
    LOOKAHEAD = 12  # tolerant scan window after weight

    while i < len(lines):
        ln = lines[i]

        # Vendor section begins
        if ln.startswith("Harga "):
            vendor_raw = ln.replace("Harga ", "").strip()
            vendor = normalize_vendor(vendor_raw)
            i += 1
            continue

        # Skip common header labels
        if ln.lower() in {"berat", "harga jual", "harga buyback"}:
            i += 1
            continue

        if vendor and is_weight_token(ln):
            w = parse_weight(ln)
            if w is None:
                i += 1
                continue

            # VALIDASI: buang noise seperti 0.001
            if not (0.5 <= w <= 1000):
                i += 1
                continue

            rp_vals = []
            for j in range(i + 1, min(len(lines), i + 1 + LOOKAHEAD)):
                if lines[j].startswith("Harga "):
                    break
                if is_rp_token(lines[j]):
                    rp_vals.append(lines[j])
                    if len(rp_vals) == 2:
                        break

            if len(rp_vals) == 2:
                sell = rupiah_to_int(rp_vals[0])
                buyback = rupiah_to_int(rp_vals[1])

                rows.append({
                    "date": update_date,
                    "vendor": vendor,
                    "weight_g": w,
                    "sell_idr": sell,
                    "buyback_idr": buyback,
                    "source": URL
                })
                i += 1
                continue

        i += 1

    if not rows:
        preview = "\n".join(lines[:80])
        raise RuntimeError(
            "Tidak menemukan data harga walaupun HTML terunduh.\n"
            "Preview awal:\n" + preview
        )

    df = pd.DataFrame(rows).drop_duplicates(
        subset=["date", "vendor", "weight_g", "sell_idr", "buyback_idr"]
    )
    df = df[df["vendor"].notna()]

    # sort by vendor then weight in exact order
    df["__wkey0"] = df["weight_g"].apply(lambda x: weight_sort_key(float(x))[0])
    df["__wkey1"] = df["weight_g"].apply(lambda x: weight_sort_key(float(x))[1])
    df = df.sort_values(["vendor", "__wkey0", "__wkey1"]).drop(columns=["__wkey0", "__wkey1"])

    return df

# =========================
# UI
# =========================
run = st.button("Ambil data sekarang")

if run:
    try:
        html = fetch_html()
        soup = BeautifulSoup(html, "html.parser")
        page_text = soup.get_text("\n", strip=True)

        # debug kecil
        st.caption(f"Panjang HTML: {len(html)} | Ada 'Harga ANTAM'?: {'Harga ANTAM' in html}")

        df = scrape_prices(html)

        # Judul update mirip website
        st.subheader(parse_update_label(page_text))

        vendors = sorted(df["vendor"].unique().tolist())
        st.sidebar.header("Vendor Emas")
        selected = st.sidebar.multiselect("Pilih Vendor", options=vendors, default=vendors)

        st.success(f"Berhasil: {len(df)} baris")

        # Render per vendor seperti website (judul + tabel)
        for v in selected:
            st.markdown(f"## Harga {v}")

            sub = df[df["vendor"] == v].copy()
            sub["__wkey0"] = sub["weight_g"].apply(lambda x: weight_sort_key(float(x))[0])
            sub["__wkey1"] = sub["weight_g"].apply(lambda x: weight_sort_key(float(x))[1])
            sub = sub.sort_values(["__wkey0", "__wkey1"]).drop(columns=["__wkey0", "__wkey1"])

            display_df = pd.DataFrame({
                "Berat": sub["weight_g"].apply(lambda x: int(x) if float(x).is_integer() else x),
                "Harga Jual": sub["sell_idr"].apply(format_rp),
                "Harga Buyback": sub["buyback_idr"].apply(format_rp),
            })

            st.table(display_df)

        # Download raw data (long format)
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Download CSV (raw long)", csv, "galeri24_harga_emas_long.csv", "text/csv")

    except Exception as e:
        st.error("Gagal ambil data")
        st.exception(e)
else:
    st.info("Klik **Ambil data sekarang** untuk menampilkan tabel harga per vendor seperti di Galeri24.")
