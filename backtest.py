"""
========
🛡️ AEGIS PRIME - ADAPTIVE VOLATILITY BACKTEST ENGINE (FIXED)
========
"""

import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')


# 1. CONFIGURATION & UNIVERS

START_DATE = "2016-01-01"
END_DATE = datetime.now().strftime("%Y-%m-%d")
INITIAL_CAPITAL = 10000.0
TRANSACTION_COST = 0.0010  # 0.10% de frais par trade (Slippage + Commission)

SECTORS = {
    'Tech/Growth': ['NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'QQQ', 'SMH', 'AAPL', 'TSLA'],
    'Healthcare': ['LLY', 'UNH', 'JNJ'],
    'Energy/Metal': ['XLE', 'COPX', 'URA', 'XME'],
    'Industrie/Def': ['ITA', 'XLI', 'RTX'],
    'Alpha/Global': ['IBIT', 'EEM', 'VEA', 'BITO', 'KWEB']
}

ATTACK_ASSETS = [t for sub in SECTORS.values() for t in sub]
DEFENSE_ASSETS = ['GLD', 'TLT', 'SHY', 'SH', 'VIXY', 'SHV']

# Proxy pour IBIT (Bitcoin ETF récent)
PROXY_MAP = {'IBIT': 'BTC-USD'}
FETCH_TICKERS = list(set([PROXY_MAP.get(t, t) for t in ATTACK_ASSETS + DEFENSE_ASSETS + ['SPY']]))


# 2. RÉCUPÉRATION DES DONNÉES

print(f"📥 Téléchargement des données depuis {START_DATE}...")
raw_data = yf.download(FETCH_TICKERS, start=START_DATE, end=END_DATE, progress=False)['Close']

if 'BTC-USD' in raw_data.columns:
    raw_data['IBIT'] = raw_data['BTC-USD']

# Nettoyage sécurisé
df = raw_data.ffill()
print(f"✅ Données chargées : {len(df)} jours ouvrés.")


# 3. MOTEUR MATHÉMATIQUE (AEGIS V25 LOGIC)

def get_growth_target(data_slice):
    if data_slice['SPY'].iloc[-1] < data_slice['SPY'].rolling(200).mean().iloc[-1]:
        return {'GLD': 0.4, 'TLT': 0.4, 'SHV': 0.2}
    
    mom = (data_slice.iloc[-1] / data_slice.iloc[-126]) - 1
    vol = data_slice.pct_change().rolling(60).std().iloc[-1]
    
    # Dropna garantit qu'on ne sélectionne que des actifs qui existent déjà
    score = (mom / vol).reindex(ATTACK_ASSETS).dropna().sort_values(ascending=False).head(5)
    
    if score.empty: return {'SHV': 1.0}
    return {s: 1.0/len(score) for s in score.index}

def get_shield_target(data_slice):
    vol = data_slice.pct_change().rolling(60).std().iloc[-1]
    mom = (data_slice.iloc[-1] / data_slice.iloc[-126]) - 1
    score = (mom / vol).reindex(ATTACK_ASSETS).dropna().sort_values(ascending=False).head(6)
    
    if score.empty: return {'GLD': 0.5, 'SHV': 0.5}
    
    inv_v = 1 / vol[score.index]
    return {k: v/inv_v.sum() for k, v in inv_v.items()}


# 4. SIMULATEUR DE PORTEFEUILLE

print("🚀 Lancement du Backtest (Rebalancement Hebdomadaire)...")

rebalance_dates = df.resample('W-FRI').last().index
rebalance_dates = [d for d in rebalance_dates if d in df.index and df.index.get_loc(d) > 200]

equity_curve = [INITIAL_CAPITAL]
weights = {t: 0.0 for t in df.columns}

for i in range(1, len(rebalance_dates)):
    date = rebalance_dates[i]
    prev_date = rebalance_dates[i-1]
    
    # 1. Calcul des rendements (AVEC PROTECTION ANTI-NaN)
    prices_curr = df.loc[date]
    prices_prev = df.loc[prev_date]
    period_rets = (prices_curr / prices_prev) - 1
    period_rets = period_rets.fillna(0) # Les actifs manquants rapportent 0%
    
    port_ret = sum(weights.get(t, 0) * period_rets.get(t, 0) for t in weights)
    
    # 2. Snapshot Data
    idx = df.index.get_loc(date)
    data_slice = df.iloc[:idx+1]
    
    # 3. Logique Adaptative
    spy_vol = data_slice['SPY'].pct_change().rolling(21).std().iloc[-1] * np.sqrt(252)
    
    if spy_vol < 0.18: split = [0.9, 0.1]
    elif spy_vol > 0.28: split = [0.2, 0.8]
    else: split = [0.5, 0.5]

    # 4. Cibles
    t_growth = get_growth_target(data_slice)
    t_shield = get_shield_target(data_slice)
    
    target_weights = {}
    all_assets = set(list(t_growth.keys()) + list(t_shield.keys()))
    for a in all_assets:
        w = (t_growth.get(a, 0) * split[0]) + (t_shield.get(a, 0) * split[1])
        if w > 0.02: target_weights[a] = w
            
    total_w = sum(target_weights.values())
    if total_w > 0:
        target_weights = {k: v/total_w for k, v in target_weights.items()}

    # 5. Frais & NAV
    turnover = sum(abs(target_weights.get(t, 0) - weights.get(t, 0)) for t in df.columns)
    fees = turnover * TRANSACTION_COST
    
    new_nav = equity_curve[-1] * (1 + port_ret - fees)
    equity_curve.append(new_nav)
    
    weights = target_weights


# 5. RÉSULTATS & GRAPHIQUES

strategy_equity = pd.Series(equity_curve, index=rebalance_dates)
spy_bench = (df['SPY'].loc[rebalance_dates] / df['SPY'].loc[rebalance_dates[0]]) * INITIAL_CAPITAL

def calc_metrics(series):
    rets = series.pct_change().dropna()
    cagr = (series.iloc[-1] / series.iloc[0]) ** (252 / (len(series) * 5)) - 1
    vol = rets.std() * np.sqrt(52)
    sharpe = cagr / vol if vol > 0 else 0
    drawdown = (series - series.cummax()) / series.cummax()
    max_dd = drawdown.min()
    return cagr, vol, sharpe, max_dd

cagr, vol, sharpe, max_dd = calc_metrics(strategy_equity)
b_cagr, b_vol, b_sharpe, b_max_dd = calc_metrics(spy_bench)

print("\n" + "="*50)
print("📊 RÉSULTATS DU BACKTEST AEGIS PRIME V25")
print("="*50)
print(f"Période      : {START_DATE} à {END_DATE}")
print(f"Capital Final: ${strategy_equity.iloc[-1]:,.2f} (Init: ${INITIAL_CAPITAL:,.0f})")
print(f"CAGR         : {cagr:.2%} (vs SPY: {b_cagr:.2%})")
print(f"Sharpe Ratio : {sharpe:.2f} (vs SPY: {b_sharpe:.2f})")
print(f"Max Drawdown : {max_dd:.2%} (vs SPY: {b_max_dd:.2%})")
print("="*50)

plt.style.use('dark_background')
fig, ax = plt.subplots(figsize=(14, 7))

ax.plot(strategy_equity.index, strategy_equity, color='#00FFAA', linewidth=2.5, label=f'AEGIS PRIME (CAGR: {cagr:.1%})')
ax.plot(spy_bench.index, spy_bench, color='#888888', linestyle='--', linewidth=1.5, label=f'S&P 500 (CAGR: {b_cagr:.1%})')

ax.fill_between(strategy_equity.index, strategy_equity, spy_bench, 
                where=(strategy_equity > spy_bench), color='#00FFAA', alpha=0.1)

ax.set_title("🛡️ AEGIS PRIME - Performance Historique vs S&P 500", fontsize=16, fontweight='bold', pad=20)
ax.set_ylabel("Valeur du Portefeuille ($)", fontsize=12)
ax.set_yscale('log')
ax.yaxis.set_major_formatter('${x:,.0f}')
ax.grid(color='#333333', linestyle='--', alpha=0.7)
ax.legend(loc='upper left', fontsize=12, frameon=True, facecolor='#000000', edgecolor='#00FFAA')

plt.tight_layout()
plt.savefig('aegis_backtest_results.png', dpi=300, bbox_inches='tight')
print("📸 Graphique généré avec succès : 'aegis_backtest_results.png'")