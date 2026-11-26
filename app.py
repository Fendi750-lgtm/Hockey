import streamlit as st
import numpy as np
import pandas as pd
import requests
from io import StringIO

st.set_page_config(page_title="Hockey Pro AI", page_icon="🏒", layout="wide")
st.title("🏒 Анализатор матчей (7 лиг • 4 000 000 симуляций)")

# --- НАСТРОЙКИ ЛИГ (СРЕДНЯЯ РЕЗУЛЬТАТИВНОСТЬ И БОНУС ЛЬДА) ---
LEAGUES_CONFIG = {
    "🇺🇸🇨🇦 НХЛ (Авто-API + полные составы)": {"code": "NHL", "avg": 3.05, "home_boost": 1.04},
    "🇷🇺 КХЛ (KHL)": {"code": "KHL", "avg": 2.65, "home_boost": 1.05},
    "🇫🇮 Финляндия (Liiga)": {"code": "LIIGA", "avg": 2.70, "home_boost": 1.05},
    "🇸🇪 Швеция (SHL)": {"code": "SHL", "avg": 2.68, "home_boost": 1.05},
    "🇨🇿 Чехия (Tipsport Extraliga)": {"code": "ELH", "avg": 2.75, "home_boost": 1.06},
    "🇨🇭 Швейцария (National League)": {"code": "NL", "avg": 2.85, "home_boost": 1.05},
    "🇳🇴 Норвегия (EHL)": {"code": "EHL", "avg": 3.10, "home_boost": 1.06},
}

# --- ПРЕДУСТАНОВЛЕННЫЕ БАЗЫ КОМАНД СЕЗОНА 2026/27 ---
PRESET_TEAMS = {
    "KHL": [
        "Металлург Мг", "ЦСКА", "Локомотив", "Авангард", "Северсталь", "Торпедо",
        "Спартак", "Динамо Москва", "Нефтехимик", "Амур", "Автомобилист", "Ак Барс",
        "Трактор", "Салават Юлаев", "Барыс", "Куньлунь Ред Стар", "Динамо Минск",
        "СКА", "Сибирь", "Адмирал", "Лада", "ХК Сочи"
    ],
    "LIIGA": [
        "Lukko", "JYP", "Ilves", "Jukurit", "Tappara", "HIFK", "Kärpät",
        "KalPa", "Ässät", "Pelicans", "TPS", "KooKoo", "SaiPa", "HPK", "Sport", "Kiekko-Espoo"
    ],
    "SHL": [
        "Färjestad BK", "Skellefteå AIK", "Frölunda HC", "Växjö Lakers", "Luleå HF",
        "Brynäs IF", "Timrå IK", "Rögle BK", "Leksands IF", "Linköping HC",
        "Örebro HK", "Malmö Redhawks", "HV71", "MoDo Hockey"
    ],
    "ELH": [
        "HC Dynamo Pardubice", "HC Sparta Praha", "HC Oceláři Třinec", "HC Kometa Brno",
        "Mountfield HK", "Bílí Tygři Liberec", "HC Verva Litvínov", "HC Motor České Budějovice",
        "HC Škoda Plzeň", "HC Vítkovice Ridera", "HC Energie Karlovy Vary", "HC Olomouc",
        "BK Mladá Boleslav", "Rytíři Kladno"
    ],
    "NL": [
        "ZSC Lions", "Lausanne HC", "EV Zug", "HC Fribourg-Gottéron", "SC Bern",
        "HC Davos", "HC Lugano", "Genève-Servette HC", "EHC Biel-Bienne", "HC Ambri-Piotta",
        "SCL Tigers", "SC Rapperswil-Jona Lakers", "EHC Kloten", "HC Ajoie"
    ],
    "EHL": [
        "Storhamar", "Vålerenga", "Stavanger Oilers", "Frisk Asker", "Sparta Sarpsborg",
        "Lillehammer", "Stjernen", "Lørenskog", "Comet", "Nidaros"
    ]
}

# --- 1. ЗАГРУЗКА ДАННЫХ НХЛ ---
@st.cache_data(ttl=3600)
def get_nhl_teams():
    d = ".".join(["api-web", "nhle", "com"])
    u = f"https://{d}/v1/standings/now"
    res = requests.get(u, timeout=10).json()
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
def get_nhl_roster(abbrev):
    d = ".".join(["api-web", "nhle", "com"])
    u = f"https://{d}/v1/club-stats/{abbrev}/now"
    res = requests.get(u, timeout=10).json()
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

# --- 2. МАТЕМАТИЧЕСКИЙ АНСАМБЛЬ (4 МОДЕЛИ x 1 000 000) ---
def run_simulations(l1, l2, n=1_000_000):
    rng = np.random.default_rng()
    
    # 1. Двумерный Пуассон
    cov = 0.14
    z = rng.poisson(cov, n)
    x_bp = rng.poisson(max(0.1, l1 - cov), n) + z
    y_bp = rng.poisson(max(0.1, l2 - cov), n) + z
    
    # 2. Диксон-Коулз
    x_dc = rng.poisson(l1, n)
    y_dc = rng.poisson(l2, n)
    mask_low = (x_dc <= 1) & (y_dc <= 1) & (rng.random(n) < 0.08)
    x_dc[mask_low] = np.where(x_dc[mask_low] == y_dc[mask_low], x_dc[mask_low], x_dc[mask_low] + 1)
    
    # 3. Отрицательное биномиальное
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

