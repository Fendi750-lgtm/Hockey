import streamlit as st
import numpy as np
import pandas as pd
from scipy.stats import nbinom

st.set_page_config(page_title="Hockey Monte Carlo Simulator", layout="wide")

st.title("🏒 Ансамбль симуляции хоккейных матчей (1 000 000 итераций)")
st.markdown("Расчет вероятностей исходов, тоталов, фор и точного счета в основное время (60 минут).")

# Боковая панель ввода данных
with st.sidebar:
    st.header("Параметры матча")
    team1 = st.text_input("Хозяева (Команда 1)", "СКА")
    team2 = st.text_input("Гости (Команда 2)", "Барыс")
    
    st.subheader("Ожидаемые голы (λ)")
    lam1 = st.number_input(f"λ {team1}", min_value=0.5, max_value=7.0, value=3.25, step=0.05)
    lam2 = st.number_input(f"λ {team2}", min_value=0.5, max_value=7.0, value=2.40, step=0.05)
    
    st.subheader("Настройки моделей")
    n_sims = st.select_slider("Количество итераций на модель", options=[50_000, 100_000, 250_000], value=250_000)
    rho = st.slider("Поправка Диксона-Коулза (ρ)", -0.15, 0.05, -0.06, 0.01)
    dispersion = st.slider("Дисперсия (Negative Binomial r)", 2.0, 20.0, 8.0, 0.5)
    
    run_btn = st.button("🚀 Запустить симуляцию", type="primary", use_container_width=True)

@st.cache_data
def run_ensemble_simulation(l1, l2, n, rho_dc, r_nb):
    rng = np.random.default_rng(42)
    
    # 1. Bivariate Poisson (с учетом общей ковариации темпа игры)
    cov = min(l1, l2) * 0.12
    g0 = rng.poisson(cov, n)
    bp_1 = rng.poisson(max(0.1, l1 - cov), n) + g0
    bp_2 = rng.poisson(max(0.1, l2 - cov), n) + g0
    
    # 2. Dixon-Coles (коррекция низовых и ничейных счетов 0:0, 1:0, 0:1, 1:1)
    dc_1 = rng.poisson(l1, n)
    dc_2 = rng.poisson(l2, n)
    mask_00 = (dc_1 == 0) & (dc_2 == 0)
    mask_11 = (dc_1 == 1) & (dc_2 == 1)
    # Вероятностная корректировка ничьих
    flip = rng.random(n)
    dc_1 = np.where(mask_00 & (flip < abs(rho_dc)), 1, dc_1)
    dc_2 = np.where(mask_11 & (flip < abs(rho_dc)), 2, dc_2)

    # 3. Negative Binomial (учет нестабильности и разброса формы)
    p1 = r_nb / (r_nb + l1)
    p2 = r_nb / (r_nb + l2)
    nb_1 = rng.negative_binomial(r_nb, p1, n)
    nb_2 = rng.negative_binomial(r_nb, p2, n)

    # 4. Markov Chain (разбиение на 58 мин обычной игры + 2 мин Empty Net)
    mc_1 = rng.poisson(l1 * (58 / 60), n)
    mc_2 = rng.poisson(l2 * (58 / 60), n)
    
    # Логика снятия вратаря при разнице в 1-2 шайбы за 2 минуты до конца
    diff = mc_1 - mc_2
    trailing_2 = (diff == 1) | (diff == 2)
    trailing_1 = (diff == -1) | (diff == -2)
    
    # Обычные 2 минуты для равных счетов или разгромов
    normal_end = ~(trailing_1 | trailing_2)
    mc_1 += np.where(normal_end, rng.poisson(l1 * (2 / 60), n), 0)
    mc_2 += np.where(normal_end, rng.poisson(l2 * (2 / 60), n), 0)
    
    # Если проигрывают гости: выше шанс забить 6 на 5, но высокий риск пропустить в пустые (EN)
    mc_2 += np.where(trailing_2, rng.poisson(l2 * (2 / 60) * 1.45, n), 0)
    mc_1 += np.where(trailing_2, rng.poisson(0.32, n), 0)
    
    # Если проигрывают хозяева
    mc_1 += np.where(trailing_1, rng.poisson(l1 * (2 / 60) * 1.45, n), 0)
    mc_2 += np.where(trailing_1, rng.poisson(0.32, n), 0)

    # Объединение результатов всех 4 моделей в единый ансамбль
    goals_1 = np.concatenate([bp_1, dc_1, nb_1, mc_1])
    goals_2 = np.concatenate([bp_2, dc_2, nb_2, mc_2])
    total = goals_1 + goals_2
    
    return goals_1, goals_2, total

