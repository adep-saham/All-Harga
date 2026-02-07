import pandas as pd
import requests
from datetime import datetime

URL_HRTA = "https://hrtagold.id/en/gold-price"
API_HRTA_DAILY = "https://hrtagold.id/api/v1/brandings/price/daily"

WEIGHT_ORDER = [0.1, 0.25, 0.5, 1, 2, 3, 4, 5, 10, 25, 50, 100, 150, 175, 200, 250, 500, 1000]
WEIGHT_RANK = {w: i for i, w in enumerate(WEIGHT_ORDER)}

def weight_sort_key(w: float):
    if w in WEIGHT_RANK:
        return (0, WEIGHT_RANK[w])
    return (1, w)

def _to_float_weight(x):
    try:
        return float(str(x).replace(",", ".").strip())
    except Exception:
        return None

def _to_int_money(x):
    # API biasanya sudah numeric; tapi kita buat tolerant
    try:
        if x is None:
            return 0
        if isinstance(x, (int, float)):
            return int(x)
        s = str(x)
        s = s.replace("Rp", "").replace("IDR", "").replace(" ", "").strip()
        s = s.replace(".", "").replace(",", "")
        return int(s) if s.isdigit() else 0
    except Exception:
        return 0

def fetch_hrta_daily_json() -> dict:
    headers = {
        "accept": "application/json, text/plain, */*",
        "referer": URL_HRTA,
        "user-agent": "Mozilla/5.0",
        "cache-control": "no-cache",
        "pragma": "no-cache",
    }
    r = requests.get(API_HRTA_DAILY, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()

def _extract_rows(obj) -> list[dict]:
    """
    HRTA API schema bisa berubah. Kita buat extractor yang fleksibel:
    - cari list item yang punya weight/gram + sell/buyback fields
    - handle beberapa kemungkinan key
    """
    candidates = []

    # helper: walk dict/list, kumpulkan list yang isinya dict
    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            # list of dict?
            if x and all(isinstance(i, dict) for i in x):
                candidates.append(x)
            for i in x:
                walk(i)

    walk(obj)

    # pilih kandidat list yang paling "harga-like"
    best = None
    best_score = -1

    def score_list(lst):
        keys = set()
        for it in lst[:10]:
            keys |= set(it.keys())
        # weight keys
        w_keys = {"weight", "gram", "grams", "size", "berat", "weight_g", "weightGram"}
        s_keys = {"sell", "sell_price", "selling", "sellingPrice", "priceSell", "harga_jual", "sellIdr"}
        b_keys = {"buy", "buyback", "buy_back", "buyBack", "buyback_price", "harga_buyback", "harga_beli", "buyIdr"}
        score = 0
        score += 3 if keys & w_keys else 0
        score += 3 if keys & s_keys else 0
        score += 2 if keys & b_keys else 0
        return score

    for lst in candidates:
        sc = score_list(lst)
        if sc > best_score:
            best_score = sc
            best = lst

    if not best or best_score < 3:
        return []

    # map field guesser
    def pick(it, options):
        for k in options:
            if k in it:
                return it.get(k)
        return None

    rows = []
    for it in best:
        w = pick(it, ["weight", "gram", "grams", "size", "berat", "weight_g", "weightGram"])
        sell = pick(it, ["sell", "sell_price", "selling", "sellingPrice", "priceSell", "harga_jual", "sellIdr", "price"])
        buyb = pick(it, ["buyback", "buy_back", "buyBack", "buy", "buyback_price", "harga_buyback", "harga_beli", "buyIdr"])

        w = _to_float_weight(w)
        if w is None or not (0.1 <= w <= 1000):
            continue

        rows.append({
            "weight_g": w,
            "sell_idr": _to_int_money(sell),
            "buyback_idr": _to_int_money(buyb),
        })

    return rows

def parse_hrta(_: str = "") -> tuple[pd.DataFrame, str]:
    """
    signature dibuat kompatibel dengan app kamu: parse_hrta(html)
    tapi kita tidak pakai html, langsung API.
    """
    data = fetch_hrta_daily_json()

    rows = _extract_rows(data)
    if not rows:
        # fallback: kalau API ternyata bungkusnya beda, simpan sedikit preview keys
        top_keys = list(data.keys()) if isinstance(data, dict) else type(data).__name__
        raise RuntimeError(f"HRTA API: tidak menemukan list harga. Top keys: {top_keys}")

    update_label = f"HRTA Daily Price (API) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    df = pd.DataFrame(rows)
    df["snapshot_ts"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    df["update_label"] = update_label
    df["source_site"] = "hrta"
    df["vendor"] = "HRTA"
    df["source_url"] = URL_HRTA

    # sort weight (urutan preferensi lalu numeric)
    df["__w0"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[0])
    df["__w1"] = df["weight_g"].map(lambda x: weight_sort_key(float(x))[1])
    df = df.sort_values(["__w0", "__w1"]).drop(columns=["__w0", "__w1"])

    # rapikan kolom urutan umum
    df = df[["snapshot_ts", "update_label", "source_site", "vendor", "weight_g", "sell_idr", "buyback_idr", "source_url"]]

    return df, update_label
