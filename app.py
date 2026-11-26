
import streamlit as st
import numpy as np
import pandas as pd
import requests

st.set_page_config(page_title="Hockey Pro AI", page_icon="🏒", layout="wide")
st.title("🏒 Анализатор матчей (4 000 000 симуляций)")

@st.cache_data(ttl=3600)
def get_nhl_teams():
    url = "https://nhle.com"
    res = requests.get(url).json()
    teams = {}
    for t in res["standings"]:
        abbrev = t["teamAbbrev"]["default"]
        name = t["teamName"]["default"]
        teams[f"{name} ({abbrev})"] = {
            "abbrev": abbrev,
            "gp": t["gamesPlayed"],
            "gf": t["goalFor"],
            "ga": t["goalAgainst"],
            "home_gf": t["homeGoalsFor"],
            "home_ga": t["homeGoalsAgainst"],
            "home_gp": t["homeGamesPlayed"],
            "road_gf": t["roadGoalsFor"],
            "road_ga": t["roadGoalsAgainst"],
            "road_gp": t["roadGamesPlayed"]
        }
    return teams

@st.cache_data(ttl=3600)
def get_roster_stats(abbrev):
    url = f"https://nhle.com{abbrev}/now"
    res = requests.get(url).json()
    skaters = []
    for s in res.get("skaters", []):
        skaters.append({
            "Игрок": f"{s['firstName']['default']} {s['lastName']['default']}",
            "Поз.": s["positionCode"],
            "Игры": s["gamesPlayed"],
            "Голы": s["goals"],
            "Пасы": s["assists"],
            "Очки": s["points"],
            "+/-": s["plusMinus"],
            "Броски": s["shots"],
            "Штр": s["penaltyMinutes"]
        })
    goalies = []
    for g in res.get("goalies", []):
        goalies.append({
            "Вратарь": f"{g['firstName']['default']} {g['lastName']['default']}",
            "Игры": g["gamesPlayed"],
            "Победы": g["wins"],
            "% ОБ": round(g["savePercentage"] * 100, 2),
            "КН (GAA)": round(g["goalsAgainstAverage"], 2),
            "Сухари": g["shutouts"]
        })
    return pd.DataFrame(skaters), pd.DataFrame(goalies)

def run_simulations(l1, l2, n=1_000_000):
    rng = np.random.default_rng()
    
    # 1. Двумерный Пуассон
    cov = 0.14
    z = rng.poisson(cov, n)
    x_bp = rng.poisson(max(0.1, l1 - cov), n) + z
    y_bp = rng.poisson(max(0.1, l2 - cov), n) + z
    
    # 2. Диксон-Коулз (поправка на ничьи/низы)
    x_dc = rng.poisson(l1, n)
    y_dc = rng.poisson(l2, n)
    mask_low = (x_dc <= 1) & (y_dc <= 1) & (rng.random(n) < 0.08)
    x_dc[mask_low] = np.where(x_dc[mask_low] == y_dc[mask_low], x_dc[mask_low], x_dc[mask_low] + 1)
    
    # 3. Отрицательное биномиальное (дисперсия)
    r = 6.5
    x_nb = rng.negative_binomial(r, r / (r + l1), n)
    y_nb = rng.negative_binomial(r, r / (r + l2), n)
    
    # 4. Марковская цепь + Empty Net
    x_en = rng.poisson(l1 * 0.93, n)
    y_en = rng.poisson(l2 * 0.93, n)
    diff = x_en - y_en
    r_en = rng.random(n)
    x_en += (diff == 1) & (r_en < 0.22)
    y_en += (diff == 1) & (r_en >= 0.22) & (r_en < 0.33)
    y_en += (diff == -1) & (r_en < 0.22)
    x_en += (diff == -1) & (r_en >= 0.22) & (r_en < 0.33)
    
    return np.concatenate([x_bp, x_dc, x_nb, x_en]), np.concatenate([y_bp, y_dc, y_nb, y_en])