if run_btn or True:
    g1, g2, tot = run_ensemble_simulation(lam1, lam2, n_sims, rho, dispersion)
    total_iters = len(g1)
    
    st.success(f"Выполнено **{total_iters:,}** симуляций ({n_sims:,} на каждую из 4 моделей).".replace(",", " "))
    
    # Базовые вероятности
    p1 = np.mean(g1 > g2) * 100
    x = np.mean(g1 == g2) * 100
    p2 = np.mean(g1 < g2) * 100
    
    # Отображение главных метрик
    col1, col2, col3 = st.columns(3)
    col1.metric(f"П1 ({team1})", f"{p1:.2f}%")
    col2.metric("Х (Ничья в 60 мин)", f"{x:.2f}%")
    col3.metric(f"П2 ({team2})", f"{p2:.2f}%")
    
    st.divider()
    
    # Формирование сводной таблицы маркетов
    markets_data = [
        ("Исходы", f"П1 ({team1})", f"{p1:.2f}%"),
        ("Исходы", "Х (Ничья)", f"{x:.2f}%"),
        ("Исходы", f"П2 ({team2})", f"{p2:.2f}%"),
        ("Исходы", "1Х", f"{p1 + x:.2f}%"),
        ("Исходы", "2Х", f"{p2 + x:.2f}%"),
        ("Тоталы", "ТБ 4.5 / ТМ 4.5", f"{np.mean(tot > 4.5)*100:.2f}% / {np.mean(tot < 4.5)*100:.2f}%"),
        ("Тоталы", "ТБ 5.5 / ТМ 5.5", f"{np.mean(tot > 5.5)*100:.2f}% / {np.mean(tot < 5.5)*100:.2f}%"),
        ("Тоталы", "ТБ 6.5 / ТМ 6.5", f"{np.mean(tot > 6.5)*100:.2f}% / {np.mean(tot < 6.5)*100:.2f}%"),
        ("Форы", "Ф1 (-1.5)", f"{np.mean((g1 - g2) >= 2)*100:.2f}%"),
        ("Форы", "Ф1 (+1.5)", f"{np.mean((g1 - g2) >= -1)*100:.2f}%"),
        ("Форы", "Ф2 (-1.5)", f"{np.mean((g2 - g1) >= 2)*100:.2f}%"),
        ("Форы", "Ф2 (+1.5)", f"{np.mean((g2 - g1) >= -1)*100:.2f}%"),
        ("Комби", "П1 + ТБ 5.5 / П1 + ТМ 5.5", f"{np.mean((g1 > g2) & (tot > 5.5))*100:.2f}% / {np.mean((g1 > g2) & (tot < 5.5))*100:.2f}%"),
        ("Комби", "П2 + ТБ 5.5 / П2 + ТМ 5.5", f"{np.mean((g1 < g2) & (tot > 5.5))*100:.2f}% / {np.mean((g1 < g2) & (tot < 5.5))*100:.2f}%"),
        ("Комби", "1Х + ТБ 5.5 / 1Х + ТМ 5.5", f"{np.mean((g1 >= g2) & (tot > 5.5))*100:.2f}% / {np.mean((g1 >= g2) & (tot < 5.5))*100:.2f}%"),
        ("Комби", "2Х + ТБ 5.5 / 2Х + ТМ 5.5", f"{np.mean((g1 <= g2) & (tot > 5.5))*100:.2f}% / {np.mean((g1 <= g2) & (tot < 5.5))*100:.2f}%"),
    ]
    
    left_col, right_col = st.columns([2, 1])
    
    with left_col:
        st.subheader("📊 Сводная таблица маркетов")
        df_markets = pd.DataFrame(markets_data, columns=["Категория", "Маркет", "Вероятность"])
        st.dataframe(df_markets, use_container_width=True, hide_index=True)
        
    with right_col:
        st.subheader("🎯 Топ-5 точных счетов")
        scores = pd.Series([f"{a}:{b}" for a, b in zip(g1, g2)]).value_counts(normalize=True).head(5) * 100
        df_scores = pd.DataFrame({
            "Точный счет": scores.index,
            "Вероятность": [f"{v:.2f}%" for v in scores.values]
        })
        st.dataframe(df_scores, use_container_width=True, hide_index=True)
