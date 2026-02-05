import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from datetime import datetime
import re
import json

# ======================
# CONFIG
# ======================
VENDOR_ID_GALERI24 = "d0fd1d95-ac0a-48d8-95f8-98bd9c5f9197"
API_VARIANTS = f"https://galeri24.co.id/api/product-variants?take=200&vendor_id={VENDOR_ID_GALERI24}"
PAGE_URL = "https://galeri24.co.id/harga-emas"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/144.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://galeri24.co.id/harga-emas",
}

# ======================
# UTIL
# ======================
def to_int(x):
    try:
        if x is None:
            return None
        if isinstance(x, str):
            digits = re.sub(r"[^\d]", "", x)
            return int(digits) if digits else None
        return int(x)
    except Exception:
        return None

def norm_gram(x):
    s = str(x).lower()
    s = s.replace("gram", "").replace("gr", "").replace("g", "").strip()
    token = s.split()[0] if s.split() else ""
    token = "".join(ch for ch in token if (ch.isdigit() or ch == "."))
    return token if token else None

def find_items(payload):
    """
    Cari list item dari berbagai kemungkinan struktur response.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        # langsung list
        for k in ["data", "items", "results", "result"]:
            v = payload.get(k)
            if isinstance(v, list):
                return v
        # nested
        d = payload.get("data")
        if isinstance(d, dict):
            for k in ["items", "results", "result"]:
                v = d.get(k)
                if isinstance(v, list):
                    return v
    return None

# ======================
# FETCH JSON / HTML
# ======================
def http_get(url: str):
    r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
    return r

# ======================
# SELL PRICES (PRODUCT VARIANTS) + DEBUG
# ======================
def fetch_sell_prices_with_debug():
    r = http_get(API_VARIANTS)

    with st.expander("🧾 Debug: response product-variants"):
        st.write("URL:", API_VARIANTS)
        st.write("Status:", r.status_code)
        st.write("Final URL:", r.url)
        st.write("Content-Type:", (r.headers.get("content-type") or ""))
        st.write("Text length:", len(r.text))
        st.code(r.text[:4000])

    r.raise_for_status()

    # pastikan json
    try:
        payload = r.json()
    except Exception:
        raise ValueError("product-variants tidak mengembalikan JSON (cek debug text di atas)")

    items = find_items(payload)
    if not isinstance(items, list):
        raise ValueError("Tidak menemukan list items dari response product-variants (cek debug JSON)")

    # tampilkan sample json item
    with st.expander("🧾 Debug: sample JSON product-variants"):
        if isinstance(payload, dict):
            st.json(payload)
        else:
            st.json(payload[:3])

    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue

        # ambil label berat
        weight = it.get("weight") or it.get("name") or it.get("variant_name")
        gram = norm_gram(weight)

        # harga jual: coba beberapa key
        sell = (
            it.get("price")
            or it.get("sell_price")
            or it.get("sellPrice")
            or it.get("selling_price")
            or it.get("sellingPrice")
        )
        sell = to_int(sell)

        if gram and sell:
            rows.append({"gram": gram, "berat": weight, "harga_jual": sell})

    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("Items ditemukan tapi harga_jual kosong (cek sample JSON untuk key harga)")

    return df

# ======================
# BUYBACK FROM /HARGA-EMAS (HTML) + DEBUG
# ======================
def fetch_buyback_from_page():
    r = http_get(PAGE_URL)

    with st.expander("🧾 Debug: response /harga-emas"):
        st.write("URL:", PAGE_URL)
        st.write("Status:", r.status_code)
        st.write("Final URL:", r.url)
        st.write("Content-Type:", (r.headers.get("content-type") or ""))
        st.write("HTML length:", len(r.text))
        st.code(r.text[:5000])

    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table")

    if not table:
        # tidak langsung gagal; return df kosong agar app tetap tampil debug
        return pd.DataFrame(columns=["gram", "harga_buyback"])

    rows = table.find_all("tr")[1:]
    out = []
    for tr in rows:
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) < 3:
            continue
        gram = norm_gram(tds[0])
        buyback = to_int(tds[2])
        if gram and buyback:
            out.append({"gram": gram, "harga_buyback": buyback})

    return pd.DataFrame(out)

# ======================
# UI
# ======================
st.set_page_config(page_title="Harga Emas Galeri 24", layout="wide")
st.title("📊 Harga Emas Galeri 24 (Jual + Buyback)")
st.caption("Debug selalu muncul: product-variants & /harga-emas")

try:
    df_sell = fetch_sell_prices_with_debug()
    df_buy = fetch_buyback_from_page()

    df = df_sell.merge(df_buy, on="gram", how="left")
    df["tanggal"] = datetime.now().strftime("%Y-%m-%d")
    df["produk"] = "GALERI 24"
    df = df[["tanggal", "produk", "berat", "harga_jual", "harga_buyback"]]

    st.success("✅ Data berhasil diambil (jual terisi; buyback tergantung halaman)")
    st.dataframe(df, use_container_width=True)

    # ringkasan 1g
    col1, col2, col3 = st.columns(3)
    col1.metric("Jumlah Varian", len(df))

    df_tmp = df.copy()
    df_tmp["gram"] = df_tmp["berat"].apply(norm_gram)
    one = df_tmp[df_tmp["gram"] == "1"]
    if not one.empty:
        col2.metric("Harga Jual 1 gr", f"Rp {int(one.iloc[0]['harga_jual']):,}")
        bb = one.iloc[0]["harga_buyback"]
        col3.metric("Buyback 1 gr", f"Rp {int(bb):,}" if pd.notna(bb) else "—")
    else:
        col2.metric("Harga Jual 1 gr", "—")
        col3.metric("Buyback 1 gr", "—")

    if df["harga_buyback"].isna().all():
        st.warning("Buyback masih kosong karena halaman /harga-emas yang diterima server tidak berisi tabel. Lihat Debug /harga-emas untuk penyebabnya.")

except Exception as e:
    st.error("❌ Gagal ambil data")
    st.exception(e)
