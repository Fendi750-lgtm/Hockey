import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Hockey Pro AI", page_icon="🏒", layout="wide")
st.title("🏒 Анализатор матчей (7 лиг • 4 000 000 симуляций)")

LEAGUES_CONFIG = {
    "🇺🇸🇨🇦 НХЛ (Авто-API + полные составы)": {
        "code": "NHL",
        "avg": 3.05,
        "home_boost": 1.04,
    },
    "🇷🇺 КХЛ (KHL)": {"code": "KHL", "avg": 2.65, "home_boost": 1.05},
    "🇫🇮 Финляндия (Liiga)": {"code": "LIIGA", "avg": 2.70, "home_boost": 1.05},
    "🇸🇪 Швеция (SHL)": {"code": "SHL", "avg": 2.68, "home_boost": 1.05},
    "🇨🇿 Чехия (Tipsport Extraliga)": {
        "code": "ELH",
        "avg": 2.75,
        "home_boost": 1.06,
    },
    "🇨🇭 Швейцария (National League)": {
        "code": "NL",
        "avg": 2.85,
        "home_boost": 1.05,
    },
    "🇳🇴 Норвегия (EHL)": {"code": "EHL", "avg": 3.10, "home_boost": 1.06},
}

PRESET_TEAMS = {
    "KHL": [
        "Металлург Мг",
        "ЦСКА",
        "Локомотив",
        "Авангард",
        "Северсталь",
        "Торпедо",
        "Спартак",
        "Динамо Москва",
        "Нефтехимик",
        "Амур",
        "Автомобилист",
        "Ак Барс",
        "Трактор",
        "Салават Юлаев",
        "Барыс",
        "Куньлунь Ред Стар",
        "Динамо Минск",
        "СКА",
        "Сибирь",
        "Адмирал",
        "Лада",
        "ХК Сочи",
    ],
    "LIIGA": [
        "Lukko",
        "JYP",
        "Ilves",
        "Jukurit",
        "Tappara",
        "HIFK",
        "Kärpät",
        "KalPa",
        "Ässät",
        "Pelicans",
        "TPS",
        "KooKoo",
        "SaiPa",
        "HPK",
        "Sport",
        "Kiekko-Espoo",
    ],
    "SHL": [
        "Färjestad BK",
        "Skellefteå AIK",
        "Frölunda HC",
        "Växjö Lakers",
        "Luleå HF",
        "Brynäs IF",
        "Timrå IK",
        "Rögle BK",
        "Leksands IF",
        "Linköping HC",
        "Örebro HK",
        "Malmö Redhawks",
        "HV71",
        "MoDo Hockey",
    ],
    "ELH": [
        "HC Dynamo Pardubice",
        "HC Sparta Praha",
        "HC Oceláři Třinec",
        "HC Kometa Brno",
        "Mountfield HK",
        "Bílí Tygři Liberec",
        "HC Verva Litvínov",
        "HC Motor České Budějovice",
        "HC Škoda Plzeň",
        "HC Vítkovice Ridera",
        "HC Energie Karlovy Vary",
        "HC Olomouc",
        "BK Mladá Boleslav",
        "Rytíři Kladno",
    ],
    "NL": [
        "ZSC Lions",
        "Lausanne HC",
        "EV Zug",
        "HC Fribourg-Gottéron",
        "SC Bern",
        "HC Davos",
        "HC Lugano",
        "Genève-Servette HC",
        "EHC Biel-Bienne",
        "HC Ambri-Piotta",
        "SCL Tigers",
        "SC Rapperswil-Jona Lakers",
        "EHC Kloten",
        "HC Ajoie",
    ],
    "EHL": [
        "Storhamar",
        "Vålerenga",
        "Stavanger Oilers",
        "Frisk Asker",
        "Sparta Sarpsborg",
        "Lillehammer",
        "Stjernen",
        "Lørenskog",
        "Comet",
        "Nidaros",
    ],
}


@st.cache_data(ttl=3600)
def get_nhl_teams():
    try:
        url = "https://nhle.com"
        res = requests.get(url, timeout=10).json()
        teams = {}
        for t in res.get("standings", []):
            abbrev = t["teamAbbrev"]["default"]
            name = t["teamName"]["default"]
            teams[f"{name} ({abbrev})"] = {
                "abbrev": abbrev,
                "gp": max(1, t.get("gamesPlayed", 1)),
                "gf": t.get("goalFor", 0),
                "ga": t.get("goalAgainst", 0),
                "home_gf": t.get("homeGoalsFor", 0),
                "home_ga": t.get("homeGoalsAgainst", 0),
                "home_gp": max(1, t.get("homeGamesPlayed", 1)),
                "road_gf": t.get("roadGoalsFor", 0),
                "road_ga": t.get("roadGoalsAgainst", 0),
                "road_gp": max(1, t.get("roadGamesPlayed", 1)),
            }
        return teams
    except Exception as e:
        st.error(f"Ошибка загрузки данных NHL API: {e}")
        return {}


