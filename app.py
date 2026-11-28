import streamlit as st
import pandas as pd
from leagues_api import get_league_data, fetch_last_10_protocols
from sim_core import HockeyMatchSimulator

st.set_page_config(page_title="Hockey AI & Monte Carlo", page_icon="🏒", layout="centered")

@st.cache_data(ttl=1800)
def cached_league(code: str):
    return get_league_data(code)

@st.cache_data(ttl=1800)
def cached_protocols(code: str, key: str, stat: dict):
    return fetch_last_10_protocols(code, key, stat)

st.title("🏒 Хоккейный Анализатор (500K)")

LEAGUE_MAP = {
    "NHL (НХЛ)": "NHL", "KHL (КХЛ)": "KHL", "Liiga (Финляндия)": "Liiga",
    "Extraliga (Чехия)": "Extraliga", "DEL (Германия)": "DEL",
    "SHL (Швеция)": "SHL", "NL (Швейцария)": "NL", "EHL (Норвегия)": "EHL"
}

sel_label = st.selectbox("Выберите лигу:", list(LEAGUE_MAP.keys()))
code = LEAGUE_MAP[sel_label]
matches, team_stats = cached_league(code)

h_key, a_key = None, None
h_def = {"name": "Хозяева", "xg_per60": 3.00, "xga_per60": 2.65, "hdcf_pct": 51.5, "pp_pct": 21.5, "pk_pct": 80.5, "goalie_gsax_per60": 0.08}
a_def = {"name": "Гости", "xg_per60": 2.80, "xga_per60": 2.80, "hdcf_pct": 49.0, "pp_pct": 19.5, "pk_pct": 79.0, "goalie_gsax_per60": 0.00}

if matches:
    sel_m = st.selectbox("📅 Предстоящие матчи:", [m["label"] for m in matches])
    m_obj = next(m for m in matches if m["label"] == sel_m)
    h_key, a_key = m_obj["home"], m_obj["away"]
    h_def, a_def = team_stats.get(h_key, h_def), team_stats.get(a_key, a_def)
elif team_stats:
    teams = sorted(list(team_stats.keys()))
    c1, c2 = st.columns(2)
    h_key = c1.selectbox("Команда хозяев:", teams, index=0)
    a_key = c2.selectbox("Команда гостей:", teams, index=min(1, len(teams) - 1))
    h_def, a_def = team_stats[h_key], team_stats[a_key]

h_adv = cached_protocols(code, h_key or h_def["name"], h_def)
a_adv = cached_protocols(code, a_key or a_def["name"], a_def)

st.markdown(f"### 🆚 {h_def['name']} — {a_def['name']}")

# Блок поправок на усталость (B2B), травмы и вратарей
with st.expander("⚙️ Поправки на состав, вратарей и бэк-ту-бэк", expanded=True):
    fc1, fc2 = st.columns(2)
    with fc1:
        st.markdown(f"**{h_def['name']}**")
        h_b2b = st.checkbox("Бэк-ту-бэк (2-й матч за 2 дня)", key="hb2b")
        h_backup = st.checkbox("Запасной вратарь (бэкап)", key="hbk")
        h_inj = st.number_input("Травмировано лидеров (топ-6/топ-4)", 0, 5, 0, key="hinj")
    with fc2:
        st.markdown(f"**{a_def['name']}**")
        a_b2b = st.checkbox("Бэк-ту-бэк (2-й матч за 2 дня)", key="ab2b")
        a_backup = st.checkbox("Запасной вратарь (бэкап)", key="abk")
        a_inj = st.number_input("Травмировано лидеров (топ-6/топ-4)", 0, 5, 0, key="ainj")

with st.expander("📊 Автозагруженные метрики команд"):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**{h_def['name']}**")
        st.write(f"• xG/60: **{h_def['xg_per60']}** | xGA/60: **{h_def['xga_per60']}**")
        st.write(f"• Corsi: **{h_adv['corsi_pct']}%** | Fenwick: **{h_adv['fenwick_pct']}%**")
        st.write(f"• HDCF%: **{h_def['hdcf_pct']}%** | PP/PK: **{h_def['pp_pct']}%/{h_def['pk_pct']}%**")
        st.write(f"• Вратарь GSAx/60: **{h_def['goalie_gsax_per60']:+.2f}**")
    with c2:
        st.markdown(f"**{a_def['name']}**")
        st.write(f"• xG/60: **{a_def['xg_per60']}** | xGA/60: **{a_def['xga_per60']}**")
        st.write(f"• Corsi: **{a_adv['corsi_pct']}%** | Fenwick: **{a_adv['fenwick_pct']}%**")
        st.write(f"• HDCF%: **{a_def['hdcf_pct']}%** | PP/PK: **{a_def['pp_pct']}%/{a_def['pk_pct']}%**")
        st.write(f"• Вратарь GSAx/60: **{a_def['goalie_gsax_per60']:+.2f}**")