# --- 3. ИНТЕРФЕЙС ВЫБОРА ЛИГИ ---
selected_league = st.selectbox("Выберите лигу", list(LEAGUES_CONFIG.keys()))
cfg = LEAGUES_CONFIG[selected_league]
l_code = cfg["code"]

sk1, gl1, sk2, gl2 = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

if l_code == "NHL":
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
        
        avg = cfg["avg"]
        t1_att = (t1["home_gf"] / max(1, t1["home_gp"])) / avg
        t1_def = (t1["home_ga"] / max(1, t1["home_gp"])) / avg
        t2_att = (t2["road_gf"] / max(1, t2["road_gp"])) / avg
        t2_def = (t2["road_ga"] / max(1, t2["road_gp"])) / avg
        
        base_l1 = t1_att * t2_def * avg * cfg["home_boost"]
        base_l2 = t2_att * t1_def * avg * (2 - cfg["home_boost"])
        sk1, gl1 = get_nhl_roster(t1["abbrev"])
        sk2, gl2 = get_nhl_roster(t2["abbrev"])
    except Exception as e:
        st.error(f"Ошибка загрузки НХЛ: {e}")
        base_l1, base_l2 = 2.8, 2.5
        t1_name, t2_name = "Хозяева", "Гости"
else:
    # Режим КХЛ / Финляндия / Швеция / Чехия / Швейцария / Норвегия
    team_list = PRESET_TEAMS[l_code]
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        t1_name = st.selectbox("Хозяева (П1)", team_list, index=0)
        gp1 = st.number_input(f"Игры дома ({t1_name})", 1, 80, 15)
        gf1 = st.number_input(f"Забито дома ({t1_name})", 0, 300, 45)
        ga1 = st.number_input(f"Пропущено дома ({t1_name})", 0, 300, 35)
    with col_t2:
        t2_name = st.selectbox("Гости (П2)", team_list, index=1)
        gp2 = st.number_input(f"Игры в гостях ({t2_name})", 1, 80, 15)
        gf2 = st.number_input(f"Забито в гостях ({t2_name})", 0, 300, 38)
        ga2 = st.number_input(f"Пропущено в гостях ({t2_name})", 0, 300, 42)
        
    avg = cfg["avg"]
    t1_att = (gf1 / gp1) / avg
    t1_def = (ga1 / gp1) / avg
    t2_att = (gf2 / gp2) / avg
    t2_def = (ga2 / gp2) / avg
    
    base_l1 = t1_att * t2_def * avg * cfg["home_boost"]
    base_l2 = t2_att * t1_def * avg * (2 - cfg["home_boost"])

# --- БЛОК ТОНКОЙ КОРРЕКТИРОВКИ (ТРАВМЫ, ВРАТАРИ, xG) ---
with st.expander("⚙️ Поправки на составы, травмы, вратарей и xG"):
    c_adj1, c_adj2 = st.columns(2)
    with c_adj1:
        adj1 = st.slider(f"Коррекция силы {t1_name} (%)", -25, 25, 0, help="Учтите травмы лидеров или бекап-вратаря")
    with c_adj2:
        adj2 = st.slider(f"Коррекция силы {t2_name} (%)", -25, 25, 0)
        
    if l_code != "NHL":
        st.caption("📋 Вставьте скопированную с сайта лиги таблицу игроков (необязательно):")
        raw_p1 = st.text_area(f"Статистика игроков {t1_name} (скопируйте таблицу с сайта и вставьте сюда)", height=80)
        raw_p2 = st.text_area(f"Статистика игроков {t2_name}", height=80)
        if raw_p1.strip():
            try:
                sk1 = pd.read_csv(StringIO(raw_p1), sep="\t")
            except Exception:
                pass
        if raw_p2.strip():
            try:
                sk2 = pd.read_csv(StringIO(raw_p2), sep="\t")
            except Exception:
                pass

lambda1 = round(max(0.4, base_l1 * (1 + adj1 / 100)), 2)
lambda2 = round(max(0.4, base_l2 * (1 + adj2 / 100)), 2)

st.info(f"Итоговый расчетный xG (λ): **{t1_name}: {lambda1}** — **{t2_name}: {lambda2}**")

# --- ЗАПУСК СИМУЛЯЦИЙ ---
if st.button("🚀 Запустить 4 000 000 симуляций", use_container_width=True):
    g1, g2 = run_simulations(lambda1, lambda2)
    tot = g1 + g2
    
    tab1, tab2, tab3 = st.tabs(["📊 Исходы и Точный счет", f"📋 Состав {t1_name}", f"📋 Состав {t2_name}"])
    
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
if not gl1.empty:
st.subheader("Вратари")
st.dataframe(gl1, use_container_width=True, hide_index=True)
if not sk1.empty:
st.subheader("Полевые игроки (весь сезон)")
st.dataframe(sk1, use_container_width=True, hide_index=True)
else:
st.info("Для европейских лиг вставьте таблицу игроков с сайта лиги в меню «Поправки на составы» выше, чтобы просмотреть ее целиком здесь.")
with tab3:
if not gl2.empty:
st.subheader("Вратари")
st.dataframe(gl2, use_container_width=True, hide_index=True)
if not sk2.empty:
st.subheader("Полевые игроки (весь сезон)")
st.dataframe(sk2, use_container_width=True, hide_index=True)
else:
st.info("Для европейских лиг вставьте таблицу игроков с сайта лиги в меню «Поправки на составы» выше, чтобы просмотреть ее целиком здесь.")
