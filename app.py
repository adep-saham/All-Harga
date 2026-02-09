import streamlit as st
import requests
import pandas as pd
from io import BytesIO
import datetime as dt
import plotly.express as px

# =========================================================
# IMPORT SCRAPERS & UTILS
# =========================================================
from scrapers.galeri24 import parse_galeri24, URL_GALERI24
from scrapers.stargold import parse_stargold, URL_STARGOLD
from scrapers.anekalogam import parse_anekalogam, URL_ANEKALOGAM
from scrapers.hrta import parse_hrta, URL_HRTA
from scrapers.indogold import parse_indogold, URL_INDOGOLD
from scrapers.hakabegold import parse_hakabegold, URL_HAKABEGOLD
from scrapers.agungjewellery import parse_agungjewellery

from utils.uploader import render_uploader_sidebar
from utils.history_manager import get_full_history, save_to_history

# =========================================================
# CONFIG & HELPERS
# =========================================================
st.set_page_config(page_title="Monitor Harga Emas", layout="wide")


def format_rp(x):
    try:
        return f"Rp{int(x):,}".replace(",", ".")
    except Exception:
        return "Rp0"


@st.cache_data(ttl=300)
def fetch_html(url: str) -> str:
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        return r.text or ""
    except Exception:
        return ""


def get_all_comparison_100g():
    """Mengumpulkan data 100g dari semua sumber + Waktu Update Web."""
    results = []
    scrapers = [
        ("StarGold", lambda: parse_stargold("")),
        ("Galeri 24", lambda: parse_galeri24(fetch_html(URL_GALERI24))),
        ("Aneka Logam", lambda: parse_anekalogam(fetch_html(URL_ANEKALOGAM))),
        ("HRTA GOLD", lambda: parse_hrta("")),
        ("IndoGold", lambda: parse_indogold(fetch_html(URL_INDOGOLD))),
        ("HK Logam Mulia", lambda: parse_hakabegold()),
        ("Agung Jewellery", lambda: parse_agungjewellery()),
    ]

    for name, func in scrapers:
        try:
            df_tmp, update_label = func()  # menangkap label waktu dari scraper
            if df_tmp is None or df_tmp.empty:
                continue

            # aturan khusus: untuk beberapa sumber, ambil ANTAM 100g
            if name in ["Galeri 24", "StarGold", "IndoGold"]:
                mask = (df_tmp["vendor"].str.contains("ANTAM", case=False, na=False)) & (df_tmp["weight_g"] == 100)
            else:
                mask = df_tmp["weight_g"] == 100

            filtered = df_tmp[mask].copy()
            if filtered.empty:
                continue

            row = filtered.sort_values("sell_idr").iloc[0]
            results.append(
                {
                    "vendor": name,
                    "weight_g": 100,
                    "sell_idr": row["sell_idr"],
                    "buyback_idr": row["buyback_idr"],
                    "source_update": update_label,
                }
            )
        except Exception:
            continue

    return pd.DataFrame(results)


# =========================================================
# EXPORT EXCEL (ALL SHEETS)
# =========================================================
ALL_SHEETS = [
    "Summary_100g",
    "StarGold",
    "Galeri24",
    "AnekaLogam",
    "HRTA",
    "IndoGold",
    "HK_Logam_Mulia",
    "Agung_Jewellery",
]


def build_excel_all_sheets() -> bytes:
    """Tarik seluruh history dari Google Sheet -> jadikan 1 file Excel multi-sheet."""
    output = BytesIO()
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        info = pd.DataFrame(
            {
                "generated_at": [now],
                "sheets": [", ".join(ALL_SHEETS)],
            }
        )
        info.to_excel(writer, sheet_name="_INFO", index=False)

        for sheet in ALL_SHEETS:
            df = get_full_history(worksheet_name=sheet)

            if df is None or df.empty:
                pd.DataFrame(
                    columns=["timestamp", "vendor", "weight_g", "sell_idr", "buyback_idr", "source_update"]
                ).to_excel(writer, sheet_name=sheet[:31], index=False)
                continue

            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
                df = df.sort_values("timestamp")

            df.to_excel(writer, sheet_name=sheet[:31], index=False)

    output.seek(0)
    return output.getvalue()