@st.cache_data(ttl=3600)
def get_nhl_roster(abbrev):
    try:
        url = f"https://nhle.com{abbrev}/now"
        res = requests.get(url, timeout=10).json()
        skaters = []
        for s in res.get("skaters", []):
            skaters.append({
                "Игрок": f"{s['firstName']['default']} {s['lastName']['default']}",
                "Поз.": s.get("positionCode", "-"),
                "Игры": s.get("gamesPlayed", 0),
                "Голы": s.get("goals", 0),
                "Пасы": s.get("assists", 0),
                "Очки": s.get("points", 0),
                "+/-": s.get("plusMinus", 0),
                "Броски": s.get("shots", 0),
                "Штр": s.get("penaltyMinutes", 0),
            })
        goalies = []
        for g in res.get("goalies", []):
            save_pct = g.get("savePercentage", 0)
            goalies.append({
                "Вратарь": f"{g['firstName']['default']} {g['lastName']['default']}",
                "Игры": g.get("gamesPlayed", 0),
                "Победы": g.get("wins", 0),
                "% ОБ": round(save_pct * 100, 2) if save_pct else 0.0,
                "КН (GAA)": round(g.get("goalsAgainstAverage", 0), 2),
                "Сухари": g.get("shutouts", 0),
            })
        return pd.DataFrame(skaters), pd.DataFrame(goalies)
    except Exception as e:
        st.warning(f"Не удалось загрузить состав {abbrev}: {e}")
        return pd.DataFrame(), pd.DataFrame()
        def run_simulations(l1, l2, n=1_000_000):
    rng = np.random.default_rng()

    # 1. Bivariate Poisson
    cov = 0.14
    z = rng.poisson(cov, n)
    x_bp = rng.poisson(max(0.1, l1 - cov), n) + z
    y_bp = rng.poisson(max(0.1, l2 - cov), n) + z

    # 2. Dixon-Coles
    x_dc = rng.poisson(l1, n)
    y_dc = rng.poisson(l2, n)
    mask_low = (x_dc <= 1) & (y_dc <= 1) & (rng.random(n) < 0.08)
    x_dc[mask_low] = np.where(
        x_dc[mask_low] == y_dc[mask_low], x_dc[mask_low], x_dc[mask_low] + 1
    )

    # 3. Negative Binomial
    r = 6.5
    x_nb = rng.negative_binomial(r, r / (r + l1), n)
    y_nb = rng.negative_binomial(r, r / (r + l2), n)

    # 4. Empty Net Model
    x_en = rng.poisson(l1 * 0.93, n)
    y_en = rng.poisson(l2 * 0.93, n)
    diff = x_en - y_en
    r_en = rng.random(n)

    x_en += np.where((diff >= 1) & (diff <= 2) & (r_en < 0.28), 1, 0)
    y_en += np.where(
        (diff >= 1) & (diff <= 2) & (r_en >= 0.28) & (r_en < 0.40), 1, 0
    )

    y_en += np.where((diff <= -1) & (diff >= -2) & (r_en < 0.28), 1, 0)
    x_en += np.where(
        (diff <= -1) & (diff >= -2) & (r_en >= 0.28) & (r_en < 0.40), 1, 0
    )

    total_x = np.concatenate([x_bp, x_dc, x_nb, x_en])
    total_y = np.concatenate([y_bp, y_dc, y_nb, y_en])
    return total_x, total_y


# --- ИНТЕРФЕЙС STREAMLIT ---
selected_league_name = st.selectbox(
    "Выберите лигу:", list(LEAGUES_CONFIG.keys())
)
league_info = LEAGUES_CONFIG[selected_league_name]
league_code = league_info["code"]

col1, col2 = st.columns(2)

