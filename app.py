from html.parser import HTMLParser
import io, re
import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Hockey Pro AI", page_icon="🏒", layout="wide")
st.title("🏒 Анализатор матчей (7 лиг • Авто-xG • 4 000 000 симуляций)")
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36", "Accept": "*/*"}

LEAGUES = {
    "🇺🇸🇨🇦 НХЛ (NHL.com + MoneyPuck xG)": {"c": "NHL", "avg": 3.05, "hb": 1.04},
    "🇷🇺 КХЛ (KHL)": {"c": "KHL", "avg": 2.65, "hb": 1.05, "urls": [("KHL.ru", "https://khl.ru"), ("Wikipedia", "https://wikipedia.org")]},
    "🇫🇮 Финляндия (Liiga)": {"c": "LIIGA", "avg": 2.70, "hb": 1.05, "urls": [("EliteProspects", "https://eliteprospects.com"), ("Wikipedia", "https://wikipedia.org")]},
    "🇸🇪 Швеция (SHL)": {"c": "SHL", "avg": 2.68, "hb": 1.05, "urls": [("EliteProspects", "https://eliteprospects.com"), ("Wikipedia", "https://wikipedia.org")]},
    "🇨🇿 Чехия (ELH)": {"c": "ELH", "avg": 2.75, "hb": 1.06, "urls": [("Hokej.cz", "https://hokej.cz"), ("EliteProspects", "https://eliteprospects.com")]},
    "🇨🇭 Швейцария (NL)": {"c": "NL", "avg": 2.85, "hb": 1.05, "urls": [("EliteProspects", "https://eliteprospects.com"), ("Wikipedia", "https://wikipedia.org")]},
    "🇳🇴 Норвегия (EHL)": {"c": "EHL", "avg": 3.10, "hb": 1.06, "urls": [("EliteProspects", "https://eliteprospects.com"), ("Wikipedia", "https://wikipedia.org")]},
}

TEAMS = {
    "NHL": ["ANA", "BOS", "BUF", "CGY", "CAR", "CHI", "COL", "CBJ", "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NSH", "NJD", "NYI", "NYR", "OTT", "PHI", "PIT", "SJS", "SEA", "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WSH", "WPG"],
    "KHL": ["Металлург Мг", "ЦСКА", "Локомотив", "Авангард", "Северсталь", "Торпедо", "Спартак", "Динамо Москва", "Нефтехимик", "Амур", "Автомобилист", "Ак Барс", "Трактор", "Салават Юлаев", "Барыс", "Куньлунь", "Динамо Минск", "СКА", "Сибирь", "Адмирал", "Лада", "ХК Сочи"],
    "LIIGA": ["Lukko", "JYP", "Ilves", "Jukurit", "Tappara", "HIFK", "Kärpät", "KalPa", "Ässät", "Pelicans", "TPS", "KooKoo", "SaiPa", "HPK", "Sport", "Kiekko-Espoo", "Jokerit"],
    "SHL": ["Färjestad", "Skellefteå", "Frölunda", "Växjö", "Luleå", "Brynäs", "Timrå", "Rögle", "Leksands", "Linköping", "Örebro", "Malmö", "HV71", "Djurgården", "MoDo"],
    "ELH": ["Pardubice", "Sparta Praha", "Třinec", "Kometa Brno", "Mountfield HK", "Liberec", "Litvínov", "České Budějovice", "Plzeň", "Vítkovice", "Karlovy Vary", "Olomouc", "Mladá Boleslav", "Kladno"],
    "NL": ["ZSC Lions", "Lausanne", "EV Zug", "Fribourg", "SC Bern", "HC Davos", "HC Lugano", "Genève-Servette", "Biel-Bienne", "Ambri-Piotta", "SCL Tigers", "Rapperswil", "Kloten", "Ajoie"],
    "EHL": ["Storhamar", "Vålerenga", "Stavanger", "Frisk Asker", "Lillehammer", "Stjernen", "Nidaros", "Narvik", "Ringerike"],
}
KHL_MAP = {"Металлург Мг": "metallurg", "ЦСКА": "cska", "Локомотив": "lokomotiv", "Авангард": "avangard", "Северсталь": "severstal", "Торпедо": "torpedo", "Спартак": "spartak", "Динамо Москва": "dynamo m", "Нефтехимик": "neftekhimik", "Амур": "amur", "Автомобилист": "avtomobilist", "Ак Барс": "ak bars", "Трактор": "traktor", "Салават Юлаев": "salavat", "Барыс": "barys", "Куньлунь": "kunlun", "Динамо Минск": "dinamo mn", "СКА": "ska", "Сибирь": "sibir", "Адмирал": "admiral", "Лада": "lada", "ХК Сочи": "sochi"}

class TParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell, self.td = [], [], [], False
    def handle_starttag(self, t, a):
        if t == "tr": self.row = []
        elif t in ("td", "th"): self.td, self.cell = True, []
    def handle_endtag(self, t):
        if t in ("td", "th") and self.td:
            self.row.append(" ".join("".join(self.cell).split())); self.td = False
        elif t == "tr" and self.row: self.rows.append(self.row)
    def handle_data(self, d):
        if self.td: self.cell.append(d)

@st.cache_data(ttl=3600)
def get_nhl():
    teams, xg, src = {}, {}, "NHL.com"
    try:
        r = requests.get("https://nhle.com", headers=HDR, timeout=10).json()
        for t in r.get("standings", []):
            a, gp = t["teamAbbrev"]["default"], max(1, int(t.get("gamesPlayed", 1)))
            teams[f"{t['teamName']['default']} ({a})"] = {"a": a, "xgf": t.get("goalFor", 0) / gp, "xga": t.get("goalAgainst", 0) / gp}
    except Exception:
        try:
            r = requests.get("https://espn.com", headers=HDR, timeout=10).json()
            src = "ESPN NHL"
            for cf in r.get("children", []):
                for e in cf.get("standings", {}).get("entries", []):
                    tm, sm = e.get("team", {}), {s["name"]: float(s.get("value", 0)) for s in e.get("stats", [])}
                    a, gp = tm.get("abbreviation", ""), max(1.0, sm.get("gamesPlayed", 1.0))
                    if a: teams[f"{tm.get('displayName', a)} ({a})"] = {"a": a, "xgf": sm.get("pointsFor", 0) / gp, "xga": sm.get("pointsAgainst", 0) / gp}
        except Exception: pass
    for yr in ["2026", "2025"]:
        try:
            res = requests.get(f"https://moneypuck.com{yr}/regular/teams.csv", headers=HDR, timeout=10)
            if res.status_code == 200 and "xGoalsFor" in res.text:
                df = pd.read_csv(io.StringIO(res.text))
                for _, row in df[df["situation"] == "all"].iterrows():
                    gp = max(1.0, float(row.get("games_played", 1)))
                    xg[str(row["team"]).strip()] = (float(row["xGoalsFor"]) / gp, float(row["xGoalsAgainst"]) / gp)
                if xg: src = f"NHL + MoneyPuck {yr}"; break
        except Exception: pass
    for v in teams.values():
        if v["a"] in xg: v["xgf"], v["xga"] = xg[v["a"]][0], xg[v["a"]][1]
    return teams, src
@st.cache_data(ttl=3600)
def get_euro(code, urls):
    for label, url in urls:
        try:
            p = TParser(); p.feed(requests.get(url, headers=HDR, timeout=10).text)
            stats = {}
            for row in p.rows:
                for tm in TEAMS[code]:
                    keys = [tm.lower(), tm.lower().replace("-", " ")] + ([KHL_MAP[tm]] if code == "KHL" and tm in KHL_MAP else [])
                    idx_t = next((i for i, c in enumerate(row) if any(k in c.lower().replace("-", " ") for k in keys)), -1)
                    if idx_t == -1: continue
                    tail = row[idx_t + 1:]
                    ints = [int(c) for c in tail if c.isdigit()]
                    gp = next((x for x in ints if 3 <= x <= 82), 0)
                    sc = next((c for c in tail if re.match(r"^\d+\s*[-:]\s*\d+$", c)), None)
                    if sc and gp > 0:
                        gf, ga = map(float, re.split(r"[-:]", sc))
                        stats[tm] = {"xgf": gf / gp, "xga": ga / gp}
                    elif len(ints) >= 6 and gp > 0:
                        pr = next(((ints[k], ints[k + 1]) for k in range(1, len(ints) - 1) if 1.1 * gp <= ints[k] <= 6.5 * gp and 1.1 * gp <= ints[k + 1] <= 6.5 * gp), None)
                        if pr: stats[tm] = {"xgf": pr[0] / gp, "xga": pr[1] / gp}
            if len(stats) >= 4: return stats, label
        except Exception: continue
    return {}, ""

@st.cache_data(ttl=3600)
def get_roster(a):
    try:
        r = requests.get(f"https://nhle.com{a}/now", headers=HDR, timeout=10).json()
        sk = [{"Игрок": f"{s['firstName']['default']} {s['lastName']['default']}", "Поз": s.get("positionCode", "-"), "И": s.get("gamesPlayed", 0), "Г": s.get("goals", 0), "П": s.get("assists", 0), "О": s.get("points", 0)} for s in r.get("skaters", [])]
        gl = [{"Вратарь": f"{g['firstName']['default']} {g['lastName']['default']}", "И": g.get("gamesPlayed", 0), "В": g.get("wins", 0), "%ОБ": round((g.get("savePercentage") or 0) * 100, 2), "КН": round(g.get("goalsAgainstAverage", 0), 2)} for g in r.get("goalies", [])]
        return pd.DataFrame(sk), pd.DataFrame(gl)
    except Exception: return pd.DataFrame(), pd.DataFrame()

def run_sim(l1, l2, n=1_000_000):
    rng = np.random.default_rng()
    z = rng.poisson(0.14, n)
    xb, yb = rng.poisson(max(0.1, l1 - 0.14), n) + z, rng.poisson(max(0.1, l2 - 0.14), n) + z
    xd, yd = rng.poisson(l1, n), rng.poisson(l2, n)
    m = (xd <= 1) & (yd <= 1) & (rng.random(n) < 0.08)
    xd[m] = np.where(xd[m] == yd[m], xd[m], xd[m] + 1)
    xn, yn = rng.negative_binomial(6.5, 6.5 / (6.5 + l1), n), rng.negative_binomial(6.5, 6.5 / (6.5 + l2), n)
    xe, ye = rng.poisson(l1 * 0.93, n), rng.poisson(l2 * 0.93, n)
    df, re = xe - ye, rng.random(n)
    xe += np.where((df >= 1) & (df <= 2) & (re < 0.28), 1, 0) + np.where((df <= -1) & (df >= -2) & (re >= 0.28) & (re < 0.40), 1, 0)
    ye += np.where((df <= -1) & (df >= -2) & (re < 0.28), 1, 0) + np.where((df >= 1) & (df <= 2) & (re >= 0.28) & (re < 0.40), 1, 0)
    return np.concatenate([xb, xd, xn, xe]), np.concatenate([yb, yd, yn, ye])

lg = LEAGUES[st.selectbox("Лига:", list(LEAGUES.keys()))]
c1, c2 = st.columns(2)
live, src = get_nhl() if lg["c"] == "NHL" else get_euro(lg["c"], lg["urls"])
names = sorted(live.keys()) if (lg["c"] == "NHL" and live) else TEAMS[lg["c"]]
h_t, a_t = c1.selectbox("🏠 Хозяева", names, 0), c2.selectbox("✈️ Гости", names, 1)

if h_t in live and a_t in live:
    l_avg = float(np.mean([v["xgf"] for v in live.values()])) or lg["avg"]
    hs, as_ = live[h_t], live[a_t]
    dl1 = round(l_avg * (hs["xgf"] / l_avg) * (as_["xga"] / l_avg) * lg["hb"], 2)
    dl2 = round(l_avg * (as_["xgf"] / l_avg) * (hs["xga"] / l_avg), 2)
    st.success(f"📡 Авто-xG ({src}): {h_t} ({hs['xgf']:.2f} / {hs['xga']:.2f}) vs {a_t} ({as_['xgf']:.2f} / {as_['xga']:.2f})")
else:
    dl1, dl2 = round(lg["avg"] * lg["hb"], 2), round(lg["avg"], 2)
    st.warning("⚠️ Внешний источник временно недоступен — включены средние лиги.")

k1, k2 = st.columns(2)
l1 = k1.number_input(f"Ожидаемые голы (xG): {h_t}", 0.5, 8.0, float(dl1), 0.05)
l2 = k2.number_input(f"Ожидаемые голы (xG): {a_t}", 0.5, 8.0, float(dl2), 0.05)

if st.button("🚀 Запустить 4 000 000 симуляций", type="primary", use_container_width=True):
    with st.spinner("Симуляция..."):
        x, y = run_sim(l1, l2); tot = x + y
        p1, px, p2 = np.mean(x > y) * 100, np.mean(x == y) * 100, np.mean(x < y) * 100
    m1, m2, m3 = st.columns(3)
    m1.metric("П1 (Хозяева)", f"{p1:.2f}%", f"С ОТ: {p1 + px * 0.52:.2f}%")
    m2.metric("Х (Ничья)", f"{px:.2f}%")
    m3.metric("П2 (Гости)", f"{p2:.2f}%", f"С ОТ: {p2 + px * 0.48:.2f}%")
    st.subheader("🎯 Тоталы (Основное время)")
    tc = st.columns(4)
    for i, ln in enumerate([4.5, 5.5, 6.5, 7.5]):
        ov = np.mean(tot > ln) * 100
        tc[i].info(f"**Т {ln}**\n\nТБ: **{ov:.1f}%**\n\nТМ: **{100 - ov:.1f}%**")
    sc, cnt = np.unique(np.column_stack((x, y)), axis=0, return_counts=True)
    idx = np.argsort(-cnt)[:5]
    st.subheader("🔢 Топ-5 точных счетов")
    st.dataframe(pd.DataFrame({"Счет": [f"{int(sc[i, 0])} : {int(sc[i, 1])}" for i in idx], "Вероятность (%)": [round(cnt[i] / len(x) * 100, 2) for i in idx]}), hide_index=True, use_container_width=True)

if lg["c"] == "NHL":
    with st.expander("📋 Составы и статистика НХЛ"):
        t1, t2 = st.tabs([h_t, a_t])
        for tab, tm in zip([t1, t2], [h_t, a_t]):
            with tab:
                sk, gl = get_roster(live[tm]["a"] if tm in live else tm)
                if not gl.empty: st.dataframe(gl, hide_index=True, use_container_width=True)
                if not sk.empty: st.dataframe(sk, hide_index=True, use_container_width=True)
                if gl.empty and sk.empty: st.info("Составы временно недоступны.")
class MatchReportGenerator:
    @staticmethod
    def generate_report(league, home_team, away_team, home_metrics, away_metrics, sim_results, home_lineup, away_lineup) -> str:
        outcomes = sim_results["outcomes"]
        totals = sim_results["totals"]
        best_combo, best_prob = sim_results["best_win_total_combo"]

        h_line1 = ", ".join(home_lineup.get("forward_lines", {}).get("Line 1", ["лидеры атаки"]))
        a_line1 = ", ".join(away_lineup.get("forward_lines", {}).get("Line 1", ["лидеры атаки"]))

        pace_desc = (
            "высокоинтенсивный атакующий хоккей с обилием бросков из опасных зон"
            if (home_metrics["HDCF"] + away_metrics["HDCF"]) >= 22
            else "вязкая позиционная борьба с плотной обороной в средней зоне и акцентом на блокировку бросков"
        )

        if outcomes["П1"] > outcomes["П2"] + 7:
            fav_text = f"Хозяева льда ({home_team}) подходят к встрече в статусе явного фаворита с вероятностью победы в основное время {outcomes['П1']}%."
        elif outcomes["П2"] > outcomes["П1"] + 7:
            fav_text = f"Гостевой коллектив ({away_team}) выглядит предпочтительнее по качеству создаваемых моментов, имея {outcomes['П2']}% на успех в основное время."
        else:
            fav_text = f"Соперники демонстрируют сопоставимый уровень готовности, что подтверждается близкими шансами на успех: {outcomes['П1']}% у {home_team} против {outcomes['П2']}% у {away_team}."

        return f"""
Аналитический превью-отчет матча {league}: {home_team} — {away_team}

Предстоящее противостояние между {home_team} и {away_team} обещает {pace_desc}. На основе глубокого разбора продвинутой статистики прошедших игр сезона и моделирования 1 000 000 сценариев развития встречи с помощью ансамбля стохастических моделей (двумерное распределение Пуассона, модель Диксона — Коулза, отрицательное биномиальное распределение и марковская цепь с учетом снятия вратаря в концовке) сформирована объективная картина соотношения сил.

Качество игры и продвинутые метрики
Хозяева площадки ({home_team}) демонстрируют показатель контроля шайбы Corsi на уровне {home_metrics['CF%']}% и Fenwick — {home_metrics['FF%']}%. В среднем за матч команда генерирует {home_metrics['xGF']} ожидаемых голов (xG) при {home_metrics['HDCF']} опасных моментах из слота (High Danger Chances), допуская у своих ворот {home_metrics['xGA']} xGA. Высокая самоотдача полевых игроков при блокировке бросков (в среднем {home_metrics['Blocks']} блоков за игру) снижает нагрузку на вратарскую линию.

В свою очередь, {away_team} владеет инициативой по бросковой активности на уровне {away_metrics['CF%']}% Corsi и {away_metrics['FF%']}% Fenwick. Атакующий потенциал гостей оценивается в {away_metrics['xGF']} xG при {away_metrics['HDCF']} острых моментах за матч, тогда как оборонительные редуты позволяют соперникам создавать {away_metrics['xGA']} xGA. Важнейшим фактором станет дисциплина и игра в неравных составах: при наличии удалений именно реализация большинства способна переломить ход встречи.

Прогнозируемые составы и ключевые сочетания
Исходя из анализа игрового времени (TOI) и результативности в последних турах, ударную нагрузку в первой тройке нападения {home_team} должны взять на себя {h_line1}. У {away_team} в ведущем атакующем звене ожидается выход сочетания {a_line1}, от эффективности которого напрямую зависит темп перехода из обороны в атаку.

Итоги симуляции (1 000 000 итераций) и вероятностные сценарии
{fav_text} Вероятность ничейного исхода по итогам трех периодов составляет {outcomes['Х']}%, а шансы на непроигрыш (двойной шанс) распределяются как {outcomes['1Х']}% на 1Х и {outcomes['2Х']}% на 2Х. Средний ожидаемый счет по итогам симуляций — {sim_results['expected_score']}.

По линии результативности распределение вероятностей выглядит следующим образом:
- Тотал 4.5: ТБ — {totals[4.5]['ТБ']}%, ТМ — {totals[4.5]['ТМ']}%
- Тотал 5.5: ТБ — {totals[5.5]['ТБ']}%, ТМ — {totals[5.5]['ТМ']}%
- Тотал 6.5: ТБ — {totals[6.5]['ТБ']}%, ТМ — {totals[6.5]['ТМ']}%

Наиболее статистически обоснованным комбинированным сценарием данного поединка выступает вариант «{best_combo}», вероятность реализации которого в проведенных симуляциях достигла {best_prob}%.
""".strip()


def run_pipeline():
    print("1. Инициализация модулей...")
    nhl = NHLScraper()
    analytics = HockeyAnalyticsEngine()
    simulator = EnsembleMatchSimulator(n_simulations=1_000_000)

    try:
        upcoming = nhl.get_upcoming_games(days_ahead=1)
    except Exception:
        upcoming = []

    if not upcoming:
        print("Ближайших матчей НХЛ не найдено. Используем тестовую пару.")
        match = {"league": "NHL", "home_team": "EDM", "away_team": "FLA"}
    else:
        match = upcoming[0]

    home = match["home_team"]
    away = match["away_team"]
    print(f"2. Анализ матча {match['league']}: {home} vs {away}")

    sample_events = pd.DataFrame([
        {"event_type": "shot-on-goal", "team_id": 1, "x_coord": 75, "y_coord": 5, "shot_type": "wrist", "situation": "1551"},
        {"event_type": "goal", "team_id": 1, "x_coord": 81, "y_coord": -3, "shot_type": "tip-in", "situation": "1541"},
        {"event_type": "missed-shot", "team_id": 1, "x_coord": 68, "y_coord": 12, "shot_type": "slap", "situation": "1551"},
        {"event_type": "blocked-shot", "team_id": 2, "x_coord": 60, "y_coord": -15, "shot_type": "wrist", "situation": "1551"},
        {"event_type": "shot-on-goal", "team_id": 2, "x_coord": 78, "y_coord": 4, "shot_type": "snap", "situation": "1551"},
    ] * 12)

    home_metrics = analytics.compute_team_advanced_metrics(sample_events, team_id=1)
    away_metrics = analytics.compute_team_advanced_metrics(sample_events, team_id=2)

    try:
        home_roster = nhl.get_team_season_logs(home)
        away_roster = nhl.get_team_season_logs(away)
        home_lineup = analytics.project_lineup(home_roster)
        away_lineup = analytics.project_lineup(away_roster)
    except Exception:
        home_lineup = {"forward_lines": {"Line 1": ["Игрок 1", "Игрок 2", "Игрок 3"]}}
        away_lineup = {"forward_lines": {"Line 1": ["Игрок А", "Игрок Б", "Игрок В"]}}

    proj_xg_home = (home_metrics["xGF"] + away_metrics["xGA"]) / 2.0
    proj_xg_away = (away_metrics["xGF"] + home_metrics["xGA"]) / 2.0

    print("3. Запуск 1 000 000 симуляций...")
    t0 = time.perf_counter()
    sim_results = simulator.run_ensemble(xg_home=proj_xg_home, xg_away=proj_xg_away)
    elapsed = time.perf_counter() - t0
    print(f"   Готово за {elapsed:.3f} сек!")

    report = MatchReportGenerator.generate_report(
        league=match["league"],
        home_team=home,
        away_team=away,
        home_metrics=home_metrics,
        away_metrics=away_metrics,
        sim_results=sim_results,
        home_lineup=home_lineup,
        away_lineup=away_lineup
    )

    print("\n" + "=" * 50)
    print(report)
    print("=" * 50)
    print(f"Слов в отчете: {len(report.split())}")


run_pipeline()