try:
    teams_data = get_nhl_teams()
    team_names = sorted(list(teams_data.keys()))
    
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        t1_name = st.selectbox("Хозяева (П1)", team_names, index=0)
    with col_t2:
        t2_name = st.selectbox("Гости (П2)", team_names, index=1)
        
    t1 = teams_data[t1_name]
    t2 = teams_data[t2_name]
    
    league_avg = 3.05
    t1_att = (t1["home_gf"] / max(1, t1["home_gp"])) / league_avg
    t1_def = (t1["home_ga"] / max(1, t1["home_gp"])) / league_avg
    t2_att = (t2["road_gf"] / max(1, t2["road_gp"])) / league_avg
    t2_def = (t2["road_ga"] / max(1, t2["road_gp"])) / league_avg
    
    lambda1 = round(t1_att * t2_def * league_avg * 1.04, 2)
    lambda2 = round(t2_att * t1_def * league_avg * 0.96, 2)
    
    st.caption(f"Расчетный xG (λ): **{t1['abbrev']} {lambda1}** — **{t2['abbrev']} {lambda2}**")
    
    if st.button("🚀 Запустить 4 000 000 симуляций", use_container_width=True):
        g1, g2 = run_simulations(lambda1, lambda2)
        tot = g1 + g2
        
        tab1, tab2, tab3 = st.tabs(["📊 Исходы и Точный счет", f"📋 Состав {t1['abbrev']}", f"📋 Состав {t2['abbrev']}"])
        
        with tab1:
            markets = [
                ("П1 (осн. время)", np.mean(g1 > g2)),
                ("Х (ничья)", np.mean(g1 == g2)),
                ("П2 (осн. время)", np.mean(g1 < g2)),
                ("1Х", np.mean(g1 >= g2)),
                ("2Х", np.mean(g1 <= g2)),
                ("ТБ 4.5", np.mean(tot > 4.5)),
                ("ТМ 4.5", np.mean(tot < 4.5)),
                ("ТБ 5.5", np.mean(tot > 5.5)),
                ("ТМ 5.5", np.mean(tot < 5.5)),
                ("ТБ 6.5", np.mean(tot > 6.5)),
                ("ТМ 6.5", np.mean(tot < 6.5)),
                ("Ф1 (-1.5)", np.mean((g1 - g2) > 1.5)),
                ("Ф1 (+1.5)", np.mean((g1 - g2) > -1.5)),
                ("Ф2 (-1.5)", np.mean((g2 - g1) > 1.5)),
                ("Ф2 (+1.5)", np.mean((g2 - g1) > -1.5)),
                ("П1 + ТБ 4.5", np.mean((g1 > g2) & (tot > 4.5))),
                ("П1 + ТМ 5.5", np.mean((g1 > g2) & (tot < 5.5))),
                ("П2 + ТБ 4.5", np.mean((g1 < g2) & (tot > 4.5))),
                ("П2 + ТМ 5.5", np.mean((g1 < g2) & (tot < 5.5))),
                ("1Х + ТБ 4.5", np.mean((g1 >= g2) & (tot > 4.5))),
                ("1Х + ТМ 5.5", np.mean((g1 >= g2) & (tot < 5.5))),
                ("2Х + ТБ 4.5", np.mean((g1 <= g2) & (tot > 4.5))),
                ("2Х + ТМ 5.5", np.mean((g1 <= g2) & (tot < 5.5))),
            ]
            df_m = pd.DataFrame(markets, columns=["Маркет", "Вероятность"])
            df_m["Вероятность (%)"] = (df_m["Вероятность"] * 100).round(2)
            st.dataframe(df_m[["Маркет", "Вероятность (%)"]], use_container_width=True, hide_index=True)
            
            st.subheader("🎯 Топ-5 точных счетов (60 мин)")
            packed = g1 * 100 + g2
            vals, counts = np.unique(packed, return_counts=True)
            top_idx = np.argsort(-counts)[:5]
            top_list = []
            for idx in top_idx:
                sc1, sc2 = divmod(vals[idx], 100)
                prob = (counts[idx] / len(g1)) * 100
                top_list.append({"Точный счет": f"{sc1}:{sc2}", "Вероятность (%)": round(prob, 2)})
            st.dataframe(pd.DataFrame(top_list), use_container_width=True, hide_index=True)
            
        with tab2:
            sk1, gl1 = get_roster_stats(t1["abbrev"])
            st.subheader("Вратари")
            st.dataframe(gl1, use_container_width=True, hide_index=True)
            st.subheader("Полевые игроки (весь сезон)")
            st.dataframe(sk1.sort_values(by="Очки", ascending=False), use_container_width=True, hide_index=True)
            
        with tab3:
            sk2, gl2 = get_roster_stats(t2["abbrev"])
            st.subheader("Вратари")
            st.dataframe(gl2, use_container_width=True, hide_index=True)
            st.subheader("Полевые игроки (весь сезон)")
            st.dataframe(sk2.sort_values(by="Очки", ascending=False), use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"Ошибка загрузки данных: {e}")