if league_code == "NHL":
    nhl_teams = get_nhl_teams()
    team_names = sorted(list(nhl_teams.keys()))
    if not team_names:
        st.stop()

    with col1:
        home_team = st.selectbox("🏠 Хозяева", team_names, index=0)
    with col2:
        away_team = st.selectbox(
            "✈️ Гости", team_names, index=min(1, len(team_names) - 1)
        )

    h_stats = nhl_teams[home_team]
    a_stats = nhl_teams[away_team]

    avg_goals = league_info["avg"]
    h_att = (h_stats["home_gf"] / h_stats["home_gp"]) / avg_goals
    h_def = (h_stats["home_ga"] / h_stats["home_gp"]) / avg_goals
    a_att = (a_stats["road_gf"] / a_stats["road_gp"]) / avg_goals
    a_def = (a_stats["road_ga"] / a_stats["road_gp"]) / avg_goals

    default_l1 = round(
        avg_goals * h_att * a_def * league_info["home_boost"], 2
    )
    default_l2 = round(avg_goals * a_att * h_def, 2)
else:
    teams_list = PRESET_TEAMS[league_code]
    with col1:
        home_team = st.selectbox("🏠 Хозяева", teams_list, index=0)
    with col2:
        away_team = st.selectbox("✈️ Гости", teams_list, index=1)

    default_l1 = round(league_info["avg"] * league_info["home_boost"], 2)
    default_l2 = round(league_info["avg"], 2)

st.markdown("### ⚙️ Параметры ожидаемых голов (λ)")
c1, c2 = st.columns(2)
with c1:
    l1 = st.number_input(
        f"Ожидаемые голы: {home_team}",
        min_value=0.5,
        max_value=8.0,
        value=float(default_l1),
        step=0.05,
    )
with c2:
    l2 = st.number_input(
        f"Ожидаемые голы: {away_team}",
        min_value=0.5,
        max_value=8.0,
        value=float(default_l2),
        step=0.05,
    )

if st.button(
    "🚀 Запустить 4 000 000 симуляций", type="primary", use_container_width=True
):
    with st.spinner("Выполняется расчет 4 ансамблей моделей..."):
        x, y = run_simulations(l1, l2, n=1_000_000)
        tot = x + y

        p1 = np.mean(x > y) * 100
        px = np.mean(x == y) * 100
        p2 = np.mean(x < y) * 100

        p1_ot = p1 + px * 0.52
        p2_ot = p2 + px * 0.48

        st.subheader("📊 Результаты моделирования (Основное время)")
        m1, m2, m3 = st.columns(3)
        m1.metric("П1 (Хозяева)", f"{p1:.2f}%", f"С учетом ОТ: {p1_ot:.2f}%")
        m2.metric("Х (Ничья)", f"{px:.2f}%")
        m3.metric("П2 (Гости)", f"{p2:.2f}%", f"С учетом ОТ: {p2_ot:.2f}%")

        st.subheader("🎯 Вероятности тоталов (Основное время)")
        t_cols = st.columns(4)
        for idx, line in enumerate([4.5, 5.5, 6.5, 7.5]):
            over = np.mean(tot > line) * 100
            under = 100 - over
            t_cols[idx].info(
                f"**Тотал {line}**\n\nТБ: **{over:.1f}%**\n\nТМ: **{under:.1f}%**"
            )

        scores, counts = np.unique(
            np.column_stack((x, y)), axis=0, return_counts=True
        )
        top_idx = np.argsort(-counts)[:5]
        st.subheader("🔢 Топ-5 наиболее вероятных счетов")
        score_df = pd.DataFrame({
            "Счет (Хозяева : Гости)": [
                f"{scores[i][0]} : {scores[i][1]}" for i in top_idx
            ],
            "Вероятность (%)": [
                round(counts[i] / len(x) * 100, 2) for i in top_idx
            ],
        })
        st.dataframe(score_df, hide_index=True, use_container_width=True)

if league_code == "NHL":
    with st.expander("📋 Посмотреть актуальные составы и статистику игроков НХЛ"):
        tab1, tab2 = st.tabs([home_team, away_team])
        with tab1:
            sk1, gl1 = get_nhl_roster(nhl_teams[home_team]["abbrev"])
            st.write("**Вратари**")
            st.dataframe(gl1, hide_index=True, use_container_width=True)
            st.write("**Полевые игроки**")
            st.dataframe(sk1, hide_index=True, use_container_width=True)
        with tab2:
            sk2, gl2 = get_nhl_roster(nhl_teams[away_team]["abbrev"])
            st.write("**Вратари**")
            st.dataframe(gl2, hide_index=True, use_container_width=True)
            st.write("**Полевые игроки**")
            st.dataframe(sk2, hide_index=True, use_container_width=True)
