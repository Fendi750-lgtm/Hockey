@st.cache_data(ttl=3600)
def get_euro_data(code, urls):
    for label, url in urls:
        try:
            html = requests.get(url, headers=HDR, timeout=10).text
            p = TableParser()
            p.feed(html)
            stats = {}
            for row in p.rows:
                for tm in TEAMS[code]:
                    keys = [tm.lower(), tm.lower().replace("-", " ")]
                    if code == "KHL" and tm in KHL_MAP:
                        keys.append(KHL_MAP[tm])
                    idx_t = next((i for i, c in enumerate(row) if any(k in c.lower().replace("-", " ") for k in keys)), -1)
                    if idx_t == -1:
                        continue
                    tail = row[idx_t + 1:]
                    ints = [int(c) for c in tail if c.isdigit()]
                    gp = next((x for x in ints if 3 <= x <= 82), 0)
                    sc_cell = next((c for c in tail if re.match(r"^\d+\s*[-:]\s*\d+$", c)), None)
                    if sc_cell and gp > 0:
                        gf, ga = map(float, re.split(r"[-:]", sc_cell))
                        stats[tm] = {"xgf": gf / gp, "xga": ga / gp}
                    elif len(ints) >= 6 and gp > 0:
                        pair = next(((ints[k], ints[k + 1]) for k in range(1, len(ints) - 1) if 1.1 * gp <= ints[k] <= 6.5 * gp and 1.1 * gp <= ints[k + 1] <= 6.5 * gp), None)
                        if pair:
                            stats[tm] = {"xgf": pair[0] / gp, "xga": pair[1] / gp}
            if len(stats) >= 4:
                return stats, label
        except Exception:
            continue
    return {}, ""

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

live, src = get_nhl_data() if lg["c"] == "NHL" else get_euro_data(lg["c"], lg["urls"])
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
    st.warning("⚠️ Внешний источник временно недоступен — включены средние лиги (доступен ручной ввод).")

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
@st.cache_data(ttl=3600)
def get_euro_data(code, urls):
    for label, url in urls:
        try:
            html = requests.get(url, headers=HDR, timeout=10).text
            p = TableParser()
            p.feed(html)
            stats = {}
            for row in p.rows:
                for tm in TEAMS[code]:
                    keys = [tm.lower(), tm.lower().replace("-", " ")]
                    if code == "KHL" and tm in KHL_MAP:
                        keys.append(KHL_MAP[tm])
                    idx_t = next((i for i, c in enumerate(row) if any(k in c.lower().replace("-", " ") for k in keys)), -1)
                    if idx_t == -1:
                        continue
                    tail = row[idx_t + 1:]
                    ints = [int(c) for c in tail if c.isdigit()]
                    gp = next((x for x in ints if 3 <= x <= 82), 0)
                    sc_cell = next((c for c in tail if re.match(r"^\d+\s*[-:]\s*\d+$", c)), None)
                    if sc_cell and gp > 0:
                        gf, ga = map(float, re.split(r"[-:]", sc_cell))
                        stats[tm] = {"xgf": gf / gp, "xga": ga / gp}
                    elif len(ints) >= 6 and gp > 0:
                        pair = next(((ints[k], ints[k + 1]) for k in range(1, len(ints) - 1) if 1.1 * gp <= ints[k] <= 6.5 * gp and 1.1 * gp <= ints[k + 1] <= 6.5 * gp), None)
                        if pair:
                            stats[tm] = {"xgf": pair[0] / gp, "xga": pair[1] / gp}
            if len(stats) >= 4:
                return stats, label
        except Exception:
            continue
    return {}, ""

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

live, src = get_nhl_data() if lg["c"] == "NHL" else get_euro_data(lg["c"], lg["urls"])
names = sorted(live.keys()) if (lg["c"] == "NHL" and live) else TEAMS[lg["c"]]
h_t, a_t = c1.selectbox("🏠 Хозяева", names, 0), c2.selectbox("✈️ Гости", names, 1)

if h_t in live and a_t in live:
    hs, as_ = live[h_t], live[a_t]
    h_gf = hs["xgf"][0] if isinstance(hs["xgf"], tuple) else hs["xgf"]
    h_ga = hs["xga"][1] if isinstance(hs["xga"], tuple) else hs["xga"]
    a_gf = as_["xgf"][0] if isinstance(as_["xgf"], tuple) else as_["xgf"]
    a_ga = as_["xga"][1] if isinstance(as_["xga"], tuple) else as_["xga"]
    vals = [v["xgf"][0] if isinstance(v["xgf"], tuple) else v["xgf"] for v in live.values()]
    l_avg = float(np.mean(vals)) or lg["avg"]
    dl1 = round(l_avg * (h_gf / l_avg) * (a_ga / l_avg) * lg["hb"], 2)
    dl2 = round(l_avg * (a_gf / l_avg) * (h_ga / l_avg), 2)
    st.success(f"📡 Авто-xG ({src}): {h_t} ({h_gf:.2f} / {h_ga:.2f}) vs {a_t} ({a_gf:.2f} / {a_ga:.2f})")
else:
    dl1, dl2 = round(lg["avg"] * lg["hb"], 2), round(lg["avg"], 2)
    st.warning("⚠️ Внешний источник временно недоступен — включены средние лиги (доступен ручной ввод).")

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
