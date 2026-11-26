import io
import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Hockey Pro AI", page_icon="🏒", layout="wide")
st.title("🏒 Анализатор матчей (7 лиг • Авто-xG • 4 000 000 симуляций)")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

LEAGUES = {
    "🇺🇸🇨🇦 НХЛ (Авто-API + реальный xG)": {"c": "NHL", "avg": 3.05, "hb": 1.04},
    "🇷🇺 КХЛ (KHL)": {"c": "KHL", "avg": 2.65, "hb": 1.05},
    "🇫🇮 Финляндия (Liiga)": {"c": "LIIGA", "avg": 2.70, "hb": 1.05},
    "🇸🇪 Швеция (SHL)": {"c": "SHL", "avg": 2.68, "hb": 1.05},
    "🇨🇿 Чехия (ELH)": {"c": "ELH", "avg": 2.75, "hb": 1.06},
    "🇨🇭 Швейцария (NL)": {"c": "NL", "avg": 2.85, "hb": 1.05},
    "🇳🇴 Норвегия (EHL)": {"c": "EHL", "avg": 3.10, "hb": 1.06},
}

TEAMS = {
    "NHL": [
        "ANA", "BOS", "BUF", "CGY", "CAR", "CHI", "COL", "CBJ", "DAL", "DET",
        "EDM", "FLA", "LAK", "MIN", "MTL", "NSH", "NJD", "NYI", "NYR", "OTT",
        "PHI", "PIT", "SJS", "SEA", "STL", "TBL", "TOR", "UTA", "VAN", "VGK",
        "WSH", "WPG",
    ],
    "KHL": [
        "Металлург Мг", "ЦСКА", "Локомотив", "Авангард", "Северсталь", "Торпедо",
        "Спартак", "Динамо Москва", "Нефтехимик", "Амур", "Автомобилист",
        "Ак Барс", "Трактор", "Салават Юлаев", "Барыс", "Куньлунь",
        "Динамо Минск", "СКА", "Сибирь", "Адмирал", "Лада", "ХК Сочи",
    ],
    "LIIGA": [
        "Lukko", "JYP", "Ilves", "Jukurit", "Tappara", "HIFK", "Kärpät", "KalPa",
        "Ässät", "Pelicans", "TPS", "KooKoo", "SaiPa", "HPK", "Sport", "Kiekko-Espoo",
    ],
    "SHL": [
        "Färjestad", "Skellefteå", "Frölunda", "Växjö", "Luleå", "Brynäs",
        "Timrå", "Rögle", "Leksands", "Linköping", "Örebro", "Malmö", "HV71", "MoDo",
    ],
    "ELH": [
        "Pardubice", "Sparta Praha", "Třinec", "Kometa Brno", "Mountfield HK",
        "Liberec", "Litvínov", "České Budějovice", "Plzeň", "Vítkovice",
        "Karlovy Vary", "Olomouc", "Mladá Boleslav", "Kladno",
    ],
    "NL": [
        "ZSC Lions", "Lausanne", "EV Zug", "Fribourg", "SC Bern", "HC Davos",
        "HC Lugano", "Genève-Servette", "Biel-Bienne", "Ambri-Piotta",
        "SCL Tigers", "Rapperswil", "Kloten", "Ajoie",
    ],
    "EHL": [
        "Storhamar", "Vålerenga", "Stavanger", "Frisk Asker", "Sparta Sarpsborg",
        "Lillehammer", "Stjernen", "Lørenskog", "Comet", "Nidaros",
    ],
}


@st.cache_data(ttl=3600)
def get_nhl_xg():
    """Загружает реальные xGF и xGA команд НХЛ с MoneyPuck (все ситуации)."""
    urls = [
        "https://moneypuck.com",
        "https://moneypuck.com",
    ]
    for url in urls:
        try:
            res = requests.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=10)
            if res.status_code == 200 and "xGoalsFor" in res.text:
                df = pd.read_csv(io.StringIO(res.text))
                df = df[df["situation"] == "all"]
                xg_map = {}
                for _, row in df.iterrows():
                    gp = max(1, float(row.get("games_played", 1)))
                    abbr = str(row.get("team", "")).strip()
                    xg_map[abbr] = {
                        "xgf_pg": float(row.get("xGoalsFor", 0)) / gp,
                        "xga_pg": float(row.get("xGoalsAgainst", 0)) / gp,
                    }
                if xg_map:
                    return xg_map
        except Exception:
            continue
    return {}


