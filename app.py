import requests
import pandas as pd
import streamlit as st
from datetime import datetime

# ======================
# CONFIG
# ======================
VENDOR_ID_GALERI24 = "d0fd1d95-ac0a-48d8-95f8-98bd9c5f9197"
API_VARIANTS = f"https://galeri24.co.id/api/product-variants?take=300&vendor_id={VENDOR_ID_GALERI24}"

# daily update biasanya berisi harga emas harian (jual/buyback)
API_DAILY = "https://galeri24.co.id/api/daily-update"

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
        if isinstance(x, str):
            digits = "".join(ch for ch in x if ch.isdigit())
            return int(digits) if digits else None
        return int(x)
    except Exception:
        return None

def find_list(payload):
    """
    Cari list items dari berbagai kemungkinan struktur:
    - list langsung
    - {"data":[...]}
    - {"items":[...]}
    - {"data":{"items":[...]}}
    - {"result":[...]} / {"results":[...]}
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ["data", "items", "result", "results"]:
            if k in payload and isinstance(payload[k], list):
                return payload[k]
        if "data" in payload and isinstance(payload["data"], dict):
            for k in ["items", "result", "results"]:
                if k in payload["data"] and isinstance(payload["data"][k], list):
                    return payload["data"][k]
    return None

def normalize_gram(text):
    """
    "1 Gram - Black Gold Series" -> "1"
    "0.5 Gram ..." -> "0.5"
    "10 gr" -> "10"
    """
    if text is None:
        return None
    s = str(text).lower()
    s = s.replace("gram", "").replace("gr", "").replace("g", "").strip()
    # ambil token pertama yang angka/desimal
    token = s.split()[0] if s.split() else ""
    # hanya keep digit dan titik
    token = "".join(ch for ch in token if (ch.isdigit() or ch == "."))
    return token if token else None

def is_batangan(it: dict) -> bool:
    """
    Filter supaya ambil logam mulia/batangan, bukan perhiasan.
    """
    blob_parts = [
        it.get("name"),
        it.get("variant_name"),
        it.get("slug"),
        it.get("sku"),
        (it.get("category") or {}).get("name") if isinstance(it.get("category"), dict) else None,
        (it.get("product") or {}).get("name") if isinstance(it.get("product"), dict) else None,
    ]
    blob = " ".join([str(x).lower() for x in blob_parts if x])

    good = ["logam", "mulia", "batangan", "gold", "bar", "galeri 24"]
    bad = ["hwt", "lotus", "perhiasan", "jewelry"]

    return any(g in blob for g in good) and not any(b in blob for b in bad)

def extract_sell_price(it: dict):
    """
    Harga jual umumnya ada di variants.
    """
    for k in ["sell_price", "sellPrice", "price", "harga_jual", "selling_price", "sellingPrice"]:
        if k in it and it.get(k) is not None:
            return to_int(it.get(k))
    # fallback nested
    for path in [
        ["pricing", "sell"],
        ["pricing", "price"],
        ["price", "sell"],
        ["price", "value"],
    ]:
        cur = it
        ok = True
        for p in path:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                ok = False
                break
        if ok:
            v = to_int(cur)
            if v is not None:
                return v
    return None

# ======================
# FETCHERS
# ======================
def fetch_json(url: str):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()

def fetch_variants():
    payload = fetch_json(API_VARIANTS)
    items = find_list(payload)
    if items is None:
        raise ValueError("Tidak menemukan list items pada product-variants")
    return items, payload

def fetch_buyback_map():
    """
    Build mapping gram -> buyback_price (dan opsional sell_price kalau ada)
    return:
      buyback_map: {"1": 2794000, ...}
      sell_map: {"1": 2984000, ...}  (kalau daily-update menyediakan)
      raw_payload: payload untuk debug
    """
    payload = fetch_json(API_DAILY)
    items = find_list(payload)
    if items is None:
        # beberapa API menaruh list pada key lain
        # tetap simpan payload untuk debug
        return {}, {}, payload

    buyback_map = {}
    sell_map = {}

    for it in items:
        if not isinstance(it, dict):
            continue

        # cari gram
        gram = (
            normalize_gram(it.get("weight"))
            or normalize_gram(it.get("berat"))
            or normalize_gram(it.get("name"))
        )
        if not gram:
            continue

        # cari buyback
        bb = None
        for k in ["buyback_price", "buybackPrice", "buyback", "harga_buyback"]:
            if k in it and it.get(k) is not None:
                bb = to_int(it.get(k))
                break

        # cari sell (kadang daily-update juga punya harga jual)
        sp = None
        for k in ["sell_price", "sellPrice", "price", "harga_jual"]:
            if k in it and it.get(k) is not None:
                sp = to_int(it.get(k))
                break

        if bb is not None:
            buyback_map[gram] = bb
        if sp is not None:
            sell_map[gram] = sp

    return buyback_map, sell_map, payload

# ======================
# BUILD FINAL DF
# ======================
def build_final_df(variants_items, buyback_map):
    rows = []
    for it in variants_items:
        if not isinstance(it, dict):
            continue

        if not is_batangan(it):
            continue

        name = it.get("name") or it.get("variant_name") or ""
        gram = normalize_gram(it.get("weight") or name)

        sell = extract_sell_price(it)
        if sell is None:
            continue

        rows.append({
            "tanggal": datetime.now().strftime("%Y-%m-%d"),
            "produk": "GALERI 24",
            "berat": it.get("weight") or name,
            "gram_norm": gram,
            "harga_jual": sell,
            "harga_buyback": buyback_map.get(gram) if gram else None
        })

    df = pd.DataFrame(rows)

    # rapikan: gram_norm tidak perlu tampil
    if not df.empty:
        df = df.drop(columns=["gram_norm"])
        # optional sort by gram numeric jika bisa
        def gram_to_float(x):
            try:
                return float(normalize_gram(x))
            except Exception:
                return 999999.0
        df["__sort"] = df["berat"].apply(gram_to_float)
        df = df.sort_values("__sort").drop(columns=["__sort"]).reset_index(drop=True)

    return df

# ======================
# STREAMLIT UI
# ======================
st.set_page_config(page_title="Harga Emas Galeri 24", layout="wide")
st.title("📊 Harga Emas Galeri 24 (LIVE)")
st.caption("Sumber: galeri24.co.id – Jual dari product-variants + Buyback dari daily-update")

with st.expander("🔧 Debug URL"):
    st.code(API_VARIANTS)
    st.code(API_DAILY)

try:
    variants_items, variants_raw = fetch_variants()
    buyback_map, sell_map_daily, daily_raw = fetch_buyback_map()

    # Debug raw payload (penting kalau buyback masih None)
    with st.expander("🧾 Debug: Sample daily-update (raw)"):
        st.json(daily_raw)

    df = build_final_df(variants_items, buyback_map)

    if df.empty:
        st.error("Data batangan tidak ditemukan / harga jual tidak terbaca.")
    else:
        st.success("✅ Data harga GALERI 24 berhasil diambil")
        st.dataframe(df, use_container_width=True)

        st.subheader("🔎 Ringkasan")
        col1, col2, col3 = st.columns(3)
        col1.metric("Jumlah Varian", len(df))

        # 1 gr
        df_tmp = df.copy()
        df_tmp["gram"] = df_tmp["berat"].apply(normalize_gram)
        one = df_tmp[df_tmp["gram"] == "1"]
        if not one.empty:
            col2.metric("Harga Jual 1 gr", f"Rp {int(one['harga_jual'].iloc[0]):,}")
            bb = one["harga_buyback"].iloc[0]
            col3.metric("Buyback 1 gr", f"Rp {int(bb):,}" if pd.notna(bb) else "—")
        else:
            col2.metric("Harga Jual 1 gr", "—")
            col3.metric("Buyback 1 gr", "—")

        # warning kalau buyback banyak None
        null_bb = df["harga_buyback"].isna().mean()
        if null_bb > 0.5:
            st.warning(
                "Buyback masih banyak kosong. Itu berarti daily-update tidak mengandung mapping buyback per gram "
                "atau field buyback memakai nama lain. Buka expander 'Sample daily-update (raw)' dan cari field buyback."
            )

except Exception as e:
    st.error("❌ Gagal ambil / parse data harga")
    st.exception(e)
