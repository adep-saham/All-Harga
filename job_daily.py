import os
import re
from datetime import datetime
import requests
import pandas as pd
from bs4 import BeautifulSoup

import gspread
from google.oauth2.service_account import Credentials


URL = "https://galeri24.co.id/harga-emas"

WEIGHT_ORDER = [0.5, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000]
WEIGHT_RANK = {w: i for i, w in enumerate(WEIGHT_ORDER)}

def weight_sort_key(w: float):
    if w in WEIGHT_RANK:
        return (0, WEIGHT_RANK[w])
    return (1, w)

def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()

def parse_update_label(text: str) -> str:
    m = re.search(r"(Diperbarui\s+[A-Za-z]+,\s*\d{1,2}\s+[A-Za-z]+\s+\d{4})", text)
    if m:
        return m.group(1)
    return f"Diperbarui {datetime.now().strftime('%Y-%m-%d')}"

def rupiah_to_int(s: str) -> int:
    s = str(s).replace("Rp", "").replace(" ", "").strip()
    s = s.replace(".", "").replace(",", "")
    return int(s) if s.isdigit() else 0

def fetch_html() -> str:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    r = requests.get(URL, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text

def scrape_prices(html: str) -> tuple[pd.DataFrame, str]:
    soup = BeautifulSoup(html, "html.parser")
    raw_text = soup.get_text(" ", strip=True)
    text = normalize_spaces(raw_text)
    update_label = parse_update_label(text)

    block_pattern = re.compile(
        r"Harga\s+(?P<vendor>.+?)\s+Berat\s+Harga\s+Jual\s+Harga\s+Buyback\s+(?P<body>.+?)"
        r"(?=(?:\s+Harga\s+.+?\s+Berat\s+Harga\s+Jual\s+Harga\s+Buyback)|(?:\s+Diperbarui)|\Z)",
        re.IGNORECASE,
    )

    blocks = list(block_pattern.finditer(text))
    if not blocks:
        raise RuntimeError("Tidak menemukan blok vendor.")

    pair_pattern = re.compile(
        r"(?P<w>\d+(?:\.\d+)?)\s+Rp\s*(?P<sell>[\d\.\,]+)\s+Rp\s*(?P<buy>[\d\.\,]+)",
        re.IGNORECASE,
    )

    rows = []
    vendor_order = []
    for b in blocks:
        vendor = normalize_spaces(b.group("vendor")).upper()
        if vendor not in vendor_order:
            vendor_order.append(vendor)

        body = b.group("body")
        for p in pair_pattern.finditer(body):
            w = float(p.group("w"))
            if not (0.5 <= w <= 1000):
                continue
            rows.append({
                "snapshot_ts": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "update_label": update_label,
                "vendor": vendor,
                "weight_g": w,
                "sell_idr": rupiah_to_int("Rp" + p.group("sell")),
                "buyback_idr": rupiah_to_int("Rp" + p.group("buy")),
                "source": URL
            })

    if not rows:
        raise RuntimeError("Tidak menemukan pasangan berat+harga.")

    df = pd.DataFrame(rows).drop_duplicates(subset=["update_label", "vendor", "weight_g", "sell_idr", "buyback_idr"])

    # sort vendor by appearance, weight by fixed order
    vendor_rank = {v: i for i, v in enumerate(vendor_order)}
    df["__vr"] = df["vendor"].map(lambda x: vendor_rank.get(x, 9999))
    df["__w0"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[0])
    df["__w1"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[1])
    df = df.sort_values(["__vr", "vendor", "__w0", "__w1"]).drop(columns=["__vr", "__w0", "__w1"])

    return df, update_label

def push_to_gsheet_append(df: pd.DataFrame, sheet_id: str, worksheet_name: str):
    # Service account JSON is provided via env var (file path) OR via JSON string
    sa_json_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    sa_json_raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_RAW", "").strip()

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    if sa_json_raw:
        import json
        creds = Credentials.from_service_account_info(json.loads(sa_json_raw), scopes=scopes)
    else:
        if not sa_json_path:
            raise RuntimeError("Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_JSON_RAW")
        creds = Credentials.from_service_account_file(sa_json_path, scopes=scopes)

    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)

    try:
        ws = sh.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet_name, rows=5000, cols=20)
        ws.append_row(df.columns.tolist())

    # Append rows (tidak overwrite)
    ws.append_rows(df.astype(str).values.tolist(), value_input_option="RAW")

def main():
    sheet_id = os.environ["GSHEET_ID"]
    worksheet = os.environ.get("GSHEET_TAB", "galeri24_harga_long")

    html = fetch_html()
    df, update_label = scrape_prices(html)

    push_to_gsheet_append(df, sheet_id, worksheet)
    print(f"OK: {len(df)} rows appended. {update_label}")

if __name__ == "__main__":
    main()
