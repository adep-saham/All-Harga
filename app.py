import requests
import pandas as pd
import streamlit as st
from datetime import datetime

# ======================
# CONFIG
# ======================
VENDOR_ID_GALERI24 = "d0fd1d95-ac0a-48d8-95f8-98bd9c5f9197"
API_URL = f"https://galeri24.co.id/api/product-variants?take=200&vendor_id={VENDOR_ID_GALERI24}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/144.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://galeri24.co.id/harga-emas",
}

# ======================
# HELPERS
# ======================
def to_int(x):
    try:
        if x is None:
            return None
        # kalau string "Rp1.234.000" atau "1,234,000"
        if isinstance(x, str):
            digits = "".join(ch for ch in x if ch.isdigit())
            return int(digits) if digits else None
        return int(x)
    except Exception:
        return None

def get_nested(d, path):
    cur = d
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur

def find_items(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        # banyak API pakai data/items/results
        for key in ["data", "items", "results", "result"]:
            if key in payload and isinstance(payload[key], list):
                return payload[key]
        # nested
        if "data" in payload and isinstance(payload["data"], dict):
            for key in ["items", "results"]:
                if key in payload["data"] and isinstance(payload["data"][key], list):
                    return payload["data"][key]
    return None

def is_batangan(it: dict) -> bool:
    """
    Filter agar yang diambil hanya produk batangan/logam mulia (bukan perhiasan).
    Karena struktur bisa beda, kita cek beberapa field teks.
    """
    text_fields = [
        it.get("name"),
        it.get("variant_name"),
        it.get("slug"),
        it.get("sku"),
        get_nested(it, ["product", "name"]),
        get_nested(it, ["product", "slug"]),
        get_nested(it, ["category", "name"]),
        get_nested(it, ["category", "slug"]),
    ]
    blob = " ".join([str(x).lower() for x in text_fields if x])

    keywords = ["logam", "mulia", "lm", "batangan", "gold bar", "galeri 24"]
    # kalau mengandung "hwt" / "lotus" biasanya bukan batangan harga tabel
    bad = ["hwt", "lotus", "jewelry", "perhiasan"]

    return any(k in blob for k in keywords) and not any(b in blob for b in bad)

def extract_price_fields(it: dict):
    """
    Cari harga dari berbagai kemungkinan field (top-level & nested).
    """
    # kandidat field top-level
    candidates_sell = [
        "sell_price", "sellPrice", "price", "harga_jual", "sell",
        "selling_price", "sellingPrice"
    ]
    candidates_buyback = [
        "buyback_price", "buybackPrice", "buyback", "harga_buyback"
    ]

    sell = None
    buyback = None

    for k in candidates_sell:
        if k in it and it.get(k) is not None:
            sell = it.get(k)
            break

    for k in candidates_buyback:
        if k in it and it.get(k) is not None:
            buyback = it.get(k)
            break

    # kalau masih kosong, cek nested umum
    if sell is None:
        # contoh kemungkinan: it["prices"][0]["sell"]
        nested_paths = [
            ["prices", 0, "sell"],
            ["prices", 0, "sell_price"],
            ["prices", 0, "price"],
            ["price", "sell"],
            ["pricing", "sell"],
            ["pricing", "price"],
            ["product", "price"],
            ["product", "sell_price"],
        ]
        for p in nested_paths:
            cur = it
            ok = True
            for step in p:
                if isinstance(step, int):
                    if isinstance(cur, list) and len(cur) > step:
                        cur = cur[step]
                    else:
                        ok = False
                        break
                else:
                    if isinstance(cur, dict) and step in cur:
                        cur = cur[step]
                    else:
                        ok = False
                        break
            if ok and cur is not None:
                sell = cur
                break

    if buyback is None:
        nested_paths = [
            ["prices", 0, "buyback"],
            ["prices", 0, "buyback_price"],
            ["pricing", "buyback"],
            ["price", "buyback"],
            ["product", "buyback_price"],
        ]
        for p in nested_paths:
            cur = it
            ok = True
            for step in p:
                if isinstance(step, int):
                    if isinstance(cur, list) and len(cur) > step:
                        cur = cur[step]
                    else:
                        ok = False
                        break
                else:
                    if isinstance(cur, dict) and step in cur:
                        cur = cur[step]
                    else:
                        ok = False
                        break
            if ok and cur is not None:
                buyback = cur
                break

    return to_int(sell), to_int(buyback)

# ======================
# FETCH
# ======================
def fetch_payload():
    r = requests.get(API_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()

def build_df(items):
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue

        # FILTER: hanya batangan/logam mulia
        if not is_batangan(it):
            continue

        berat = it.get("weight") or it.get("berat") or it.get("variant_name") or it.get("name")
        sell, buyback = extract_price_fields(it)

        # wajib ada harga jual
        if sell is None:
            continue

        rows.append({
            "tanggal": datetime.now().strftime("%Y-%m-%d"),
            "produk": "GALERI 24",
            "berat": str(berat).strip() if berat else None,
            "harga_jual": sell,
            "harga_buyback": buyback,
        })

    return pd.DataFrame(rows)

# ======================
# UI
# ======================
st.set_page_config(page_title="Harga Emas Galeri 24", layout="wide")
st.title("📊 Harga Emas Galeri 24 (LIVE)")
st.caption("Sumber: galeri24.co.id – API product-variants (filtered batangan)")

with st.expander("🔧 Debug URL"):
    st.code(API_URL)

try:
    payload = fetch_payload()
    items = find_items(payload)
    if items is None:
        raise ValueError("Tidak menemukan list items di response")

    # Debug: tampilkan keys item pertama agar kita tahu field harga sebenarnya
    with st.expander("🧾 Debug: keys item pertama"):
        if len(items) > 0 and isinstance(items[0], dict):
            st.write(sorted(list(items[0].keys())))
            st.json(items[0])
        else:
            st.write("Item pertama bukan dict / kosong")

    df = build_df(items)

    if df.empty:
        st.warning("Data berhasil diambil, tapi belum ada item batangan dengan harga terdeteksi.")
        st.info("Cek expander debug keys/JSON di atas untuk lihat field harga yang sebenarnya.")
    else:
        st.success("✅ Data harga batangan GALERI 24 berhasil diambil")
        st.dataframe(df, use_container_width=True)

        st.subheader("🔎 Ringkasan")
        col1, col2 = st.columns(2)
        col1.metric("Jumlah Varian Batangan", len(df))

        # coba ambil 1 gr
        df_norm = df.copy()
        df_norm["berat_norm"] = (
            df_norm["berat"].astype(str)
            .str.replace("gr", "", case=False)
            .str.replace("g", "", case=False)
            .str.strip()
        )
        one = df_norm[df_norm["berat_norm"] == "1"]
        col2.metric("Harga Jual 1 gr", f"Rp {int(one['harga_jual'].iloc[0]):,}" if not one.empty else "—")

except Exception as e:
    st.error("❌ Gagal ambil / parse data harga")
    st.exception(e)
