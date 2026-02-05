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
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://galeri24.co.id/",
}

# ======================
# UTIL
# ======================
def to_int(text):
    if text is None:
        return None
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else None

def norm_gram(x):
    s = str(x).lower()
    s = s.replace("gram", "").replace("gr", "").replace("g", "").strip()
    token = s.split()[0] if s.split() else ""
    token = "".join(ch for ch in token if (ch.isdigit() or ch == "."))
    return token if token else None

def safe_json_loads(s):
    try:
        return json.loads(s)
    except Exception:
        return None

# ======================
# 1) HARGA JUAL (API)
# ======================
def fetch_sell_prices():
    r = requests.get(API_VARIANTS, headers=HEADERS, timeout=30)
    r.raise_for_status()
    payload = r.json()

    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("Response product-variants tidak berformat list pada key 'data'")

    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = it.get("name", "") or it.get("variant_name", "")
        weight = it.get("weight") or name
        gram = norm_gram(weight)

        sell = it.get("price") or it.get("sell_price") or it.get("sellPrice")
        sell = int(sell) if sell is not None else None
        if gram and sell:
            rows.append({"gram": gram, "berat": weight, "harga_jual": sell})

    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("Harga jual kosong dari product-variants (filter gram/sell tidak match)")
    return df

# ======================
# 2) BUYBACK (MULTI STRATEGY)
# ======================
def parse_buyback_from_table(html: str):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return None  # table tidak ada

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

    return pd.DataFrame(out) if out else None

def parse_buyback_from_next_data(html: str):
    """
    Fallback: cari JSON embedded yang memuat buyback.
    Kita scan:
    - <script id="__NEXT_DATA__" type="application/json">...</script>
    - script JSON lain yang mengandung kata buyback
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1) __NEXT_DATA__
    nd = soup.find("script", id="__NEXT_DATA__")
    if nd and nd.string:
        jd = safe_json_loads(nd.string)
        if isinstance(jd, dict):
            # cari list angka buyback + weight secara heuristik
            # flatten sederhana: cari dict yang punya key mirip weight + buyback
            buy_rows = []

            def walk(obj):
                if isinstance(obj, dict):
                    keys = set(obj.keys())
                    # banyak kemungkinan penamaan
                    weight_key = next((k for k in keys if k.lower() in ["weight", "berat"]), None)
                    bb_key = next((k for k in keys if "buyback" in k.lower()), None)
                    if weight_key and bb_key:
                        gram = norm_gram(obj.get(weight_key))
                        bb = to_int(obj.get(bb_key))
                        if gram and bb:
                            buy_rows.append({"gram": gram, "harga_buyback": bb})

                    for v in obj.values():
                        walk(v)
                elif isinstance(obj, list):
                    for v in obj:
                        walk(v)

            walk(jd)
            if buy_rows:
                # dedup by gram (ambil max/terakhir)
                m = {}
                for r in buy_rows:
                    m[r["gram"]] = r["harga_buyback"]
                return pd.DataFrame([{"gram": g, "harga_buyback": v} for g, v in m.items()])

    # 2) fallback: scan script yang mengandung "buyback"
    scripts = soup.find_all("script")
    buy_rows = []
    for sc in scripts:
        txt = sc.string or ""
        if "buyback" not in txt.lower():
            continue
        # cari pola sederhana: "buyback" angka dan "weight" angka
        # ini heuristik, cukup buat menangkap kasus umum
        # jika cocok, akan terisi; kalau tidak, return None
    return None

def fetch_buyback_prices():
    """
    Ambil halaman /harga-emas dan ekstrak buyback dengan beberapa strategi.
    """
    r = requests.get(PAGE_URL, headers=HEADERS, timeout=30, allow_redirects=True)
    r.raise_for_status()

    html = r.text
    ctype = (r.headers.get("content-type") or "").lower()

    with st.expander("🧾 Debug: response /harga-emas"):
        st.write("Status:", r.status_code)
        st.write("Content-Type:", ctype)
        st.write("Final URL:", r.url)
        st.write("HTML length:", len(html))
        st.code(html[:5000])  # potongan awal untuk lihat apakah diblok / redirect

    # Strategy A: table
    df_table = parse_buyback_from_table(html)
    if df_table is not None and not df_table.empty:
        return df_table

    # Strategy B: embedded JSON (Next.js)
    df_next = parse_buyback_from_next_data(html)
    if df_next is not None and not df_next.empty:
        return df_next

    raise ValueError("Buyback tidak ditemukan: HTML tidak ada table dan tidak ada JSON embedded yang memuat buyback.")

# ======================
# MAIN UI
# ======================
st.set_page_config(page_title="Harga Emas Galeri 24", layout="wide")
st.title("📊 Harga Emas Galeri 24 (Jual + Buyback)")
st.caption("Jual: API product-variants | Buyback: multi-strategy dari /harga-emas")

try:
    df_sell = fetch_sell_prices()
    df_buy = fetch_buyback_prices()

    df = df_sell.merge(df_buy, on="gram", how="left")
    df["tanggal"] = datetime.now().strftime("%Y-%m-%d")
    df["produk"] = "GALERI 24"
    df = df[["tanggal", "produk", "berat", "harga_jual", "harga_buyback"]]

    st.success("✅ Data berhasil diambil")
    st.dataframe(df, use_container_width=True)

    # ringkasan
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

except Exception as e:
    st.error("❌ Gagal ambil data")
    st.exception(e)