@st.cache_data(ttl=3600)
def get_nhl_teams():
    try:
        res = requests.get(
            "https://nhle.com",
            headers=HEADERS,
            timeout=10,
        )
        res.raise_for_status()
        r = res.json()
        return {
            f"{t['teamName']['default']} ({t['teamAbbrev']['default']})": {
                "a": t["teamAbbrev"]["default"],
                "hgf": t.get("homeGoalsFor", 0),
                "hga": t.get("homeGoalsAgainst", 0),
                "hgp": max(1, t.get("homeGamesPlayed", 1)),
                "rgf": t.get("roadGoalsFor", 0),
                "rga": t.get("roadGoalsAgainst", 0),
                "rgp": max(1, t.get("roadGamesPlayed", 1)),
            }
            for t in r.get("standings", [])
        }
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def get_nhl_roster(a):
    try:
        res = requests.get(
            f"https://nhle.com{a}/now",
            headers=HEADERS,
            timeout=10,
        )
        res.raise_for_status()
        r = res.json()
        sk = [
            {
                "Игрок": f"{s['firstName']['default']} {s['lastName']['default']}",
                "Поз": s.get("positionCode", "-"),
                "И": s.get("gamesPlayed", 0),
                "Г": s.get("goals", 0),
                "П": s.get("assists", 0),
                "О": s.get("points", 0),
                "+/-": s.get("plusMinus", 0),
            }
            for s in r.get("skaters", [])
        ]
        gl = [
            {
                "Вратарь": f"{g['firstName']['default']} {g['lastName']['default']}",
                "И": g.get("gamesPlayed", 0),
                "В": g.get("wins", 0),
                "%ОБ": round((g.get("savePercentage") or 0) * 100, 2),
                "КН": round(g.get("goalsAgainstAverage", 0), 2),
            }
            for g in r.get("goalies", [])
        ]
        return pd.DataFrame(sk), pd.DataFrame(gl)
    except Exception:
        return pd.DataFrame(), pd.DataFrame()


def run_sim(l1, l2, n=1_000_000):
    rng = np.random.default_rng()
    z = rng.poisson(0.14, n)
    xb, yb = (
        rng.poisson(max(0.1, l1 - 0.14), n) + z,
        rng.poisson(max(0.1, l2 - 0.14), n) + z,
    )
    xd, yd = rng.poisson(l1, n), rng.poisson(l2, n)
    m = (xd <= 1) & (yd <= 1) & (rng.random(n) < 0.08)
    xd[m] = np.where(xd[m] == yd[m], xd[m], xd[m] + 1)
    xn = rng.negative_binomial(6.5, 6.5 / (6.5 + l1), n)
    yn = rng.negative_binomial(6.5, 6.5 / (6.5 + l2), n)
    xe, ye = rng.poisson(l1 * 0.93, n), rng.poisson(l2 * 0.93, n)
    df, re = xe - ye, rng.random(n)
    xe += np.where((df >= 1) & (df <= 2) & (re < 0.28), 1, 0) + np.where(
        (df <= -1) & (df >= -2) & (re >= 0.28) & (re < 0.40), 1, 0
    )
    ye += np.where((df <= -1) & (df >= -2) & (re < 0.28), 1, 0) + np.where(
        (df >= 1) & (df <= 2) & (re >= 0.28) & (re < 0.40), 1, 0
    )
    return np.concatenate([xb, xd, xn, xe]), np.concatenate([yb, yd, yn, ye])


lg_name = st.selectbox("Лига:", list(LEAGUES.keys()))
lg = LEAGUES[lg_name]
c1, c2 = st.columns(2)

nhl = get_nhl_teams() if lg["c"] == "NHL" else {}
xg_data = get_nhl_xg() if lg["c"] == "NHL" else {}

