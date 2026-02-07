import re
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup

URL_HRTA = "https://hrtagold.id/en/gold-price"

WEIGHT_ORDER = [0.1, 0.25, 0.5, 1, 2, 3, 5, 10, 25, 50, 100, 250, 500, 1000]
WEIGHT_RANK = {w: i for i, w in enumerate(WEIGHT_ORDER)}

def weight_sort_key(w: float):
    if w in WEIGHT_RANK:
        return (0, WEIGHT_RANK[w])
    return (1, w)

def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()

def money_to_int(s: str) -> int:
    """
    Tolerant parser:
    - remove currency words/symbols
    - keep digits only
    """
    s = str(s)
    # common currency tokens
    s = s.replace("IDR", "").replace("Rp", "").replace("rp", "")
    s = s.replace(",", "").replace(".", "").replace(" ", "").strip()
    s = re.sub(r"[^\d]", "", s)
    return int(s) if s.isdigit() else 0

def parse_update_label(text: str) -> str:
    # HRTA page may not have a clear "last update"; we use snapshot time.
    return f"Snapshot {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

def _try_parse_tables(soup: BeautifulSoup):
    """
    Try to parse from HTML tables by detecting headers:
    weight/gram + sell + buy/buyback
    """
    tables = soup.find_all("table")
    if not tables:
        return None

    def norm(h):  # normalize header string
        return normalize_spaces(h).lower()

    for t in tables:
        # get headers
        ths = t.find_all("th")
        if not ths:
            # sometimes header is in first row td
            first_tr = t.find("tr")
            if first_tr:
                ths = first_tr.find_all(["th", "td"])
        headers = [norm(th.get_text(" ", strip=True)) for th in ths]
        if not headers:
            continue

        # detect columns
        # weight column
        w_idx = None
        for i, h in enumerate(headers):
            if "weight" in h or "gram" in h or "g)" in h or "g " in h:
                w_idx = i
                break

        # sell column
        sell_idx = None
        for i, h in enumerate(headers):
            if "sell" in h or "selling" in h or "price" in h:
                sell_idx = i
                break

        # buy/buyback column
        buy_idx = None
        for i, h in enumerate(headers):
            if "buyback" in h or "buy back" in h or "buy" in h:
                buy_idx = i
                break

        if w_idx is None or sell_idx is None:
            continue  # not our price table

        # rows
        rows = []
        trs = t.find_all("tr")
        for tr in trs[1:]:
            tds = tr.find_all(["td", "th"])
            if not tds:
                continue
            cells = [normalize_spaces(td.get_text(" ", strip=True)) for td in tds]

            if w_idx >= len(cells) or sell_idx >= len(cells):
                continue

            w_txt = cells[w_idx]
            # weight examples: "1 g", "1gr", "1 gram"
            m = re.search(r"(\d+(?:\.\d+)?)", w_txt.replace(",", "."))
            if not m:
                continue
            w = float(m.group(1))
            if not (0.1 <= w <= 1000):
                continue

            sell = money_to_int(cells[sell_idx])
            buyb = money_to_int(cells[buy_idx]) if (buy_idx is not None and buy_idx < len(cells)) else 0

            rows.append((w, sell, buyb))

        if rows:
            return rows

    return None

def parse_hrta(html: str) -> tuple[pd.DataFrame, str]:
    soup = BeautifulSoup(html, "html.parser")
    text = normalize_spaces(soup.get_text(" ", strip=True))
    update_label = parse_update_label(text)

    rows = []

    # 1) table-first
    table_rows = _try_parse_tables(soup)
    if table_rows:
        for w, sell, buyb in table_rows:
            rows.append({
                "snapshot_ts": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "update_label": update_label,
                "source_site": "hrta",
                "vendor": "HRTA",
                "weight_g": float(w),
                "sell_idr": int(sell),
                "buyback_idr": int(buyb),
                "source_url": URL_HRTA,
            })

    # 2) fallback regex (if no table)
    if not rows:
        # capture patterns like: "1 g ... Rp 1.234.000 ... Rp 1.100.000"
        # tolerate IDR, Rp, separators
        pair = re.compile(
            r"(\d+(?:\.\d+)?)\s*(?:g|gr|gram)\s+.*?(?:Rp|IDR)\s*([\d\.,]+)\s+.*?(?:Rp|IDR)\s*([\d\.,]+)",
            re.IGNORECASE,
        )
        for w_raw, sell_raw, buy_raw in pair.findall(text):
            w = float(w_raw.replace(",", "."))
            if not (0.1 <= w <= 1000):
                continue
            rows.append({
                "snapshot_ts": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "update_label": update_label,
                "source_site": "hrta",
                "vendor": "HRTA",
                "weight_g": w,
                "sell_idr": money_to_int("Rp" + sell_raw),
                "buyback_idr": money_to_int("Rp" + buy_raw),
                "source_url": URL_HRTA,
            })

    if not rows:
        raise RuntimeError("HRTA: tidak menemukan tabel/pola harga. Struktur halaman mungkin berubah.")

    df = pd.DataFrame(rows).drop_duplicates(subset=["update_label", "weight_g", "sell_idr", "buyback_idr"])

    df["__w0"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[0])
    df["__w1"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[1])
    df = df.sort_values(["__w0", "__w1"]).drop(columns=["__w0", "__w1"])

    return df, update_label
