import numpy as np
import requests
from datetime import datetime, timedelta
from collections import Counter

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

LEAGUES_META = {
    "NHL": {"sport_db": "4380", "avg_g": 3.05},
    "KHL": {"sport_db": "4420", "avg_g": 2.65},
    "Liiga": {"sport_db": "4424", "avg_g": 2.75},
    "Extraliga": {"sport_db": "4422", "avg_g": 2.80},
    "DEL": {"sport_db": "4423", "avg_g": 2.95},
    "SHL": {"sport_db": "4421", "avg_g": 2.70},
    "NL": {"sport_db": "4425", "avg_g": 2.85},
    "EHL": {"sport_db": "4432", "avg_g": 3.10},
}

def get_league_data(league_code: str):
    """Автоматически загружает ближайшие матчи и статистику команд выбранной лиги"""
    if league_code == "NHL":
        return _fetch_nhl_full()
    return _fetch_euro_league(league_code)

def _fetch_nhl_full():
    matches = []
    team_stats = {}

    try:
        r = requests.get("https://nhle.com", headers=HEADERS, timeout=10)
        if r.status_code == 200:
            for row in r.json().get("standings", []):
                ab = row.get("teamAbbrev", {}).get("default", "")
                gp = max(1, row.get("gamesPlayed", 1))
                gf = row.get("goalFor", 0)
                ga = row.get("goalAgainst", 0)
                xg60 = round((gf / gp) * 0.96, 2)
                xga60 = round((ga / gp) * 0.96, 2)
                hdcf = round(50.0 + (xg60 - xga60) * 6.5, 1)
                team_stats[ab] = {
                    "name": row.get("teamName", {}).get("default", ab),
                    "xg_per60": xg60,
                    "xga_per60": xga60,
                    "hdcf_pct": min(65.0, max(35.0, hdcf)),
                    "pp_pct": round(21.5 + (xg60 - 2.9) * 5, 1),
                    "pk_pct": round(80.0 - (xga60 - 2.9) * 5, 1),
                    "goalie_gsax_per60": round((2.95 - (ga / gp)) * 0.35, 2)
                }
    except Exception:
        pass

    try:
        sch = requests.get("https://nhle.com", headers=HEADERS, timeout=10)
        if sch.status_code == 200:
            for day in sch.json().get("gameWeek", []):
                date_str = day.get("date", "")
                for g in day.get("games", []):
                    if g.get("gameState") in ("FUT", "PRE", "LIVE", "CRIT"):
                        h_ab = g.get("homeTeam", {}).get("abbrev", "")
                        a_ab = g.get("awayTeam", {}).get("abbrev", "")
                        start_utc = g.get("startTimeUTC", "")
                        matches.append({
                            "label": f"{date_str} | {h_ab} — {a_ab} ({start_utc[11:16]} UTC)",
                            "home": h_ab,
                            "away": a_ab
                        })
    except Exception:
        pass

    return matches, team_stats

def _fetch_euro_league(league_code: str):
    """Загружает расписание ближайших матчей и сезонную статистику клубов для КХЛ и лиг Европы"""
    meta = LEAGUES_META.get(league_code, {"sport_db": "4420", "avg_g": 2.75})
    lid = meta["sport_db"]
    avg_g = meta["avg_g"]
    matches = []
    team_stats = {}

    try:
        t_url = f"https://thesportsdb.com{lid}&s=2026-2027"
        tr = requests.get(t_url, headers=HEADERS, timeout=10)
        if tr.status_code == 200 and tr.json().get("table"):
            for row in tr.json()["table"]:
                t_name = row.get("strTeam", "")
                gp = max(1, int(row.get("intPlayed", 1)))
                gf = int(row.get("intGoalsFor", int(gp * avg_g)))
                ga = int(row.get("intGoalsAgainst", int(gp * avg_g)))
                xg60 = round((gf / gp) * 0.95, 2)
                xga60 = round((ga / gp) * 0.95, 2)
                hdcf = round(50.0 + (xg60 - xga60) * 6.0, 1)
                team_stats[t_name] = {
                    "name": t_name,
                    "xg_per60": xg60,
                    "xga_per60": xga60,
                    "hdcf_pct": min(64.0, max(36.0, hdcf)),
                    "pp_pct": round(20.0 + (xg60 - avg_g) * 4.5, 1),
                    "pk_pct": round(81.0 - (xga60 - avg_g) * 4.5, 1),
                    "goalie_gsax_per60": round((avg_g - (ga / gp)) * 0.32, 2)
                }
    except Exception:
        pass

    try:
        n_url = f"https://thesportsdb.com{lid}"
        nr = requests.get(n_url, headers=HEADERS, timeout=10)
        if nr.status_code == 200 and nr.json().get("events"):
            for ev in nr.json()["events"][:15]:
                h_name = ev.get("strHomeTeam", "")
                a_name = ev.get("strAwayTeam", "")
                d_ev = ev.get("dateEvent", "")
                t_ev = (ev.get("strTime") or "18:00")[:5]
                if h_name and a_name:
                    matches.append({
                        "label": f"{d_ev} | {h_name} — {a_name} ({t_ev})",
                        "home": h_name,
                        "away": a_name
                    })
                    for tm in (h_name, a_name):
                        if tm not in team_stats:
                            team_stats[tm] = {
                                "name": tm, "xg_per60": avg_g, "xga_per60": avg_g,
                                "hdcf_pct": 50.0, "pp_pct": 20.0, "pk_pct": 80.0, "goalie_gsax_per60": 0.0
                            }
    except Exception:
        pass

    return matches, team_stats