if lg["c"] == "NHL" and nhl:
    names = sorted(nhl.keys())
    h_t = c1.selectbox("🏠 Хозяева", names, 0)
    a_t = c2.selectbox("✈️ Гости", names, 1)
    hs, as_ = nhl[h_t], nhl[a_t]
    h_abbr, a_abbr = hs["a"], as_["a"]
    avg = lg["avg"]

    # Считаем xG на основе реальных xGF/xGA, если они загружены с MoneyPuck
    if h_abbr in xg_data and a_abbr in xg_data:
        league_xg = np.mean([v["xgf_pg"] for v in xg_data.values()]) or avg
        h_att = xg_data[h_abbr]["xgf_pg"] / league_xg
        h_def = xg_data[h_abbr]["xga_pg"] / league_xg
        a_att = xg_data[a_abbr]["xgf_pg"] / league_xg
        a_def = xg_data[a_abbr]["xga_pg"] / league_xg

        dl1 = round(league_xg * h_att * a_def * lg["hb"], 2)
        dl2 = round(league_xg * a_att * h_def, 2)
        st.caption(
            f"📊 Авто-xG (MoneyPuck): {h_abbr} ({xg_data[h_abbr]['xgf_pg']:.2f} xGF / "
            f"{xg_data[h_abbr]['xga_pg']:.2f} xGA) vs {a_abbr} ({xg_data[a_abbr]['xgf_pg']:.2f} xGF / "
            f"{xg_data[a_abbr]['xga_pg']:.2f} xGA)"
        )
    else:
        dl1 = round(
            avg * ((hs["hgf"] / hs["hgp"]) / avg) * ((as_["rga"] / as_["rgp"]) / avg) * lg["hb"],
            2,
        )
        dl2 = round(
            avg * ((as_["rgf"] / as_["rgp"]) / avg) * ((hs["hga"] / hs["hgp"]) / avg),
            2,
        )
        st.caption("📊 Авто-xG рассчитан по средним забитым/пропущенным голам из API НХЛ.")
else:
    if lg["c"] == "NHL":
        st.warning("API НХЛ временно недоступен — включен базовый расчет.")
    tl = TEAMS[lg["c"]]
    h_t = c1.selectbox("🏠 Хозяева", tl, 0)
    a_t = c2.selectbox("✈️ Гости", tl, 1)
    dl1, dl2 = round(lg["avg"] * lg["hb"], 2), round(lg["avg"], 2)

# Боковая панель: автокалькулятор xG по броскам и % реализации (для КХЛ и др. лиг)
with st.sidebar:
    st.header("🧮 Калькулятор xG по броскам")
    use_shot_model = st.checkbox("Пересчитать xG по броскам в створ (SOG)")
    if use_shot_model:
        sog1 = st.number_input(f"Броски в створ: {h_t}", 15.0, 45.0, 30.0, 0.5)
        sh1 = st.number_input(f"Реализация бросков {h_t} (%)", 4.0, 18.0, 9.5, 0.5)
        sog2 = st.number_input(f"Броски в створ: {a_t}", 15.0, 45.0, 28.0, 0.5)
        sh2 = st.number_input(f"Реализация бросков {a_t} (%)", 4.0, 18.0, 9.0, 0.5)
        dl1 = round((sog1 * (sh1 / 100.0)) * lg["hb"], 2)
        dl2 = round(sog2 * (sh2 / 100.0), 2)

k1, k2 = st.columns(2)
l1 = k1.number_input(f"Ожидаемые голы (xG): {h_t}", 0.5, 8.0, float(dl1), 0.05)
l2 = k2.number_input(f"Ожидаемые голы (xG): {a_t}", 0.5, 8.0, float(dl2), 0.05)

if st.button("🚀 Запустить 4 000 000 симуляций", type="primary", use_container_width=True):
    with st.spinner("Симуляция..."):
        x, y = run_sim(l1, l2)
        tot = x + y
        p1, px, p2 = (
            np.mean(x > y) * 100,
            np.mean(x == y) * 100,
            np.mean(x < y) * 100,
        )

    m1, m2, m3 = st.columns(3)
    m1.metric("П1 (Хозяева)", f"{p1:.2f}%", f"С ОТ: {p1 + px * 0.52:.2f}%")
m2.metric("Х (Ничья)", f"{px:.2f}%")
m3.metric("П2 (Гости)", f"{p2:.2f}%", f"С ОТ: {p2 + px * 0.48:.2f}%")
st.subheader("🎯 Тоталы (Основное время)")
tc = st.columns(4)
for i, ln in enumerate([4.5, 5.5, 6.5, 7.5]):
ov = np.mean(tot > ln) * 100
tc[i].info(f"Т {ln}\n\nТБ: {ov:.1f}%\n\nТМ: {100 - ov:.1f}%")
sc, cnt = np.unique(np.column_stack((x, y)), axis=0, return_counts=True)
idx = np.argsort(-cnt)[:5]
st.subheader("🔢 Топ-5 точных счетов")
st.dataframe(
pd.DataFrame(
{
"Счет": [f"{int(sc[i])} : {int(sc[i])}" for i in idx],
"Вероятность (%)": [round(cnt[i] / len(x) * 100, 2) for i in idx],
}
),
hide_index=True,
use_container_width=True,
)
if lg["c"] == "NHL":
with st.expander("📋 Составы и статистика НХЛ"):
t1, t2 = st.tabs([h_t, a_t])
for tab, tm in zip([t1, t2], [h_t, a_t]):
with tab:
abbr = nhl[tm]["a"] if nhl else tm
sk, gl = get_nhl_roster(abbr)
if not gl.empty:
st.dataframe(gl, hide_index=True, use_container_width=True)
if not sk.empty:
st.dataframe(sk, hide_index=True, use_container_width=True)
if gl.empty and sk.empty:
st.info("Составы временно недоступны.")
lg_name = st.selectbox("Лига:", list(LEAGUES.keys()))
lg = LEAGUES[lg_name]
c1, c2 = st.columns(2)

