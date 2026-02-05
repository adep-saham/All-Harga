import streamlit as st
import requests
import pandas as pd
import re
from datetime import datetime
from bs4 import BeautifulSoup

URL = "https://galeri24.co.id/harga-emas"

st.set_page_config(page_title="All Harga Emas", layout="wide")
st.title("Scraper Harga Emas Galeri24")
st.caption(URL)

def rupiah_to_int(s: str) -> int:
    if s is None:
        return 0
    s = str(s).strip()
    s = s.replace("Rp", "").replace(" ", "").replace(".", "").replace(",", "")
    return int(s) if s.isdigit() else 0

def parse_update_date(text: str) -> str:
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

@st.cache_data(ttl=300)
def fetch_html() -> str:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,*/*",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    }
    r = requests.get(URL, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text

def scrape_prices(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    update_date = parse_update_date(text)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    def is_weight(x: str) -> bool:
        x = x.replace(",", ".")
        return bool(re.fullmatch(r"\d+(\.\d+)?", x))

    def is_rp(x: str) -> bool:
        return "Rp" in x

    rows = []
    vendor = None
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("Harga "):
            vendor = ln.replace("Harga ", "").strip()
            i += 1
            continue

        if vendor and is_weight(ln):
            w = float(ln.replace(",", "."))
            j = i + 1
            rp_vals = []
            while j < len(lines) and len(rp_vals) < 2:
                if lines[j].startswith("Harga "):
                    break
                if is_rp(lines[j]):
                    rp_vals.append(lines[j])
                j += 1

            if len(rp_vals) == 2:
                rows.append({
                    "date": update_date,
                    "vendor": vendor,
                    "weight_g": w,
                    "sell_idr": rupiah_to_int(rp_vals[0]),
                    "buyback_idr": rupiah_to_int(rp_vals[1]),
                    "source": URL
                })
                i = j
                continue

        i += 1

    if not rows:
        raise RuntimeError("Parser tidak menemukan data. HTML yang didapat kemungkinan bukan konten harga.")

    return pd.DataFrame(rows).drop_duplicates().sort_values(["vendor", "weight_g"])

col1, col2 = st.columns([1, 1])

with col1:
    if st.button("Ambil data sekarang"):
        try:
            html = fetch_html()
            st.write("Panjang HTML:", len(html))
            st.write("Ada kata 'Harga ANTAM' di HTML?:", "Harga ANTAM" in html)

            df = scrape_prices(html)
            st.success(f"Berhasil: {len(df)} baris")
            st.dataframe(df, use_container_width=True)

            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("Download CSV", csv, "galeri24_harga_emas.csv", "text/csv")
        except Exception as e:
            st.error("Gagal ambil data")
            st.exception(e)

with col2:
    st.subheader("Debug cepat")
    st.write("Kalau halaman blank, biasanya app crash sebelum render atau tidak ada st.*")
    st.write("Cek Streamlit Cloud → Manage app → Logs untuk error detail.")
