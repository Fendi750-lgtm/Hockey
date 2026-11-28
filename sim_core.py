import numpy as np
from collections import Counter

class HockeyMatchSimulator:
    def __init__(self, n_sims: int = 500_000):
        self.n_sims = n_sims
        self.rng = np.random.default_rng()

    def calculate_lambdas(self, h: dict, a: dict):
        h_off = h['xg_per60'] * (0.7 + 0.3 * (h['hdcf_pct'] / 50.0))
        a_off = a['xg_per60'] * (0.7 + 0.3 * (a['hdcf_pct'] / 50.0))
        h_pp = (h['pp_pct'] / 100.0) * (1.0 - a['pk_pct'] / 100.0) * 3.5
        a_pp = (a['pp_pct'] / 100.0) * (1.0 - h['pk_pct'] / 100.0) * 3.5
        l1 = max(0.5, (h_off * (a['xga_per60'] / 2.80) * 1.08) + h_pp - a['goalie_gsax_per60'])
        l2 = max(0.5, (a_off * (h['xga_per60'] / 2.80)) + a_pp - h['goalie_gsax_per60'])
        return round(l1, 3), round(l2, 3)

    def run_ensemble(self, h: dict, a: dict) -> dict:
        l1, l2 = self.calculate_lambdas(h, a)
        n = self.n_sims // 4

        x3 = self.rng.poisson(0.12, n)
        g1_bp = self.rng.poisson(max(0.05, l1 - 0.12), n) + x3
        g2_bp = self.rng.poisson(max(0.05, l2 - 0.12), n) + x3

        g1_dc, g2_dc = self.rng.poisson(l1, n), self.rng.poisson(l2, n)
        m00 = (g1_dc == 0) & (g2_dc == 0) & (self.rng.random(n) < 0.08 * l1 * l2)
        g1_dc[m00], g2_dc[m00] = 1, 1

        g1_nb = self.rng.negative_binomial(8.0, 8.0 / (8.0 + l1), n)
        g2_nb = self.rng.negative_binomial(8.0, 8.0 / (8.0 + l2), n)

        g1_mk, g2_mk = self.rng.poisson(l1 * 0.967, n), self.rng.poisson(l2 * 0.967, n)
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

        top_5 = [{"Счёт": f"{s} : {s}", "Вероятность (%)": round((c / len(g1)) * 100, 2)} for s, c in Counter(zip(g1.tolist(), g2.tolist())).most_common(5)]
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
