import re
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import pandas as pd
from bs4 import BeautifulSoup

URL_GALERI24 = "https://galeri24.co.id/harga-emas"

# Urutan berat (gram) untuk sorting yang rapi
WEIGHT_ORDER = [0.1, 0.25, 0.5, 1, 2, 3, 5, 10, 25, 50, 100, 250, 500, 1000]
WEIGHT_RANK = {w: i for i, w in enumerate(WEIGHT_ORDER)}


def weight_sort_key(w: float):
    if w in WEIGHT_RANK:
        return (0, WEIGHT_RANK[w])
    return (1, w)


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


def rupiah_to_int(s: str) -> int:
    """Konversi string rupiah seperti 'Rp290.277.000' -> 290277000."""
    s = str(s).replace("Rp", "").replace(" ", "").strip()
    s = s.replace(".", "").replace(",", "")
    return int(s) if s.isdigit() else 0


def parse_update_label(text: str) -> str:
    """Ambil label update dari halaman (contoh: 'Diperbarui Kamis, 12 Februari 2026')."""
    # Halaman Galeri24 biasanya berbahasa Indonesia, tapi kita buat cukup fleksibel.
    m = re.search(
        r"(Diperbarui\s+[A-Za-zÀ-ÿ]+,\s*\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        # Normalisasi kapitalisasi awal saja biar konsisten
        return normalize_spaces(m.group(1))
    # Fallback: tetap ada label agar dedup jalan
    return f"Diperbarui {datetime.now().strftime('%Y-%m-%d')}"


def normalize_vendor(raw_vendor: str) -> str:
    """Normalisasi vendor agar tidak 'ANTAM' dan 'GALERI 24' tercampur variasi penulisan."""
    v = normalize_spaces(raw_vendor).upper()
    # Banyak variasi: GALERI24 / GALERI 24 / GALERI-24
    if "ANTAM" in v:
        return "ANTAM"
    if "GALERI" in v:
        return "GALERI 24"
    return v


def parse_galeri24(html: str) -> tuple[pd.DataFrame, str]:
    soup = BeautifulSoup(html, "html.parser")

    full_text = normalize_spaces(soup.get_text(" ", strip=True))
    update_label = parse_update_label(full_text)
    snapshot_ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    def get_text(tag) -> str:
        return normalize_spaces(tag.get_text(" ", strip=True)) if tag else ""

    def extract_vendor_from_heading(s: str) -> str:
        # "Harga GALERI 24" -> "GALERI 24"
        s = normalize_spaces(s)
        if s.upper().startswith("HARGA "):
            s = s[6:].strip()
        return normalize_spaces(s).upper()

    def parse_rows_from_table(table, vendor: str) -> list[dict]:
        out = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            cell_texts = [get_text(c) for c in cells]
            joined = " ".join(cell_texts).lower()
            if "berat" in joined and "harga" in joined:
                continue

            # berat: first numeric non-Rp
            w = None
            for t in cell_texts:
                if "rp" in t.lower():
                    continue
                m = re.search(r"(\d+(?:\.\d+)?)", t)
                if m:
                    try:
                        w = float(m.group(1))
                        break
                    except:
                        pass
            if w is None:
                continue

            # harga: 2 cells containing Rp
            price_cells = [t for t in cell_texts if "rp" in t.lower()]
            if len(price_cells) < 2:
                continue

            sell = rupiah_to_int(price_cells[0])
            buy = rupiah_to_int(price_cells[1])
            if sell == 0 and buy == 0:
                continue

            out.append({
                "snapshot_ts": snapshot_ts,
                "update_label": update_label,
                "source_site": "galeri24",
                "vendor": vendor,
                "weight_g": w,
                "sell_idr": sell,
                "buyback_idr": buy,
                "source_url": URL_GALERI24,
            })
        return out

    rows = []

    # =========================================================
    # A) JALUR 1: DOM TABLE (kalau ada)
    # =========================================================
    tables = soup.find_all("table")
    if tables:
        # ambil table yang header-nya benar, vendor dari heading terdekat sebelumnya
        def is_price_table(table) -> bool:
            header_text = " ".join(get_text(x) for x in table.find_all(["th", "td"], limit=20)).lower()
            return ("berat" in header_text) and ("harga jual" in header_text) and ("harga buyback" in header_text)

        def find_vendor_for_table(table) -> str:
            for prev in table.find_all_previous(True, limit=80):
                t = get_text(prev)
                if not t:
                    continue
                tu = t.upper()
                if tu.startswith("HARGA ") and 5 <= len(t) <= 40:
                    return extract_vendor_from_heading(t)
            return "UNKNOWN"

        for table in tables:
            if not is_price_table(table):
                continue
            vendor = find_vendor_for_table(table)
            rows.extend(parse_rows_from_table(table, vendor))

    # =========================================================
    # B) JALUR 2: FALLBACK TEXT (kalau tidak ada table / rows kosong)
    #    Ini yang akan jalan di Streamlit Cloud saat HTML JS-only.
    # =========================================================
    if not rows:
        # pakai token per baris agar urutan "Harga VENDOR" -> data masih kebaca
        lines = [normalize_spaces(x) for x in soup.get_text("\n", strip=True).split("\n")]
        lines = [x for x in lines if x]

        # cari index heading "Harga ..."
        heading_idx = []
        for i, ln in enumerate(lines):
            up = ln.upper()
            if up.startswith("HARGA ") and 5 <= len(ln) <= 40:
                heading_idx.append(i)

        # kalau heading tidak ketemu, fallback terakhir: cari dari full_text (minim)
        if not heading_idx:
            # tidak bisa segment vendor -> lempar error dengan pesan jelas
            raise RuntimeError("Galeri24: HTML tidak mengandung <table> dan heading 'Harga <vendor>' tidak ditemukan. Kemungkinan diblok/redirect.")

        heading_idx.append(len(lines))  # sentinel

        # regex row: berat + Rp jual + Rp buyback
        # contoh text bisa: "0.5 Rp1.567.000 Rp1.401.000"
        row_re = re.compile(
            r"(?P<w>\d+(?:\.\d+)?)\s*(?:gr|g)?\s*"
            r"(?P<sell>Rp[\d\.\,]+)\s*"
            r"(?P<buy>Rp[\d\.\,]+)",
            flags=re.IGNORECASE
        )

        for a, b in zip(heading_idx[:-1], heading_idx[1:]):
            vendor = extract_vendor_from_heading(lines[a])
            chunk = " ".join(lines[a:b])

            for m in row_re.finditer(chunk):
                try:
                    w = float(m.group("w"))
                except:
                    continue

                sell = rupiah_to_int(m.group("sell"))
                buy = rupiah_to_int(m.group("buy"))
                if sell == 0 and buy == 0:
                    continue

                rows.append({
                    "snapshot_ts": snapshot_ts,
                    "update_label": update_label,
                    "source_site": "galeri24",
                    "vendor": vendor,
                    "weight_g": w,
                    "sell_idr": sell,
                    "buyback_idr": buy,
                    "source_url": URL_GALERI24,
                })

    if not rows:
        raise RuntimeError("Galeri24: tidak ada data berat+harga yang berhasil diparse.")

    df = pd.DataFrame(rows)

    # dedup agar tidak dobel
    df = df.drop_duplicates(subset=["vendor", "weight_g", "sell_idr", "buyback_idr"]).reset_index(drop=True)

    # sort vendor + weight
    vendor_order = []
    for v in df["vendor"].tolist():
        if v not in vendor_order:
            vendor_order.append(v)
    rank = {v: i for i, v in enumerate(vendor_order)}
    df["__vr"] = df["vendor"].map(lambda x: rank.get(x, 9999))
    df["__w0"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[0])
    df["__w1"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[1])
    df = df.sort_values(["__vr", "vendor", "__w0", "__w1"]).drop(columns=["__vr", "__w0", "__w1"]).reset_index(drop=True)

    return df, update_label






def pick_price_row(df: pd.DataFrame, vendor: str, weight_g: float) -> Optional[Dict]:
    """
    Ambil 1 baris harga untuk vendor+weight tertentu.
    Contoh:
        pick_price_row(df, 'ANTAM', 100)
        pick_price_row(df, 'GALERI 24', 100)
    """
    v = normalize_vendor(vendor)
    m = (df["vendor"] == v) & (df["weight_g"].astype(float) == float(weight_g))
    out = df.loc[m]
    if out.empty:
        return None
    # Ambil yang terbaru jika ada multiple snapshot
    out = out.sort_values("snapshot_ts").tail(1)
    return out.iloc[0].to_dict()
