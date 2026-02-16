import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')


START_DATE = "2016-01-01"
END_DATE = datetime.now().strftime("%Y-%m-%d")
INITIAL_CAPITAL = 10000.0

MAX_SECTOR_WEIGHT = 0.25
MAX_POSITION_SIZE = 0.08

SECTORS = {
    'Tech/Growth': ['NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'QQQ', 'SMH', 'AAPL', 'TSLA'],
    'Healthcare': ['LLY', 'UNH', 'JNJ'],
    'Energy/Metal': ['XLE', 'COPX', 'URA', 'XME'],
    'Industrie/Def': ['ITA', 'XLI', 'RTX'],
    'Alpha/Global': ['IBIT', 'EEM', 'VEA', 'BITO', 'KWEB']
}

ATTACK_ASSETS = [t for sub in SECTORS.values() for t in sub]
DEFENSE_ASSETS = ['GLD', 'TLT', 'SHY', 'SH', 'VIXY', 'SHV']
PROXY_MAP = {'IBIT': 'BTC-USD', 'BITO': 'BTC-USD'}
FETCH_TICKERS = list(set([PROXY_MAP.get(t, t) for t in ATTACK_ASSETS + DEFENSE_ASSETS + ['SPY']]))


print(f"\n📥 Téléchargement des données ({START_DATE} à {END_DATE})...")
raw_data = yf.download(FETCH_TICKERS, start=START_DATE, end=END_DATE, progress=False)['Close']

if 'BTC-USD' in raw_data.columns:
    raw_data['IBIT'] = raw_data['BTC-USD'] * 0.95
    raw_data['BITO'] = raw_data['BTC-USD'] * 0.85

df = raw_data.ffill().bfill()
print(f"✅ Données chargées : {len(df)} jours ouvrés.")


def enforce_risk_limits(weights):
    attack_w = {k: v for k, v in weights.items() if k in ATTACK_ASSETS}
    defense_w = {k: v for k, v in weights.items() if k in DEFENSE_ASSETS}

    attack_w = {k: min(v, MAX_POSITION_SIZE) for k, v in attack_w.items()}

    sector_exposure = {s: 0.0 for s in SECTORS.keys()}
    for ticker, weight in attack_w.items():
        for sector, tickers in SECTORS.items():
            if ticker in tickers: sector_exposure[sector] += weight
            
    for sector, exposure in sector_exposure.items():
        if exposure > MAX_SECTOR_WEIGHT:
            scale = MAX_SECTOR_WEIGHT / exposure
            for ticker in SECTORS[sector]:
                if ticker in attack_w: attack_w[ticker] *= scale

    final_weights = {**attack_w, **defense_w}
    
    total = sum(final_weights.values())
    if total > 0:
        final_weights = {k: (v/total)*0.98 for k, v in final_weights.items()}
        
    return {k: v for k, v in final_weights.items() if v >= 0.01}

# --- 3. MOTEUR DE SIMULATION MULTI-SCENARIOS ---
def run_simulation(df, rebalance_dates, transaction_cost=0.0010, use_bunker=True):
    equity_curve = [INITIAL_CAPITAL]
    weights = {t: 0.0 for t in df.columns}
    
    for i in range(1, len(rebalance_dates)):
        date = rebalance_dates[i]
        prev_date = rebalance_dates[i-1]
        
        rets = (df.loc[date] / df.loc[prev_date]) - 1
        port_ret = sum(weights.get(t, 0) * rets.get(t, 0) for t in weights)
        
        data_slice = df.iloc[:df.index.get_loc(date)+1]
        
        spy_price = data_slice['SPY'].iloc[-1]
        spy_sma200 = data_slice['SPY'].rolling(200).mean().iloc[-1]
        spy_vol = data_slice['SPY'].pct_change().rolling(21).std().iloc[-1] * np.sqrt(252)
        
        # Logique Bunker
        if use_bunker and spy_price < spy_sma200:
            target = {'GLD': 0.40, 'TLT': 0.40, 'SHV': 0.20}
        else:
            if spy_vol < 0.15: split = [0.90, 0.10]
            elif spy_vol > 0.25: split = [0.20, 0.80]
            else: split = [0.50, 0.50]
            
            mom = (data_slice.iloc[-1] / data_slice.iloc[-126]) - 1
            vol = data_slice.pct_change().rolling(60).std().iloc[-1] * np.sqrt(252)
            
            g_score = (mom / vol).reindex(ATTACK_ASSETS).dropna().sort_values(ascending=False).head(5)
            growth = {s: 1.0/len(g_score) for s in g_score.index} if not g_score.empty else {}
            
            s_score = (mom / vol).reindex(ATTACK_ASSETS).dropna().sort_values(ascending=False).head(6)
            shield = {k: (1/vol[k])/(1/vol[s_score.index]).sum() for k in s_score.index} if not s_score.empty else {}
            
            target = {}
            for a in set(list(growth.keys()) + list(shield.keys())):
                target[a] = growth.get(a, 0)*split[0] + shield.get(a, 0)*split[1]

        target = enforce_risk_limits(target)
        
        turnover = sum(abs(target.get(t, 0) - weights.get(t, 0)) for t in df.columns)
        fees = turnover * transaction_cost
        
        new_nav = equity_curve[-1] * (1 + port_ret - fees)
        equity_curve.append(new_nav)
        weights = target

    return pd.Series(equity_curve, index=rebalance_dates)

# Construction des dates de rebalancement (Correction intégrée)
valid_dates = pd.Series(df.index, index=df.index)
rebalance_dates = valid_dates.resample('W-FRI').last().dropna().values
rebalance_dates = [d for d in rebalance_dates if df.index.get_loc(d) > 200]

# Execution des Scénarios
print("🚀 Simulation 1/3 : AEGIS VF (10 bps fees)...")
strat_base = run_simulation(df, rebalance_dates, transaction_cost=0.0010, use_bunker=True)

print("🌪️ Simulation 2/3 : AEGIS Stress-Test (30 bps fees)...")
strat_stress = run_simulation(df, rebalance_dates, transaction_cost=0.0030, use_bunker=True)

print("📉 Simulation 3/3 : AEGIS No-Bunker (Sans protection 200 SMA)...")
strat_no_bunker = run_simulation(df, rebalance_dates, transaction_cost=0.0010, use_bunker=False)

bench = (df['SPY'].loc[rebalance_dates] / df['SPY'].loc[rebalance_dates[0]]) * INITIAL_CAPITAL

def calc_advanced_stats(series, name):
    rets = series.pct_change().dropna()
    monthly_rets = series.resample('ME').last().pct_change().dropna()
    
    years = len(series) / 52.14
    cagr = (series.iloc[-1] / series.iloc[0]) ** (1/years) - 1
    
    vol = rets.std() * np.sqrt(52.14)
    sharpe = cagr / vol if vol > 0 else 0
    
    downside_vol = rets[rets < 0].std() * np.sqrt(52.14)
    sortino = cagr / downside_vol if downside_vol > 0 else 0
    
    dd = (series - series.cummax()) / series.cummax()
    max_dd = dd.min()
    
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0
    
    win_rate_monthly = len(monthly_rets[monthly_rets > 0]) / len(monthly_rets)
    worst_month = monthly_rets.min()
    
    return {
        "Stratégie": name,
        "Capital Final": f"${series.iloc[-1]:,.0f}",
        "CAGR": f"{cagr:.2%}",
        "Max Drawdown": f"{max_dd:.2%}",
        "Sharpe Ratio": f"{sharpe:.2f}",
        "Sortino Ratio": f"{sortino:.2f}",
        "Calmar Ratio": f"{calmar:.2f}",
        "Volatilité": f"{vol:.2%}",
        "Win Rate (Mois)": f"{win_rate_monthly:.1%}",
        "Pire Mois": f"{worst_month:.2%}"
    }

stats_list = [
    calc_advanced_stats(strat_base, "🛡️ AEGIS VF (Base)"),
    calc_advanced_stats(strat_stress, "🌪️ AEGIS Stress (30bps)"),
    calc_advanced_stats(strat_no_bunker, "📉 AEGIS No-Bunker"),
    calc_advanced_stats(bench, "📊 S&P 500 (SPY)")
]

stats_df = pd.DataFrame(stats_list).set_index("Stratégie")

print("\n" + "="*85)
print("🏆 TABLEAU DE BORD DES PERFORMANCES INSTITUTIONNELLES")
print("="*85)
print(stats_df.to_markdown())
print("="*85)

plt.style.use('dark_background')
fig = plt.figure(figsize=(16, 12))
gs = fig.add_gridspec(3, 1, height_ratios=[2, 1, 1], hspace=0.3)

# Panneau 1 : Equity Curve
ax1 = fig.add_subplot(gs[0])
ax1.plot(strat_base, color='#00FFAA', lw=2.5, label=f"AEGIS VF Base")
ax1.plot(strat_stress, color='#FFD700', lw=1.5, ls='--', alpha=0.8, label="AEGIS Stress (30bps)")
ax1.plot(strat_no_bunker, color='#FF3333', lw=1.5, ls=':', alpha=0.8, label="AEGIS No-Bunker")
ax1.plot(bench, color='#888888', lw=1.5, label="S&P 500")
ax1.set_title("🛡️ AEGIS PRIME - Multi-Scenario Performance (Log Scale)", fontsize=14, fontweight='bold')
ax1.set_yscale('log')
ax1.set_ylabel("Valeur du Portefeuille ($)")
ax1.yaxis.set_major_formatter('${x:,.0f}')
ax1.grid(color='#333333', linestyle='--', alpha=0.5)
ax1.legend(loc='upper left', frameon=True, facecolor='black')

# Panneau 2 : Drawdowns
ax2 = fig.add_subplot(gs[1], sharex=ax1)
dd_base = (strat_base - strat_base.cummax()) / strat_base.cummax()
dd_bench = (bench - bench.cummax()) / bench.cummax()
ax2.fill_between(dd_base.index, dd_base, 0, color='#00FFAA', alpha=0.3, label="AEGIS VF Drawdown")
ax2.plot(dd_bench, color='#888888', lw=1, alpha=0.7, label="SPY Drawdown")
ax2.set_title("Analyse des Drawdowns (Sous le plus haut historique)", fontsize=12)
ax2.set_ylabel("Chute (%)")
ax2.yaxis.set_major_formatter('{x:.0%}')
ax2.grid(color='#333333', linestyle='--', alpha=0.5)
ax2.legend(loc='lower right')

# Panneau 3 : Rendements Annuels (AEGIS vs SPY)
ax3 = fig.add_subplot(gs[2])
ann_aegis = strat_base.resample('YE').last().pct_change().dropna() * 100
ann_spy = bench.resample('YE').last().pct_change().dropna() * 100

years = [d.year for d in ann_aegis.index]
x = np.arange(len(years))
width = 0.35

ax3.bar(x - width/2, ann_aegis, width, label='AEGIS VF', color='#00FFAA')
ax3.bar(x + width/2, ann_spy, width, label='S&P 500', color='#888888')

ax3.set_title("Rendements Annuels Nettes (%)", fontsize=12)
ax3.set_xticks(x)
ax3.set_xticklabels(years)
ax3.axhline(0, color='white', lw=0.5)
ax3.legend()

plt.savefig('aegis_master_dashboard.png', dpi=300, bbox_inches='tight', facecolor='#0E1117')
print("\n📸 Master Dashboard généré avec succès : 'aegis_master_dashboard.png'")