# =========================================================
# AUTO-FETCH STATE & CALLBACKS
# =========================================================
def request_fetch():
    st.session_state["need_fetch"] = True


if "need_fetch" not in st.session_state:
    st.session_state["need_fetch"] = True  # first load -> fetch
if "mode" not in st.session_state:
    st.session_state["mode"] = "📊 Perbandingan 100g (All)"
if "source_opt" not in st.session_state:
    st.session_state["source_opt"] = "StarGold"  # default saat mode detail


# =========================================================
# SIDEBAR
# =========================================================
st.sidebar.title("⚙️ Kontrol")

mode = st.sidebar.radio(
    "Mode Tampilan",
    ["📊 Perbandingan 100g (All)", "🏪 Detail Per Toko"],
    key="mode",
    on_change=request_fetch,
)

# pilihan toko hanya muncul kalau mode detail
if st.session_state.get("mode") == "🏪 Detail Per Toko":
    source_opt = st.sidebar.selectbox(
        "Pilih Toko",
        ["Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK Logam Mulia", "Agung Jewellery"],
        key="source_opt",
        on_change=request_fetch,
    )
    target_sheet = source_opt.replace(" ", "_")
else:
    # mode all
    st.session_state["source_opt"] = "All 100g"
    source_opt = "All 100g"
    target_sheet = "Summary_100g"

st.sidebar.divider()
render_uploader_sidebar()

# Export Excel All
st.sidebar.divider()
st.sidebar.subheader("⬇️ Export Database")

# 2-step: siapkan bytes saat klik, lalu download muncul (lebih stabil di Streamlit)
if st.sidebar.button("📥 Siapkan Excel (All Sheets)", use_container_width=True):
    st.session_state["excel_bytes"] = build_excel_all_sheets()

