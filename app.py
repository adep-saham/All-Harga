import requests
import pandas as pd
import streamlit as st
from datetime import datetime

# ======================
# CONFIG
# ======================
VENDOR_ID_GALERI24 = "d0fd1d95-ac0a-48d8-95f8-98bd9c5f9197"

API_URL = (
    "https://galeri24.co.id/api/product-variants"
    f"?take=100&vendor_id={VENDOR_ID_GALERI24}"
)

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
def find_items(payload):
    """
    Mencari list items dari berbagai kemungkinan struktur API:
    - payload adalah list langsung
    - payload["data"] adalah list
    - payload["items"] adalah list
    - payload["data"]["items"] adalah list
    - payload["result"] / ["results"] adalah list
    """
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return None

    candidates = [
        ("data",),
        ("items",),
        ("result",),
        ("results",),
        ("data", "items"),
        ("data", "results"),
        ("payload",),
        ("payload", "items"),
    ]

    for path in candidates:
        cur = payload
        ok = True
        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                ok = False
                break
        if ok and isinstance(cur, list):
            return cur

    return None

def to_int_or_none(x):
    try:
        if x is None or x == "":
            return None
        return int(x)
    except Exception:
        return None

def parse_variants(items):
    """
    Map item ke kolom standar.
    Karena field bisa beda-beda, kita coba beberapa nama field.
    """
    records = []
    for it in items:
        if not isinstance(it, dict):
            continue

        berat = (
            it.get("weight")
            or it.get("berat")
            or it.get("variant_weight")
            or it.get("variantName")
            or it.get("variant_name")
            or it.get("name")
        )

        harga_jual = (
            it.get("sell_price")
            or it.get("price")
            or it.get("harga_jual")
            or it.get("sellPrice")
        )

        harga_buyback = (
            it.get("buyback_price")
            or it.get("buyback")
            or it.get("harga_buyback")
            or it.get("buybackPrice")
        )

        # filter ketat: harus punya berat & harga jual
        if berat is None or harga_jual is None:
            continue

        records.append({
            "tanggal": datetime.now().strftime("%Y-%m-%d"),
            "produk": "GALERI 24",
            "berat": str(berat).strip(),
            "harga_jual": to_int_or_none(harga_jual),
            "harga_buyback": to_int_or_none(harga_buyback),
        })

    return pd.DataFrame(records)

def scrape_galeri24():
    r = requests.get(API_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()

    # Kadang server balas HTML error page walau status 200.
    ctype = (r.headers.get("content-type") or "").lower()
    if "application/json" not in ctype:
        raise ValueError(f"Response bukan JSON. content-type={ctype}")

    payload = r.json()
    return payload

# ======================
# STREAMLIT UI
# ======================
st.set_page_config(page_title="Harga Emas Galeri 24", layout="wide")
st.title("📊 Harga Emas Galeri 24 (LIVE)")
st.caption("Sumber: galeri24.co.id – API product-variants (robust parser)")

with st.expander("🔧 Debug (lihat URL & sample JSON)"):
    st.code(API_URL)

try:
    payload = scrape_galeri24()

    # tampilkan sebagian payload supaya kita tahu strukturnya (penting untuk pastikan parsing)
    with st.expander("🧾 Sample Response (raw)"):
        st.json(payload if isinstance(payload, dict) else payload[:3])

    items = find_items(payload)
    if items is None:
        raise ValueError("Tidak menemukan list items di response (struktur API berbeda)")

    df = parse_variants(items)
    if df.empty:
        raise ValueError("Items ditemukan tapi tidak ada record berat/harga yang cocok (field name berbeda)")

    st.success("✅ Data harga GALERI 24 berhasil diambil")
    st.dataframe(df, use_container_width=True)

    st.subheader("🔎 Ringkasan")
    col1, col2 = st.columns(2)
    col1.metric("Jumlah Varian", len(df))

    # coba ambil 1gr jika ada
    df_norm = df.copy()
    # normalisasi "1", "1 gr", "1g"
    df_norm["berat_norm"] = df_norm["berat"].str.replace("gr", "", case=False).str.replace("g", "", case=False).str.strip()
    one = df_norm[df_norm["berat_norm"] == "1"]
    if not one.empty and one["harga_jual"].notna().any():
        harga_1g = int(one["harga_jual"].dropna().iloc[0])
        col2.metric("Harga Jual 1 gr", f"Rp {harga_1g:,}")
    else:
        col2.metric("Harga Jual 1 gr", "—")

except Exception as e:
    st.error("❌ Gagal ambil data harga")
    st.exception(e)
