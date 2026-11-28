import numpy as np
import requests
from collections import Counter

def fetch_nhl_schedule_and_standings():
    headers = {"User-Agent": "Mozilla/5.0"}
    matches = []
    team_stats = {}

    try:
        st_resp = requests.get("https://nhle.com", headers=headers, timeout=10)
        if st_resp.status_code == 200:
            for row in st_resp.json().get("standings", []):
                abbrev = row.get("teamAbbrev", {}).get("default", "")
                gp = max(1, row.get("gamesPlayed", 1))
                gf = row.get("goalFor", 0)
                ga = row.get("goalAgainst", 0)
                xg60 = round((gf / gp) * 0.96, 2)
                xga60 = round((ga / gp) * 0.96, 2)
                hdcf = round(50.0 + (xg60 - xga60) * 6.5, 1)
                team_stats[abbrev] = {
                    "name": row.get("teamName", {}).get("default", abbrev),
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
        sch_resp = requests.get("https://nhle.com", headers=headers, timeout=10)
        if sch_resp.status_code == 200:
            for day in sch_resp.json().get("gameWeek", [])[:2]:
                date_str = day.get("date", "")
                for g in day.get("games", []):
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

def fetch_nhl_last_10(team_abbrev: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    player_counter = Counter()
    sf, sa = [], []

    try:
        url = f"https://nhle.com{team_abbrev}/now"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            games = resp.json().get("games", [])
            finished = [g for g in games if g.get("gameState") in ("OFF", "FINAL")][-10:]
            for idx, g in enumerate(finished):
                gid = g.get("id")
                is_home = g.get("homeTeam", {}).get("abbrev") == team_abbrev
                box_resp = requests.get(f"https://nhle.com{gid}/boxscore", headers=headers, timeout=8)
                if box_resp.status_code == 200:
                    box = box_resp.json()
                    side = "homeTeam" if is_home else "awayTeam"
                    opp = "awayTeam" if is_home else "homeTeam"
                    sf.append(box.get(side, {}).get("sog", 30))
                    sa.append(box.get(opp, {}).get("sog", 30))
                    weight = 1.5 if idx >= 7 else 1.0
                    p_stats = box.get("playerByGameStats", {}).get(side, {})
                    for group in ["forwards", "defense", "goalies"]:
                        for p in p_stats.get(group, []):
                            name = p.get("name", {}).get("default", "")
                            if name:
                                player_counter[name] += weight
    except Exception:
        pass

    avg_sf = round(float(np.mean(sf)), 1) if sf else 30.5
    avg_sa = round(float(np.mean(sa)), 1) if sa else 29.8
    return {
        "roster": [p for p, _ in player_counter.most_common(20)],
        "avg_sog": avg_sf,
        "corsi_pct": round((avg_sf / (avg_sf + avg_sa)) * 100, 1)
    }

class HockeyMatchSimulator:
    def __init__(self, n_sims: int = 500_000):
        self.n_sims = n_sims
        self.rng = np.random.default_rng()

    def calculate_lambdas(self, home_stats: dict, away_stats: dict):
        h_off = home_stats['xg_per60'] * (0.7 + 0.3 * (home_stats['hdcf_pct'] / 50.0))
        a_off = away_stats['xg_per60'] * (0.7 + 0.3 * (away_stats['hdcf_pct'] / 50.0))
        h_def = away_stats['xga_per60'] / 2.85
        a_def = home_stats['xga_per60'] / 2.85
        h_pp = (home_stats['pp_pct'] / 100.0) * (1.0 - away_stats['pk_pct'] / 100.0) * 3.5
        a_pp = (away_stats['pp_pct'] / 100.0) * (1.0 - home_stats['pk_pct'] / 100.0) * 3.5

        l1 = max(0.5, (h_off * h_def * 1.08) + h_pp - away_stats['goalie_gsax_per60'])
        l2 = max(0.5, (a_off * a_def) + a_pp - home_stats['goalie_gsax_per60'])
        return round(l1, 3), round(l2, 3)

    def run_ensemble(self, home_stats: dict, away_stats: dict) -> dict:
        l1, l2 = self.calculate_lambdas(home_stats, away_stats)
        n = self.n_sims // 4

        # 1. Bivariate Poisson
        x3 = self.rng.poisson(0.12, n)
        g1_bp = self.rng.poisson(max(0.05, l1 - 0.12), n) + x3
        g2_bp = self.rng.poisson(max(0.05, l2 - 0.12), n) + x3

        # 2. Dixon-Coles
        g1_dc = self.rng.poisson(l1, n)
        g2_dc = self.rng.poisson(l2, n)
        m00 = (g1_dc == 0) & (g2_dc == 0) & (self.rng.random(n) < 0.08 * l1 * l2)
        g1_dc[m00], g2_dc[m00] = 1, 1

        # 3. Negative Binomial
        g1_nb = self.rng.negative_binomial(8.0, 8.0 / (8.0 + l1), n)
        g2_nb = self.rng.negative_binomial(8.0, 8.0 / (8.0 + l2), n)

        # 4. Markov Chain + Empty Net
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