# Кнопка расчета сохраняет результат в session_state, чтобы калькулятор Value не сбрасывал экран
if st.button("🚀 Рассчитать матч (Ансамбль 500 000 симуляций)", use_container_width=True):
    adj = {
        "h_b2b": h_b2b, "a_b2b": a_b2b,
        "h_backup_goalie": h_backup, "a_backup_goalie": a_backup,
        "h_injuries": h_inj, "a_injuries": a_inj
    }
    st.session_state["sim_res"] = HockeyMatchSimulator(n_sims=500_000).run_ensemble(h_def, a_def, adj)
    st.session_state["sim_teams"] = (h_def["name"], a_def["name"])

if "sim_res" in st.session_state:
    res = st.session_state["sim_res"]
    hn, an = st.session_state["sim_teams"]
    l1, l2 = res["lambdas"]
    m = res["markets"]

    st.success(f"Ожидаемые голы с учётом факторов: **{hn} (λ₁ = {l1})** — **{an} (λ₂ = {l2})**")

    # 1. Ключевые факторы
    st.subheader("1. Ключевые факторы матча")
    factors_notes = []
    if h_b2b or a_b2b:
        factors_notes.append(f"Усталость B2B: {hn if h_b2b else ''} {an if a_b2b else ''}".strip())
    if h_backup or a_backup:
        factors_notes.append(f"Бэкап в воротах: {hn if h_backup else ''} {an if a_backup else ''}".strip())
    if h_inj > 0 or a_inj > 0:
        factors_notes.append(f"Потери лидеров: {hn} (-{h_inj}), {an} (-{a_inj})")
    extra_note = f"\n\n**• Активные поправки:** {'; '.join(factors_notes)}" if factors_notes else ""

    st.info(
        f"**• xG и моменты:** {hn} ({h_def['xg_per60']} xG, {h_def['hdcf_pct']}% HDCF) vs {an} ({a_def['xg_per60']} xG, {a_def['hdcf_pct']}% HDCF)\n\n"
        f"**• Владение (10 протоколов):** {h_adv['corsi_pct']}% CF / {h_adv['fenwick_pct']}% FF vs {a_adv['corsi_pct']}% CF / {a_adv['fenwick_pct']}% FF\n\n"
        f"**• Вратари GSAx/60:** {h_def['goalie_gsax_per60']:+.2f} vs {a_def['goalie_gsax_per60']:+.2f}{extra_note}"
    )

    if h_adv and h_adv["roster"]:
        with st.expander("📋 Прогнозируемые составы (по 10 последним протоколам)"):
            st.write(f"**{hn}:** " + ", ".join(h_adv["roster"]))
            st.write(f"**{an}:** " + ", ".join(a_adv["roster"]))

    # 2. Таблица вероятностей со справедливыми коэффициентами
    st.subheader("2. Таблица вероятностей и справедливых КФ")
    rows = []
    for k, prob in m.items():
        fair_odd = round(100.0 / prob, 2) if prob > 0 else 99.0
        rows.append({"Маркет": k, "Вероятность (%)": prob, "Справедл. КФ": fair_odd})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # 3. Топ-5 точных счетов
    st.subheader("3. Топ-5 точных счетов (основное время)")
    st.dataframe(pd.DataFrame(res["top_5_scores"]), use_container_width=True, hide_index=True)

    # 4. Калькулятор Value (сравнение с линией)
    st.subheader("4. Проверка перевеса (Value / EV)")
    vc1, vc2 = st.columns(2)
    with vc1:
        sel_mkt = st.selectbox("Выберите маркет:", list(m.keys()))
    with vc2:
        bookie_odd = st.number_input("Коэффициент в линии:", 1.01, 50.0, 2.00, 0.05)

    p_model = m[sel_mkt] / 100.0
    ev_pct = round(((p_model * bookie_odd) - 1.0) * 100, 2)
    fair_k = round(1.0 / p_model, 2) if p_model > 0 else 99.0
    kelly = max(0.0, round(((p_model * bookie_odd - 1.0) / (bookie_odd - 1.0)) * 0.25 * 100, 2))

    if ev_pct > 0:
        st.success(f"✅ **Найдено математическое ожидание (Value): +{ev_pct}%** | Справедливый КФ: **{fair_k}** | Четверть-Келли: **{kelly}%** от банка")
    else:
        st.warning(f"⚠️ **Перевеса нет (EV: {ev_pct}%)** | Справедливый КФ модели: **{fair_k}** (в линии занижен)")

    # 5. Статистический вывод
    st.subheader("5. Объективный статистический вывод")
    st.write(f"Ожидаемый тотал: **{l1 + l2:.2f} шайб**. П1: **{m['П1']}%** (1Х — **{m['1Х']}%**), П2: **{m['П2']}%** (2Х — **{m['2Х']}%**), ТБ 5.5: **{m['ТБ 5.5']}%**.")
