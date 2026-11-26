from html.parser import HTMLParser
import io
import re
import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Hockey Pro AI", page_icon="🏒", layout="wide")
st.title("🏒 Анализатор матчей (7 лиг • Авто-xG • 4 000 000 симуляций)")

HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}

LEAGUES = {
    "🇺🇸🇨🇦 НХЛ (NHL.com + MoneyPuck xG)": {"c": "NHL", "avg": 3.05, "hb": 1.04, "src": "NHL.com / MoneyPuck"},
    "🇷🇺 КХЛ (KHL.ru)": {"c": "KHL", "avg": 2.65, "hb": 1.05, "src": "KHL.ru", "url": "https://khl.ru"},
    "🇫🇮 Финляндия (Liiga.fi xG)": {"c": "LIIGA", "avg": 2.70, "hb": 1.05, "src": "Liiga.fi", "url": "https://liiga.fi"},
    "🇸🇪 Швеция (SHL.se)": {"c": "SHL", "avg": 2.68, "hb": 1.05, "src": "SHL.se", "url": "https://shl.se"},
    "🇨🇿 Чехия (Hokej.cz)": {"c": "ELH", "avg": 2.75, "hb": 1.06, "src": "Hokej.cz", "url": "https://hokej.cz"},
    "🇨🇭 Швейцария (SIHF.ch)": {"c": "NL", "avg": 2.85, "hb": 1.05, "src": "SIHF.ch", "url": "https://sihf.ch"},
    "🇳🇴 Норвегия (EHL / Hockey4You)": {"c": "EHL", "avg": 3.10, "hb": 1.06, "src": "EHL Official", "url": "https://hockey4you.no"},
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

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell, self.in_td = [], [], [], False
    def handle_starttag(self, tag, attrs):
        if tag == "tr": self.row = []
        elif tag in ("td", "th"): self.in_td, self.cell = True, []
    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_td:
            self.row.append(" ".join("".join(self.cell).split()))
            self.in_td = False
        elif tag == "tr" and self.row:
            self.rows.append(self.row)
    def handle_data(self, data):
        if self.in_td: self.cell.append(data)

@st.cache_data(ttl=3600)
def get_nhl_data():
    teams, xg = {}, {}
    try:
        r = requests.get("https://nhle.com", headers=HDR, timeout=10).json()
        for t in r.get("standings", []):
            a = t["teamAbbrev"]["default"]
            gp = max(1, t.get("gamesPlayed", 1))
            teams[f"{t['teamName']['default']} ({a})"] = {
                "a": a, "xgf": t.get("goalFor", 0) / gp, "xga": t.get("goalAgainst", 0) / gp, "is_xg": False
            }
    except Exception:
        pass
    for yr in ["2026", "2025"]:
        try:
            res = requests.get(f"https://moneypuck.com{yr}/regular/teams.csv", headers=HDR, timeout=10)
            if res.status_code == 200 and "xGoalsFor" in res.text:
                df = pd.read_csv(io.StringIO(res.text))
                for _, row in df[df["situation"] == "all"].iterrows():
                    gp = max(1, float(row.get("games_played", 1)))
                    xg[str(row["team"]).strip()] = (float(row["xGoalsFor"]) / gp, float(row["xGoalsAgainst"]) / gp)
                if xg: break
        except Exception:
            pass
    for k, v in teams.items():
        if v["a"] in xg:
            v["xgf"], v["xga"], v["is_xg"] = xg[v["a"]][0], xg[v["a"]][1], True
    return teams
@st.cache_data(ttl=3600)
def get_euro_data(code, url):
    stats = {}
    if code == "LIIGA":
        try:
            r = requests.get("https://liiga.fi", headers=HDR, timeout=10).json()
            rows = r if isinstance(r, list) else r.get("standings", [])
            for t in rows:
                name = t.get("teamName") or t.get("team_name") or ""
                gp = max(1, int(t.get("games", 1)))
                for tm in TEAMS["LIIGA"]:
                    if tm.lower() in name.lower():
                        stats[tm] = {"xgf": t.get("goals", 0) / gp, "xga": t.get("goalsAgainst", t.get("goals_against", 0)) / gp, "is_xg": False}
        except Exception:
            pass
    try:
        html = requests.get(url, headers=HDR, timeout=10).text
        p = TableParser()
        p.feed(html)
        for row in p.rows:
            joined = " | ".join(row).lower()
            matched = next((tm for tm in TEAMS[code] if tm.lower().replace("-", " ") in joined.replace("-", " ")), None)
            if not matched: continue
            score_cell = next((c for c in row if re.match(r"^\d+\s*[-:]\s*\d+$", c)), None)
            nums = [float(c.replace(",", ".")) for c in row if re.match(r"^\d+([.,]\d+)?$", c)]
            gp = next((n for n in nums if 5 <= n <= 75), 0)
            if score_cell and gp > 0:
                gf, ga = map(float, re.split(r"[-:]", score_cell))
                stats[matched] = {"xgf": gf / gp, "xga": ga / gp, "is_xg": False}
            elif code == "LIIGA" and len(nums) >= 12 and gp > 0:
                stats[matched] = {"xgf": nums[-2] / gp, "xga": nums[-1] / gp, "is_xg": True}
            elif len(nums) >= 7 and gp > 0:
                stats[matched] = {"xgf": nums[-3] / gp, "xga": nums[-2] / gp, "is_xg": False}
    except Exception:
        pass
    return stats

@st.cache_data(ttl=3600)
def get_nhl_roster(a):
    try:
        r = requests.get(f"https://nhle.com{a}/now", headers=HDR, timeout=10).json()
        sk = [{"Игрок": f"{s['firstName']['default']} {s['lastName']['default']}", "Поз": s.get("positionCode", "-"), "И": s.get("gamesPlayed", 0), "Г": s.get("goals", 0), "П": s.get("assists", 0), "О": s.get("points", 0)} for s in r.get("skaters", [])]
        gl = [{"Вратарь": f"{g['firstName']['default']} {g['lastName']['default']}", "И": g.get("gamesPlayed", 0), "В": g.get("wins", 0), "%ОБ": round((g.get("savePercentage") or 0) * 100, 2), "КН": round(g.get("goalsAgainstAverage", 0), 2)} for g in r.get("goalies", [])]
        return pd.DataFrame(sk), pd.DataFrame(gl)
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

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

lg_name = st.selectbox("Лига:", list(LEAGUES.keys()))
lg = LEAGUES[lg_name]
c1, c2 = st.columns(2)

live = get_nhl_data() if lg["c"] == "NHL" else get_euro_data(lg["c"], lg["url"])
names = sorted(live.keys()) if (lg["c"] == "NHL" and live) else TEAMS[lg["c"]]
h_t, a_t = c1.selectbox("🏠 Хозяева", names, 0), c2.selectbox("✈️ Гости", names, 1)

if h_t in live and a_t in live:
    l_avg = np.mean([v["xgf"] for v in live.values()]) or lg["avg"]
    hs, as_ = live[h_t], live[a_t]
    dl1 = round(l_avg * (hs["xgf"] / l_avg) * (as_["xga"] / l_avg) * lg["hb"], 2)
    dl2 = round(l_avg * (as_["xgf"] / l_avg) * (hs["xga"] / l_avg), 2)
    tag = "xGF/xGA" if hs["is_xg"] else "GF/GA"
    st.success(f"📡 {lg['src']} ({tag}): {h_t} ({hs['xgf']:.2f} / {hs['xga']:.2f}) vs {a_t} ({as_['xgf']:.2f} / {as_['xga']:.2f})")
else:
    dl1, dl2 = round(lg["avg"] * lg["hb"], 2), round(lg["avg"], 2)
    st.caption(f"ℹ️ Сайт {lg['src']} недоступен с сервера — использованы средние лиги (доступен ручной ввод).")

k1, k2 = st.columns(2)
l1 = k1.number_input(f"Ожидаемые голы (xG): {h_t}", 0.5, 8.0, float(dl1), 0.05)
l2 = k2.number_input(f"Ожидаемые голы (xG): {a_t}", 0.5, 8.0, float(dl2), 0.05)

if st.button("🚀 Запустить 4 000 000 симуляций", type="primary", use_container_width=True):
    with st.spinner("Симуляция..."):
        x, y = run_sim(l1, l2)
        tot = x + y
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
                sk, gl = get_nhl_roster(live[tm]["a"] if tm in live else tm)
                if not gl.empty: st.dataframe(gl, hide_index=True, use_container_width=True)
                if not sk.empty: st.dataframe(sk, hide_index=True, use_container_width=True)
                if gl.empty and sk.empty: st.info("Составы временно недоступны.")
