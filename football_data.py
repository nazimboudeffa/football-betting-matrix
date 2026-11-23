import csv
import io
import time
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import requests

# Simple in-memory cache: url -> (timestamp, rows)
_CSV_CACHE: Dict[str, Tuple[float, List[Dict[str, str]]]] = {}
_CSV_CACHE_TTL_SECONDS = 60 * 30  # 30 minutes


@dataclass
class FdMatchRow:
    raw: Dict[str, str]


# Map (season_folder, league_file) -> (csv_code_or_url_info)
# season_folder is the folder name used by openfootball raw API, e.g. "2025-26"
# league_file like "en.1.json"
FD_CSV_MAP = {
    ("2025-26", "en.1.json"): ("2526", "E0"),
    ("2025-26", "en.2.json"): ("2526", "E1"),
    ("2025-26", "en.3.json"): ("2526", "E2"),
    ("2025-26", "en.4.json"): ("2526", "E3"),
    ("2026-27", "en.1.json"): ("2627", "E0"),
    ("2026-27", "en.2.json"): ("2627", "E1"),
    # Ajouts possibles si CSV dispo (exemples)
    ("2025-26", "de.1.json"): ("2526", "D1"),
    ("2025-26", "de.2.json"): ("2526", "D2"),
    ("2025-26", "es.1.json"): ("2526", "SP1"),
    ("2025-26", "es.2.json"): ("2526", "SP2"),
    ("2025-26", "fr.1.json"): ("2526", "F1"),
    ("2025-26", "fr.2.json"): ("2526", "F2"),
    ("2025-26", "it.1.json"): ("2526", "I1"),
    ("2025-26", "it.2.json"): ("2526", "I2"),
    ("2025-26", "nl.1.json"): ("2526", "N1"),
    ("2025-26", "pt.1.json"): ("2526", "P1"),
    ("2025-26", "be.1.json"): ("2526", "B1"),
    ("2026-27", "de.1.json"): ("2627", "D1"),
    ("2026-27", "es.1.json"): ("2627", "SP1"),
    ("2026-27", "fr.1.json"): ("2627", "F1"),
    ("2026-27", "it.1.json"): ("2627", "I1"),
    ("2026-27", "nl.1.json"): ("2627", "N1"),
    ("2026-27", "pt.1.json"): ("2627", "P1"),
}


def _norm_name(s: str) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    # common replacements
    s = s.replace(" fc", " ")
    s = s.replace(" afc", " ")
    s = s.replace(" cf", " ")
    s = s.replace(" sc", " ")
    s = s.replace(" utd", " united")
    s = s.replace(" & ", " and ")
    s = s.replace("&", " and ")
    # remove some suffixes stuck
    s = s.replace("football club", " ").replace("soccer club", " ")
    for ch in [".", "'", "-", ","]:
        s = s.replace(ch, " ")
    # strip common leading/trailing words
    s = " ".join(s.split())
    # extra: remove trailing 'fc' if left alone
    if s.endswith(" fc"):
        s = s[:-3].strip()
    return s



def _name_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm_name(a), _norm_name(b)).ratio()


def football_data_csv_url(season_folder: str, league_file: str) -> Optional[str]:
    key = (season_folder, league_file)
    if key not in FD_CSV_MAP:
        return None
    season_code, div_code = FD_CSV_MAP[key]
    # format: https://www.football-data.co.uk/mmz4281/2526/E0.csv
    return f"https://www.football-data.co.uk/mmz4281/{season_code}/{div_code}.csv"


def fetch_csv_rows(url: str, use_cache: bool = True) -> List[Dict[str, str]]:
    now = time.time()
    if use_cache and url in _CSV_CACHE:
        ts, rows = _CSV_CACHE[url]
        if now - ts < _CSV_CACHE_TTL_SECONDS:
            return rows
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    text = resp.text
    try:
        f = io.StringIO(text)
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
        if use_cache:
            _CSV_CACHE[url] = (now, rows)
        return rows
    except Exception:
        return []


def _parse_date_candidates(date_str: str) -> List[str]:
    # football-data uses formats like DD/MM/YY or DD/MM/YYYY
    if not date_str:
        return []
    ds = date_str.strip()
    outs = []
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            dt = datetime.strptime(ds, fmt)
            outs.append(dt.strftime("%Y-%m-%d"))
            break
        except Exception:
            continue
    return outs


def find_fd_row_for_match(
    rows: List[Dict[str, str]],
    match_date: Optional[str],
    home_name: str,
    away_name: str,
) -> Optional[Dict[str, str]]:
    # match_date from openfootball is YYYY-MM-DD
    if not rows:
        return None

    candidates = []
    for r in rows:
        rdate_raw = r.get("Date") or r.get("date") or ""
        rdates = _parse_date_candidates(rdate_raw)
        date_ok = False
        if match_date and rdates and match_date in rdates:
            date_ok = True
        rhome = r.get("HomeTeam") or ""
        raway = r.get("AwayTeam") or ""
        hs = _name_sim(home_name, rhome)
        aw = _name_sim(away_name, raway)
        score_sim = hs + aw
        if date_ok:
            score_sim += 2.0
        # also accept if names very close even without date match? keep but lower
        candidates.append((score_sim, r, hs, aw, date_ok))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_row, hs, aw, date_ok = candidates[0]
    # Require reasonable name match: at least one side >=0.72 or sum>=1.45 with date
    if date_ok and (hs >= 0.7 or aw >= 0.7 or best_score >= 1.45):
        return best_row
    if best_score >= 1.75:
        return best_row
    return None


def format_fd_info(row: Dict[str, str]) -> List[tuple]:
    items: List[tuple] = []
    b365h = row.get("B365H")
    b365d = row.get("B365D")
    b365a = row.get("B365A")
    if b365h or b365d or b365a:
        items.append(("Bet365 (H/D/A)", f"{b365h or '-'} / {b365d or '-'} / {b365a or '-'}"))

    bwh = row.get("BWH")
    bwd = row.get("BWD")
    bwa = row.get("BWA")
    if bwh or bwd or bwa:
        items.append(("Bet&Win (H/D/A)", f"{bwh or '-'} / {bwd or '-'} / {bwa or '-'}"))

    psH = row.get("PSH") or row.get("PinnacleH")
    psD = row.get("PSD") or row.get("PinnacleD")
    psA = row.get("PSA") or row.get("PinnacleA")
    if psH or psD or psA:
        items.append(("Pinnacle (H/D/A)", f"{psH or '-'} / {psD or '-'} / {psA or '-'}"))

    fthg = row.get("FTHG")
    ftag = row.get("FTAG")
    ftr = row.get("FTR")
    if fthg not in (None, "") and ftag not in (None, ""):
        items.append(("Score FT", f"{fthg}-{ftag} ({ftr or '?'})"))

    hs = row.get("HS")
    as_ = row.get("AS")
    hst = row.get("HST")
    ast = row.get("AST")
    if hs or as_:
        items.append(("Tirs (tir cadrés)", f"{hs or '-'}-{as_ or '-'} ({hst or '-'}-{ast or '-'})"))

    hc = row.get("HC")
    ac = row.get("AC")
    if hc or ac:
        items.append(("Corners", f"{hc or '-'}-{ac or '-'}"))

    return items
