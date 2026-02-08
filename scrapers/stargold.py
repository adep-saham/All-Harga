from datetime import datetime
import pandas as pd

# === SOURCE RESMI (Google Sheets publish CSV) ===
STARGOLD_SHEET_CSV = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSVUOrPaB273nGNBr_7h4ZDKWKd3HvEtmQuN4NXK1MDibiDxmB3J4aH1uE2bhn0IpJju1BgeoBJsfad"
    "/pub?gid=2127782410&single=true&output=csv"
)

SOURCE_SITE = "stargold"
SOURCE_URL = "https://stargold.id/price/"

WEIGHT_ORDER = [0.1, 0.25, 0.5, 1, 2, 3, 4, 5, 10, 25, 50, 100, 250, 500, 1000]
WEIGHT_RANK = {w: i for i, w in enumerate(WEIGHT_ORDER)}


def weight_sort_key(w: float):
    if w in WEIGHT_RANK:
        return (0, WEIGHT_RANK[w])
    return (1, w)


def parse_stargold() -> tuple[pd.DataFrame, str]:
    """
    Load StarGold ALL VENDOR data from Google Sheets CSV
    Return:
      - DataFrame standar MI
      - update_label
    """

    df = pd.read_csv(STARGOLD_SHEET_CSV)

    if df.empty:
        raise RuntimeError("StarGold CSV kosong atau tidak bisa dibaca.")

    # === NORMALISASI ===
    df["vendor"] = df["vendor"].astype(str).str.upper().str.strip()
    df["weight_g"] = pd.to_numeric(df["weight_g"], errors="coerce")
    df["sell_idr"] = pd.to_numeric(df["sell_idr"], errors="coerce").fillna(0).astype(int)
    df["buyback_idr"] = pd.to_numeric(df["buyback_idr"], errors="coerce").fillna(0).astype(int)

    df = df[df["weight_g"].notna()]
    df = df[df["weight_g"] > 0]

    snapshot_ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    update_label = f"Google Sheets Update: {snapshot_ts}"

    # === STANDAR KOLOM MI ===
    df["snapshot_ts"] = snapshot_ts
    df["update_label"] = update_label
    df["source_site"] = SOURCE_SITE
    df["source_url"] = SOURCE_URL

    # === SORT RAPI ===
    df["__w0"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[0])
    df["__w1"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[1])

    df = (
        df.sort_values(["vendor", "__w0", "__w1"])
          .drop(columns=["__w0", "__w1"])
          .reset_index(drop=True)
    )

    return df, update_label