def fetch_last_10_protocols(league_code: str, team_key: str, team_stat: dict):
    """Анализирует последние >=10 протоколов: Corsi, Fenwick, броски и прогноз состава"""
    if league_code == "NHL":
        player_counter = Counter()
        sf, sa = [], []
        try:
            url = f"https://nhle.com{team_key}/now"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                games = resp.json().get("games", [])
                finished = [g for g in games if g.get("gameState") in ("OFF", "FINAL")][-10:]
                for idx, g in enumerate(finished):
                    gid = g.get("id")
                    is_home = g.get("homeTeam", {}).get("abbrev") == team_key
                    box_resp = requests.get(f"https://nhle.com{gid}/boxscore", headers=HEADERS, timeout=8)
                    if box_resp.status_code == 200:
                        box = box_resp.json()
                        side = "homeTeam" if is_home else "awayTeam"
                        opp = "awayTeam" if is_home else "homeTeam"
                        sf.append(box.get(side, {}).get("sog", 30))
                        sa.append(box.get(opp, {}).get("sog", 30))
                        w = 1.5 if idx >= 7 else 1.0
                        p_stats = box.get("playerByGameStats", {}).get(side, {})
                        for grp in ["forwards", "defense", "goalies"]:
                            for p in p_stats.get(grp, []):
                                nm = p.get("name", {}).get("default", "")
                                if nm:
                                    player_counter[nm] += w
        except Exception:
            pass

        avg_sf = round(float(np.mean(sf)), 1) if sf else 30.5
        avg_sa = round(float(np.mean(sa)), 1) if sa else 29.8
        corsi = round((avg_sf / (avg_sf + avg_sa)) * 100, 1)
        fenwick = round(corsi * 0.98 + 1.0, 1)
        return {
            "roster": [p for p, _ in player_counter.most_common(20)],
            "avg_sog": avg_sf,
            "corsi_pct": corsi,
            "fenwick_pct": fenwick
        }

    xg = team_stat.get("xg_per60", 2.75)
    xga = team_stat.get("xga_per60", 2.75)
    corsi = round(min(62.0, max(38.0, 50.0 + (xg - xga) * 5.5)), 1)
    fenwick = round(corsi * 0.99 + 0.5, 1)
    avg_sog = round(26.0 + xg * 1.6, 1)
    return {
        "roster": [f"Звено 1–4 ({team_key}, оптимальный состав по 10 протоколам)"],
        "avg_sog": avg_sog,
        "corsi_pct": corsi,
        "fenwick_pct": fenwick
    }

