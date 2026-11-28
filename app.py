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

with st.spinner(f"Автозагрузка матчей {sel_label}..."):
    matches, team_stats = cached_league(code)

h_key, a_key = None, None
h_def = {"name": "Хозяева", "xg_per60": 3.00, "xga_per60": 2.65, "hdcf_pct": 51.5, "pp_pct": 21.5, "pk_pct": 80.5, "goalie_gsax_per60": 0.08}
a_def = {"name": "Гости", "xg_per60": 2.80, "xga_per60": 2.80, "hdcf_pct": 49.0, "pp_pct": 19.5, "pk_pct": 79.0, "goalie_gsax_per60": 0.00}

if matches:
    sel_m = st.selectbox("📅 Предстоящие матчи (автозагрузка):", [m["label"] for m in matches])
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

if st.button("🚀 Рассчитать матч (Ансамбль 500 000 симуляций)", use_container_width=True):
    res = HockeyMatchSimulator(n_sims=500_000).run_ensemble(h_def, a_def)
    l1, l2 = res["lambdas"]
    st.success(f"Ожидаемые голы: **{h_def['name']} (λ₁ = {l1})** — **{a_def['name']} (λ₂ = {l2})**")

    st.subheader("1. Ключевые факторы матча")
    st.info(
        f"**• xG и моменты:** {h_def['name']} ({h_def['xg_per60']} xG, {h_def['hdcf_pct']}% HDCF) vs {a_def['name']} ({a_def['xg_per60']} xG, {a_def['hdcf_pct']}% HDCF)\n\n"
        f"**• Владение (10 протоколов):** {h_adv['corsi_pct']}% CF / {h_adv['fenwick_pct']}% FF vs {a_adv['corsi_pct']}% CF / {a_adv['fenwick_pct']}% FF\n\n"
        f"**• Вратари GSAx/60:** {h_def['goalie_gsax_per60']:+.2f} vs {a_def['goalie_gsax_per60']:+.2f}"
    )

    if h_adv and h_adv["roster"]:
        with st.expander("📋 Прогнозируемые составы (по 10 последним протоколам)"):
            st.write(f"**{h_def['name']}:** " + ", ".join(h_adv["roster"]))
            st.write(f"**{a_def['name']}:** " + ", ".join(a_adv["roster"]))

    st.subheader("2. Сводная таблица вероятностей (%)")
    st.dataframe(pd.DataFrame([{"Маркет": k, "Вероятность (%)": v} for k, v in res["markets"].items()]), use_container_width=True, hide_index=True)

    st.subheader("3. Топ-5 точных счетов (основное время)")
    st.dataframe(pd.DataFrame(res["top_5_scores"]), use_container_width=True, hide_index=True)

    st.subheader("4. Объективный статистический вывод")
    m = res["markets"]
    st.write(f"Ожидаемый тотал: **{l1 + l2:.2f} шайб**. П1: **{m['П1 (Победа хозяев)']}%** (1Х — **{m['1Х']}%**), П2: **{m['П2 (Победа гостей)']}%** (2Х — **{m['2Х']}%**), ТБ 5.5: **{m['ТБ 5.5']}%**.")
