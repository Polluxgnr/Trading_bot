import os, time, logging, json, requests, io, schedule, pytz
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import alpaca_trade_api as tradeapi
from alpaca_trade_api.rest import TimeFrame
from mistralai import Mistral
from dotenv import load_dotenv
from functools import wraps

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("AEGIS_VF")
NY_TZ = pytz.timezone('US/Eastern')

# CONFIGURATION & LIMITES INSTITUTIONNELLES 

PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

MAX_SECTOR_WEIGHT = 0.25  # 25% max par secteur
MAX_POSITION_SIZE = 0.08  # 8% max par actif offensif
CASH_RESERVE = 0.02       # 2% de cash permanent (Anti-Levier)

SECTORS = {
    'Tech/Growth': ['NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'QQQ', 'SMH', 'AAPL', 'TSLA'],
    'Healthcare': ['LLY', 'UNH', 'JNJ'],
    'Energy/Metal': ['XLE', 'COPX', 'URA', 'XME'],
    'Industrie/Def': ['ITA', 'XLI', 'RTX'],
    'Alpha/Global': ['IBIT', 'EEM', 'VEA', 'BITO', 'KWEB']
}
ATTACK_ASSETS = [t for sub in SECTORS.values() for t in sub]
DEFENSE_ASSETS = ['GLD', 'TLT', 'SHY', 'SH', 'VIXY', 'SHV']
ALL_TICKERS = list(set(ATTACK_ASSETS + DEFENSE_ASSETS + ['SPY']))


# UTILITAIRES & REPORTING DISCORD

def retry_network(max_retries=3):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(max_retries):
                try: return func(*args, **kwargs)
                except Exception as e: time.sleep(2 ** i)
            raise Exception(f"Failed after {max_retries} attempts")
        return wrapper
    return decorator

class DiscordReporter:
    def __init__(self, api, webhook_url):
        self.api = api
        self.webhook_url = webhook_url
        self.ai = Mistral(api_key=os.getenv("MISTRAL_API_KEY")) if os.getenv("MISTRAL_API_KEY") else None

    @retry_network()
    def send_report(self, regime, trades, weights, cb_alert=False):
        if not self.webhook_url: return
        acc = self.api.get_account()
        
        hist = self.api.get_portfolio_history(period="1M", timeframe="1D")
        df = pd.DataFrame({'equity': hist.equity}, index=pd.to_datetime(hist.timestamp, unit='s', utc=True)).dropna()
        sharpe = (df['equity'].pct_change().mean() / df['equity'].pct_change().std()) * np.sqrt(252) if len(df)>2 else 0

        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(df.index, df['equity'], color='#FF3333' if cb_alert else '#00FFAA', lw=2)
        ax.set_title(f"Portfolio Performance | Sharpe: {sharpe:.2f}")
        ax.grid(alpha=0.1)
        buf = io.BytesIO(); plt.savefig(buf, format='png', facecolor='#0E1117'); buf.seek(0); plt.close(fig)

        ai_msg = "🚨 CIRCUIT BREAKER: TRADING HALTED DUE TO INTRADAY DROP." if cb_alert else "Portfolio dynamically rebalanced based on quantitative volatility parameters."
        if self.ai and not cb_alert:
            try:
                prompt = f"Market Regime: {regime}. Write 2 concise sentences explaining this institutional allocation. Professional tone. No greetings."
                ai_msg = self.ai.chat.complete(model="mistral-tiny", messages=[{"role":"user","content":prompt}]).choices[0].message.content
            except: pass

        embed = {
            "title": "🛡️ AEGIS PRIME VF | REPORT" + (" [HALTED]" if cb_alert else ""),
            "color": 0xFF3333 if cb_alert else 0x00FFAA,
            "description": f"**Net Equity**: `${float(acc.equity):,.2f}` | **Mode**: `{'PAPER' if PAPER_TRADING else 'LIVE'}`",
            "fields": [
                {"name": "🧠 AI Analyst Commentary", "value": f"_{ai_msg}_", "inline": False},
                {"name": "🌍 Market Regime", "value": f"`{regime}`", "inline": False},
                {"name": "🎯 Target Allocation", "value": f"```json\n{json.dumps({k: f'{v:.1%}' for k,v in weights.items() if v > 0}, indent=2)}\n```"},
                {"name": "⚡ Executed Trades", "value": "\n".join(trades) if trades else "No rebalance needed (Inside drift tolerance)."}
            ],
            "footer": {"text": "Aegis Prime Kernel VF • Decoupled Risk Standard"}
        }
        requests.post(self.webhook_url, data={'payload_json': json.dumps({"embeds": [embed]})}, files={'file': ('chart.png', buf, 'image/png')})
        logger.info("✅ Discord report transmitted.")


# MOTEUR QUANTITATIF & EXÉCUTION

class AegisEngine:
    def __init__(self):
        self.api = tradeapi.REST(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), os.getenv("ALPACA_BASE_URL"), 'v2')
        self.reporter = DiscordReporter(self.api, os.getenv("DISCORD_WEBHOOK_URL"))

    def check_intraday_drawdown(self):
        """Coupe-circuit journalier : stope tout si chute > 10% aujourd'hui"""
        try:
            hist = self.api.get_portfolio_history(period="1D", timeframe="15Min")
            if not hist.equity: return True
            dd = (float(self.api.get_account().equity) - hist.equity[0]) / hist.equity[0]
            if dd < -0.10:
                logger.critical(f"🚨 CIRCUIT BREAKER: Daily drawdown {dd:.1%} exceeds limit.")
                return False
            return True
        except: return True

    @retry_network()
    def get_market_data(self):
        start = (datetime.now(NY_TZ) - timedelta(days=200)).strftime('%Y-%m-%d')
        bars = self.api.get_bars(ALL_TICKERS, TimeFrame.Day, start=start, limit=10000).df
        if bars.empty: return pd.DataFrame()
        return bars.pivot_table(index='timestamp', columns='symbol', values='close').ffill().bfill()

    def calculate_allocation(self, df):
        """Logique Mathématique Exacte de la VF"""
        spy_close = df['SPY'].iloc[-1]
        spy_sma200 = df['SPY'].rolling(200).mean().iloc[-1]
        spy_vol = df['SPY'].pct_change().rolling(21).std().iloc[-1] * np.sqrt(252)

        # 1. LE BUNKER MACRO (Priorité Absolue)
        if spy_close < spy_sma200:
            logger.warning("🐻 SPY < 200 SMA: BUNKER MODE ACTIVATED")
            return {'GLD': 0.40, 'TLT': 0.40, 'SHV': 0.20}, "BEAR MARKET (BUNKER MODE)"

        # 2. REGIMES DE VOLATILITÉ
        if spy_vol < 0.15: split = [0.90, 0.10]; regime = "BULL AGGRESSIVE (Low Vol)"
        elif spy_vol > 0.25: split = [0.20, 0.80]; regime = "BULL DEFENSIVE (High Vol)"
        else: split = [0.50, 0.50]; regime = "BULL NORMAL (Mid Vol)"

        mom = (df.iloc[-1] / df.iloc[-126]) - 1
        vol = df.pct_change().rolling(60).std().iloc[-1] * np.sqrt(252)

        # 3. MOTEUR GROWTH (Momentum ajusté au risque)
        g_score = (mom / vol).reindex(ATTACK_ASSETS).dropna().sort_values(ascending=False).head(5)
        growth = {s: 1.0/len(g_score) for s in g_score.index} if not g_score.empty else {}

        # 4. MOTEUR SHIELD (Inverse Volatilité)
        s_score = (mom / vol).reindex(ATTACK_ASSETS).dropna().sort_values(ascending=False).head(6)
        shield = {k: (1/vol[k])/(1/vol[s_score.index]).sum() for k in s_score.index} if not s_score.empty else {}

        # 5. FUSION
        target = {}
        for a in set(list(growth.keys()) + list(shield.keys())):
            target[a] = growth.get(a, 0)*split[0] + shield.get(a, 0)*split[1]

        return target, regime

    def enforce_decoupled_risk(self, weights):
        """La clé de la VF : Les limites ne brident que l'attaque."""
        attack_w = {k: v for k, v in weights.items() if k in ATTACK_ASSETS}
        defense_w = {k: v for k, v in weights.items() if k in DEFENSE_ASSETS}

        # Plafond par actif d'attaque
        attack_w = {k: min(v, MAX_POSITION_SIZE) for k, v in attack_w.items()}

        # Plafond Sectoriel
        sec_exp = {s: 0.0 for s in SECTORS.keys()}
        for t, w in attack_w.items():
            for s, tkrs in SECTORS.items():
                if t in tkrs: sec_exp[s] += w
                
        for s, exp in sec_exp.items():
            if exp > MAX_SECTOR_WEIGHT:
                for t in SECTORS[s]:
                    if t in attack_w: attack_w[t] *= (MAX_SECTOR_WEIGHT / exp)

        # Recombinaison & Normalisation Anti-Levier (98%)
        final = {**attack_w, **defense_w}
        tot = sum(final.values())
        if tot > 0:
            target_total = 1.0 - CASH_RESERVE
            final = {k: (v/tot)*target_total for k, v in final.items()}

        return {k: v for k, v in final.items() if v >= 0.01} # Nettoyage des poussières

    def execute_portfolio(self, target_weights, regime):
        logger.info("⚡ Entering Execution Engine...")
        self.api.cancel_all_orders()
        
        acc = self.api.get_account()
        equity = float(acc.equity)
        positions = {p.symbol: float(p.market_value) for p in self.api.list_positions()}
        trades = []

        # 1. PHASE DE VENTE (Libérer le capital)
        for sym, c_val in positions.items():
            t_val = equity * target_weights.get(sym, 0)
            drift = (c_val/equity) - target_weights.get(sym, 0)
            
            if drift > 0.03 or target_weights.get(sym, 0) == 0:
                diff = c_val - t_val
                try:
                    price = float(self.api.get_latest_trade(sym).price)
                    qty = round(diff / price, 4)
                    if qty > 0.001:
                        if not PAPER_TRADING: 
                            self.api.submit_order(sym, qty=qty, side='sell', type='market', time_in_force='day')
                        trades.append(f"🔴 SOLD {qty} {sym}")
                except Exception as e: logger.error(f"Sell error on {sym}: {e}")

        time.sleep(5) # Attente du règlement (Settlement)

        # 2. PHASE D'ACHAT (Fractionnel)
        bp = float(self.api.get_account().buying_power)
        for sym, w in target_weights.items():
            t_val = equity * w
            c_val = positions.get(sym, 0)
            
            if w - (c_val/equity) > 0.03:
                notional = min(round(t_val - c_val, 2), bp - 5.0) # Garde $5 de marge
                if notional > 10:
                    try:
                        if not PAPER_TRADING: 
                            self.api.submit_order(sym, notional=notional, side='buy', type='market', time_in_force='day')
                        trades.append(f"🟢 BOUGHT ${notional} of {sym}")
                        bp -= notional
                    except Exception as e: logger.error(f"Buy error on {sym}: {e}")

        self.reporter.send_report(regime, trades, target_weights)

    def run_cycle(self):
        logger.info("🚀 Starting AEGIS VF Cycle...")
        
        if not self.check_intraday_drawdown():
            self.reporter.send_report("CIRCUIT BREAKER", [], {}, cb_alert=True)
            return

        df = self.get_market_data()
        if df.empty: return

        # Calcul Cibles -> Limites -> Exécution
        raw_target, regime = self.calculate_allocation(df)
        final_target = self.enforce_decoupled_risk(raw_target)
        self.execute_portfolio(final_target, regime)

#RUNNER 

if __name__ == "__main__":
    bot = AegisEngine()
    
    # Rebalancement tous les vendredis à 21h45 (Heure de Paris = 15h45 NY)
    schedule.every().friday.at("21:45").do(bot.run_cycle)
    
    logger.info("="*50)
    logger.info(f"✅ AEGIS PRIME VF (GOLD STANDARD) ONLINE.")
    logger.info(f"⚙️ Mode: {'🧪 PAPER TRADING' if PAPER_TRADING else '🔴 LIVE TRADING'}")
    logger.info("="*50)
    
    while True:
        schedule.run_pending()
        time.sleep(10)
