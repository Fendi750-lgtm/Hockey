import streamlit as st
import pandas as pd
from engine import fetch_nhl_schedule_and_standings, fetch_nhl_last_10, HockeyMatchSimulator

st.set_page_config(page_title="Hockey AI & Monte Carlo", page_icon="🏒", layout="centered")

@st.cache_data(ttl=1800)
def get_nhl_cached():
    return fetch_nhl_schedule_and_standings()

@st.cache_data(ttl=1800)
def get_last10_cached(ab: str):
    return fetch_nhl_last_10(ab)

st.title("🏒 Хоккейный Анализатор (500K)")

league = st.selectbox(
    "Выберите лигу:",
    ["NHL (Автозагрузка API)", "KHL", "Liiga", "Extraliga", "DEL", "SHL", "NL", "EHL"]
)

h_def = {"name": "Хозяева", "xg_per60": 3.05, "xga_per60": 2.60, "hdcf_pct": 52.0, "pp_pct": 22.0, "pk_pct": 80.5, "goalie_gsax_per60": 0.10}
a_def = {"name": "Гости", "xg_per60": 2.85, "xga_per60": 2.80, "hdcf_pct": 49.0, "pp_pct": 20.0, "pk_pct": 79.0, "goalie_gsax_per60": 0.00}
h_adv, a_adv = None, None

if "NHL" in league:
    with st.spinner("Загрузка матчей НХЛ на ближайшие 24 часа..."):
        nhl_matches, nhl_stats = get_nhl_cached()
    if nhl_matches:
        sel = st.selectbox("Предстоящие матчи (24ч):", [m["label"] for m in nhl_matches])
        m_obj = next(m for m in nhl_matches if m["label"] == sel)
        h_def = nhl_stats.get(m_obj["home"], h_def)
        a_def = nhl_stats.get(m_obj["away"], a_def)
        with st.spinner("Анализ 10 последних протоколов..."):
            h_adv = get_last10_cached(m_obj["home"])
            a_adv = get_last10_cached(m_obj["away"])

with st.expander("Параметры команд (xG, HDCF, спецбригады, вратари)"):
    c1, c2 = st.columns(2)
    with c1:
        h_name = st.text_input("Хозяева", h_def["name"])
        h_xg = st.number_input("xG/60 (Хоз)", 1.0, 6.0, float(h_def["xg_per60"]), 0.05)
        h_xga = st.number_input("xGA/60 (Хоз)", 1.0, 6.0, float(h_def["xga_per60"]), 0.05)
        h_hdcf = st.number_input("HDCF% (Хоз)", 30.0, 70.0, float(h_def["hdcf_pct"]), 0.5)
        h_pp = st.number_input("PP% (Хоз)", 5.0, 45.0, float(h_def["pp_pct"]), 0.5)
        h_pk = st.number_input("PK% (Хоз)", 60.0, 95.0, float(h_def["pk_pct"]), 0.5)
        h_gsax = st.number_input("Вратарь GSAx/60 (Хоз)", -1.5, 1.5, float(h_def["goalie_gsax_per60"]), 0.02)
    with c2:
        a_name = st.text_input("Гости", a_def["name"])
        a_xg = st.number_input("xG/60 (Гос)", 1.0, 6.0, float(a_def["xg_per60"]), 0.05)
        a_xga = st.number_input("xGA/60 (Гос)", 1.0, 6.0, float(a_def["xga_per60"]), 0.05)
        a_hdcf = st.number_input("HDCF% (Гос)", 30.0, 70.0, float(a_def["hdcf_pct"]), 0.5)
        a_pp = st.number_input("PP% (Гос)", 5.0, 45.0, float(a_def["pp_pct"]), 0.5)
        a_pk = st.number_input("PK% (Гос)", 60.0, 95.0, float(a_def["pk_pct"]), 0.5)
        a_gsax = st.number_input("Вратарь GSAx/60 (Гос)", -1.5, 1.5, float(a_def["goalie_gsax_per60"]), 0.02)

if st.button("🚀 Рассчитать матч (Ансамбль 500 000 симуляций)", use_container_width=True):
    sim = HockeyMatchSimulator(n_sims=500_000)
    res = sim.run_ensemble(
        {"xg_per60": h_xg, "xga_per60": h_xga, "hdcf_pct": h_hdcf, "pp_pct": h_pp, "pk_pct": h_pk, "goalie_gsax_per60": h_gsax},
        {"xg_per60": a_xg, "xga_per60": a_xga, "hdcf_pct": a_hdcf, "pp_pct": a_pp, "pk_pct": a_pk, "goalie_gsax_per60": a_gsax}
    )
    l1, l2 = res["lambdas"]
    st.success(f"Ожидаемые голы: **{h_name} (λ₁ = {l1})** — **{a_name} (λ₂ = {l2})**")

    st.subheader("1. Ключевые факторы матча")
    corsi_txt = f"\n\n**• Corsi (по 10 играм):** {h_name} {h_adv['corsi_pct']}% ({h_adv['avg_sog']} бр) vs {a_name} {a_adv['corsi_pct']}% ({a_adv['avg_sog']} бр)" if h_adv and a_adv else ""
    st.info(f"**• Тренды xG и моменты:** {h_name} ({h_xg} xG, {h_hdcf}% HDCF) vs {a_name} ({a_xg} xG, {a_hdcf}% HDCF)\n\n**• Вратари GSAx/60:** {h_gsax:+.2f} vs {a_gsax:+.2f}{corsi_txt}")

    if h_adv and h_adv["roster"]:
        with st.expander("📋 Прогнозируемые составы (10 последних протоколов)"):
            st.write(f"**{h_name}:** " + ", ".join(h_adv["roster"]))
            st.write(f"**{a_name}:** " + ", ".join(a_adv["roster"]))

    st.subheader("2. Сводная таблица вероятностей (%)")
    st.dataframe(pd.DataFrame([{"Маркет": k, "Вероятность (%)": v} for k, v in res["markets"].items()]), use_container_width=True, hide_index=True)

    st.subheader("3. Топ-5 точных счетов (основное время)")
    st.dataframe(pd.DataFrame(res["top_5_scores"]), use_container_width=True, hide_index=True)

    st.subheader("4. Объективный статистический вывод")
    m = res["markets"]
    st.write(f"Ожидаемый тотал: **{l1 + l2:.2f} шайб**. П1: **{m['П1 (Победа хозяев)']}%**, 1Х: **{m['1Х']}%**, П2: **{m['П2 (Победа гостей)']}%**, ТБ 5.5: **{m['ТБ 5.5']}%**.")