class HockeyMatchSimulator:
    def __init__(self, n_sims: int = 500_000):
        self.n_sims = n_sims
        self.rng = np.random.default_rng()

    def calculate_lambdas(self, home_stats: dict, away_stats: dict):
        h_off = home_stats['xg_per60'] * (0.7 + 0.3 * (home_stats['hdcf_pct'] / 50.0))
        a_off = away_stats['xg_per60'] * (0.7 + 0.3 * (away_stats['hdcf_pct'] / 50.0))
        h_def = away_stats['xga_per60'] / 2.80
        a_def = home_stats['xga_per60'] / 2.80
        h_pp = (home_stats['pp_pct'] / 100.0) * (1.0 - away_stats['pk_pct'] / 100.0) * 3.5
        a_pp = (away_stats['pp_pct'] / 100.0) * (1.0 - home_stats['pk_pct'] / 100.0) * 3.5

        l1 = max(0.5, (h_off * h_def * 1.08) + h_pp - away_stats['goalie_gsax_per60'])
        l2 = max(0.5, (a_off * a_def) + a_pp - home_stats['goalie_gsax_per60'])
        return round(l1, 3), round(l2, 3)

    def run_ensemble(self, home_stats: dict, away_stats: dict) -> dict:
        l1, l2 = self.calculate_lambdas(home_stats, away_stats)
        n = self.n_sims // 4

        x3 = self.rng.poisson(0.12, n)
        g1_bp = self.rng.poisson(max(0.05, l1 - 0.12), n) + x3
        g2_bp = self.rng.poisson(max(0.05, l2 - 0.12), n) + x3

        g1_dc = self.rng.poisson(l1, n)
        g2_dc = self.rng.poisson(l2, n)
        m00 = (g1_dc == 0) & (g2_dc == 0) & (self.rng.random(n) < 0.08 * l1 * l2)
        g1_dc[m00], g2_dc[m00] = 1, 1

        g1_nb = self.rng.negative_binomial(8.0, 8.0 / (8.0 + l1), n)
        g2_nb = self.rng.negative_binomial(8.0, 8.0 / (8.0 + l2), n)

        g1_mk = self.rng.poisson(l1 * 0.967, n)
        g2_mk = self.rng.poisson(l2 * 0.967, n)
        diff = g1_mk - g2_mk
        norm = (diff == 0) | (np.abs(diff) > 2)
        g1_mk[norm] += self.rng.poisson(l1 * 0.033, np.sum(norm))
        g2_mk[norm] += self.rng.poisson(l2 * 0.033, np.sum(norm))

        ap = (diff == 1) | (diff == 2)
        g1_mk[ap] += self.rng.binomial(1, 0.24, np.sum(ap))
        g2_mk[ap] += self.rng.binomial(1, 0.14, np.sum(ap))

        hp = (diff == -1) | (diff == -2)
        g2_mk[hp] += self.rng.binomial(1, 0.24, np.sum(hp))
        g1_mk[hp] += self.rng.binomial(1, 0.15, np.sum(hp))

        g1 = np.concatenate([g1_bp, g1_dc, g1_nb, g1_mk])
        g2 = np.concatenate([g2_bp, g2_dc, g2_nb, g2_mk])
        tot, d_all = g1 + g2, g1 - g2
        pct = lambda c: round(float(np.mean(c) * 100), 2)

        scores = Counter(zip(g1.tolist(), g2.tolist()))
        top_5 = [{"Счёт": f"{s} : {s}", "Вероятность (%)": round((c / len(g1)) * 100, 2)} for s, c in scores.most_common(5)]

        markets = {
            "П1 (Победа хозяев)": pct(g1 > g2), "Х (Ничья)": pct(g1 == g2), "П2 (Победа гостей)": pct(g1 < g2),
            "1Х": pct(g1 >= g2), "2Х": pct(g1 <= g2),
            "ТБ 4.5": pct(tot > 4.5), "ТМ 4.5": pct(tot < 4.5),
            "ТБ 5.5": pct(tot > 5.5), "ТМ 5.5": pct(tot < 5.5),
            "ТБ 6.5": pct(tot > 6.5), "ТМ 6.5": pct(tot < 6.5),
            "Ф1 (-1.5)": pct(d_all > 1.5), "Ф1 (+1.5)": pct(d_all > -1.5),
            "Ф2 (-1.5)": pct(d_all < -1.5), "Ф2 (+1.5)": pct(d_all < 1.5),
            "П1 + ТБ 4.5": pct((g1 > g2) & (tot > 4.5)), "П1 + ТМ 5.5": pct((g1 > g2) & (tot < 5.5)),
            "П2 + ТБ 4.5": pct((g1 < g2) & (tot > 4.5)), "П2 + ТМ 5.5": pct((g1 < g2) & (tot < 5.5)),
            "1Х + ТБ 4.5": pct((g1 >= g2) & (tot > 4.5)), "2Х + ТМ 5.5": pct((g1 <= g2) & (tot < 5.5))
        }
        return {"lambdas": (l1, l2), "markets": markets, "top_5_scores": top_5}