nhl = get_nhl_teams() if lg["c"] == "NHL" else {}
xg_data = get_nhl_xg() if lg["c"] == "NHL" else {}

if lg["c"] == "NHL" and nhl:
    names = sorted(nhl.keys())
    h_t = c1.selectbox("🏠 Хозяева", names, 0)
    a_t = c2.selectbox("✈️ Гости", names, 1)
    hs, as_ = nhl[h_t], nhl[a_t]
    h_abbr, a_abbr = hs["a"], as_["a"]
    avg = lg["avg"]

    if h_abbr in xg_data and a_abbr in xg_data:
        l_xg = np.mean([v["xgf_pg"] for v in xg_data.values()]) or avg
        dl1 = round(l_xg * (xg_data[h_abbr]["xgf_pg"] / l_xg) * (xg_data[a_abbr]["xga_pg"] / l_xg) * lg["hb"], 2)
        dl2 = round(l_xg * (xg_data[a_abbr]["xgf_pg"] / l_xg) * (xg_data[h_abbr]["xga_pg"] / l_xg), 2)
        st.caption(f"📊 Авто-xG (MoneyPuck): {h_abbr} ({xg_data[h_abbr]['xgf_pg']:.2f} xGF / {xg_data[h_abbr]['xga_pg']:.2f} xGA) vs {a_abbr} ({xg_data[a_abbr]['xgf_pg']:.2f} xGF / {xg_data[a_abbr]['xga_pg']:.2f} xGA)")
    else:
        dl1 = round(avg * ((hs["hgf"] / hs["hgp"]) / avg) * ((as_["rga"] / as_["rgp"]) / avg) * lg["hb"], 2)
        dl2 = round(avg * ((as_["rgf"] / as_["rgp"]) / avg) * ((hs["hga"] / hs["hgp"]) / avg), 2)
        st.caption("📊 Авто-xG рассчитан по средним забитым/пропущенным голам из API НХЛ.")
else:
    if lg["c"] == "NHL":
        st.warning("API НХЛ временно недоступен — включен базовый расчет.")
    tl = TEAMS[lg["c"]]
    h_t = c1.selectbox("🏠 Хозяева", tl, 0)
    a_t = c2.selectbox("✈️ Гости", tl, 1)
    dl1, dl2 = round(lg["avg"] * lg["hb"], 2), round(lg["avg"], 2)

with st.sidebar:
    st.header("🧮 Калькулятор xG по броскам")
    if st.checkbox("Пересчитать xG по броскам в створ (SOG)"):
        sog1 = st.number_input(f"Броски в створ: {h_t}", 15.0, 45.0, 30.0, 0.5)
        sh1 = st.number_input(f"Реализация {h_t} (%)", 4.0, 18.0, 9.5, 0.5)
        sog2 = st.number_input(f"Броски в створ: {a_t}", 15.0, 45.0, 28.0, 0.5)
        sh2 = st.number_input(f"Реализация {a_t} (%)", 4.0, 18.0, 9.0, 0.5)
        dl1 = round((sog1 * (sh1 / 100.0)) * lg["hb"], 2)
        dl2 = round(sog2 * (sh2 / 100.0), 2)

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
    st.dataframe(
        pd.DataFrame({
            "Счет": [f"{int(sc[i, 0])} : {int(sc[i, 1])}" for i in idx],
            "Вероятность (%)": [round(cnt[i] / len(x) * 100, 2) for i in idx],
        }),
        hide_index=True,
        use_container_width=True,
    )

if lg["c"] == "NHL":
    with st.expander("📋 Составы и статистика НХЛ"):
        t1, t2 = st.tabs([h_t, a_t])
        for tab, tm in zip([t1, t2], [h_t, a_t]):
            with tab:
                sk, gl = get_nhl_roster(nhl[tm]["a"] if nhl else tm)
                if not gl.empty:
                    st.dataframe(gl, hide_index=True, use_container_width=True)
                if not sk.empty:
                    st.dataframe(sk, hide_index=True, use_container_width=True)
                if gl.empty and sk.empty:
                    st.info("Составы временно недоступны.")