excel_bytes = st.session_state.get("excel_bytes")
if excel_bytes:
    st.sidebar.download_button(
        label="✅ Download Excel (All Sheets)",
        data=excel_bytes,
        file_name="Database_Harga_Emas_ALL.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


# =========================================================
# FETCH LOGIC (AUTO)
# =========================================================
def do_fetch_current():
    # clear cache hanya saat user ganti mode/toko
    st.cache_data.clear()

    current_mode = st.session_state.get("mode", "📊 Perbandingan 100g (All)")
    current_source = st.session_state.get("source_opt", "All 100g")

    if current_mode == "📊 Perbandingan 100g (All)":
        st.session_state["current_df"] = get_all_comparison_100g()
        return

    # DETAIL PER TOKO
    df_detail = pd.DataFrame()
    ul = ""

    if current_source == "HK Logam Mulia":
        df_detail, ul = parse_hakabegold()
        if df_detail is not None and not df_detail.empty and ("vendor" in df_detail.columns) and df_detail["vendor"].isna().all():
            df_detail["vendor"] = "HK Logam Mulia"

    elif current_source == "StarGold":
        df_detail, ul = parse_stargold("")
    elif current_source == "Agung Jewellery":
        df_detail, ul = parse_agungjewellery()
    elif current_source == "HRTA":
        df_detail, ul = parse_hrta("")
    else:
        url = {"Galeri24": URL_GALERI24, "AnekaLogam": URL_ANEKALOGAM, "IndoGold": URL_INDOGOLD}.get(current_source)
        html = fetch_html(url) if url else ""
        if current_source == "Galeri24":
            df_detail, ul = parse_galeri24(html)
        elif current_source == "AnekaLogam":
            df_detail, ul = parse_anekalogam(html)
        elif current_source == "IndoGold":
            df_detail, ul = parse_indogold(html)

    if df_detail is not None and not df_detail.empty:
        df_detail["source_update"] = ul

        # FILTER ATURAN: ANTAM HANYA 100G, LAINNYA ASLI
        if "vendor" in df_detail.columns and "weight_g" in df_detail.columns:
            is_antam = df_detail["vendor"].str.contains("ANTAM", case=False, na=False)
            df_detail = df_detail[~is_antam | (df_detail["weight_g"] == 100)].copy()

        st.session_state["current_df"] = df_detail.reset_index(drop=True)
    else:
        st.session_state["current_df"] = pd.DataFrame()


if st.session_state.get("need_fetch"):
    st.session_state["need_fetch"] = False
    do_fetch_current()


# =========================================================
# MAIN CONTENT
# =========================================================
st.title("📊 Monitoring Harga Emas")
tab1, tab2 = st.tabs(["🕒 Harga Realtime", "📈 Grafik Histori"])

with tab1:
    df_active = st.session_state.get("current_df", pd.DataFrame())

    if df_active is not None and not df_active.empty:
        if st.button(f"💾 Simpan ke Google Sheet: {target_sheet}", use_container_width=True):
            if save_to_history(df_active, worksheet_name=target_sheet):
                st.success(f"✅ Data berhasil dicatat di tab '{target_sheet}'")

        if st.session_state.get("mode") == "📊 Perbandingan 100g (All)":
            st.subheader("📋 Tabel Perbandingan Antam 100 gr")
            df_table = df_active.sort_values("sell_idr").reset_index(drop=True)
            display_data = pd.DataFrame(
                {
                    "No": range(1, len(df_table) + 1),
                    "Nama Toko Emas": df_table["vendor"],
                    "Harga Jual": df_table["sell_idr"].apply(format_rp),
                    "Harga Beli": df_table["buyback_idr"].apply(format_rp),
                    "Update di Web": df_table["source_update"],
                }
            )
            st.dataframe(display_data, use_container_width=True, hide_index=True)
        else:
            for v_name in df_active["vendor"].dropna().unique():
                st.subheader(f"🏢 {v_name}")
                sub = df_active[df_active["vendor"] == v_name].sort_values("weight_g")
                st.table(
                    pd.DataFrame(
                        {
                            "Berat": sub["weight_g"].apply(lambda x: f"{x:g} gr"),
                            "Harga Jual": sub["sell_idr"].apply(format_rp),
                            "Harga Beli": sub["buyback_idr"].apply(format_rp),
                        }
                    )
                )
    else:
        st.info("Tidak ada data untuk ditampilkan. Pilih mode/toko di sidebar — data akan otomatis ditarik.")


with tab2:
    st.subheader("📈 Grafik Histori")

    sheet_to_view = st.selectbox(
        "Pilih Sumber Data Grafik",
        ["Summary_100g", "Galeri24", "StarGold", "AnekaLogam", "HRTA", "IndoGold", "HK_Logam_Mulia", "Agung_Jewellery"],
    )

    df_hist = get_full_history(worksheet_name=sheet_to_view)

    if df_hist is not None and not df_hist.empty:
        df_hist["timestamp"] = pd.to_datetime(df_hist["timestamp"], errors="coerce")

        c1, c2 = st.columns(2)
        v_list = sorted(df_hist["vendor"].dropna().unique())
        v_plot = c1.selectbox("Pilih Vendor", v_list)

        available_weights = sorted(df_hist[df_hist["vendor"] == v_plot]["weight_g"].unique())
        w_plot = c2.selectbox("Pilih Berat (gram)", available_weights, key="w_plot")

        plot_df = df_hist[(df_hist["vendor"] == v_plot) & (df_hist["weight_g"] == w_plot)].sort_values("timestamp")

        if not plot_df.empty:
            fig = px.line(
                plot_df,
                x="timestamp",
                y="sell_idr",
                markers=True,
                title=f"Tren Harga Jual {v_plot} {w_plot}g",
                labels={"timestamp": "Tanggal & Waktu", "sell_idr": "Harga Jual (Rp)"},
            )
            fig.update_layout(yaxis_tickformat=",.0f")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(f"Tidak ada data untuk {v_plot} dengan berat {w_plot}g.")

        with st.expander("📂 Lihat Data Mentah"):
            st.dataframe(df_hist.sort_values("timestamp", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("Belum ada data histori untuk ditampilkan. Silakan simpan data terlebih dahulu.")
