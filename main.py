import os, time, logging, json, requests, io, schedule, pytz
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
import alpaca_trade_api as tradeapi
from alpaca_trade_api.rest import TimeFrame
from mistralai import Mistral
from dotenv import load_dotenv
from functools import wraps

#SYSTEM INITIALIZATION
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s',
                    handlers=[logging.FileHandler("aegis_production.log"), logging.StreamHandler()])
logger = logging.getLogger("AEGIS_KERNEL")
NY_TZ = pytz.timezone('US/Eastern')

#CONFIGURATION & LIMITES INSTITUTIONNELLES
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"
MAX_SECTOR_WEIGHT = 0.25  # 25% max par secteur offensif
MAX_POSITION_SIZE = 0.08  # 8% max par actif offensif
CASH_RESERVE = 0.02       # 2% de cash permanent (Anti-Levier garanti)

# Univers issu du Backtest V3 (CAGR 25%, Sharpe 1.54)
SECTORS = {
    'Technology': ['NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'AAPL', 'TSLA', 'SMH'],
    'Healthcare': ['LLY', 'UNH'],
    'Industrials': ['ITA', 'XLI', 'RTX'],
    'Commodities': ['XLE', 'COPX', 'URA'],
    'Alpha': ['IBIT']
}
ATTACK_ASSETS = [t for sub in SECTORS.values() for t in sub]
DEFENSE_ASSETS = ['GLD', 'TLT', 'SHV']
UNIVERSE = list(set(ATTACK_ASSETS + DEFENSE_ASSETS + ['SPY']))


#UTILITAIRES & REPORTING
def retry_network(max_retries=3):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(max_retries):
                try: return func(*args, **kwargs)
                except Exception as e: 
                    logger.warning(f"Network retry {i+1}/{max_retries} due to: {e}")
                    time.sleep(2 ** i)
            raise Exception(f"Network function failed after {max_retries} attempts.")
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
        
        # Génération du graphique de performance
        try:
            hist = self.api.get_portfolio_history(period="1M", timeframe="1D")
            df = pd.DataFrame({'equity': hist.equity}, index=pd.to_datetime(hist.timestamp, unit='s', utc=True)).dropna()
            sharpe = (df['equity'].pct_change().mean() / df['equity'].pct_change().std()) * np.sqrt(252) if len(df)>2 else 0

            plt.style.use('dark_background')
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(df.index, df['equity'], color='#FF3B30' if cb_alert else '#00E676', lw=2.5)
            ax.fill_between(df.index, df['equity'], df['equity'].min() * 0.99, color='#FF3B30' if cb_alert else '#00E676', alpha=0.1)
            ax.set_title(f"Aegis Prime 30-Day Performance | Live Sharpe: {sharpe:.2f}", color='white', fontsize=12)
            ax.grid(color='#333333', linestyle='--', alpha=0.5)
            buf = io.BytesIO(); plt.savefig(buf, format='png', facecolor='#0B0E14', bbox_inches='tight'); buf.seek(0); plt.close(fig)
            has_chart = True
        except Exception as e:
            logger.error(f"Chart generation failed: {e}")
            has_chart = False

        # IA Insights
        ai_msg = "🚨 CIRCUIT BREAKER: TRADING HALTED DUE TO RAPID INTRADAY DRAWDOWN." if cb_alert else "Strategic portfolio rotation executed based on volatility factors."
        if self.ai and not cb_alert:
            try:
                top_w = ", ".join([f"{k} ({v:.0%})" for k, v in weights.items() if v > 0.05])
                prompt = f"Market Regime: {regime}. Key Holdings: {top_w}. Write 2 concise sentences explaining this institutional allocation. Professional tone. No greetings."
                ai_msg = self.ai.chat.complete(model="mistral-tiny", messages=[{"role":"user","content":prompt}]).choices[0].message.content
            except: pass

        # Construction du Webhook
        embed = {
            "title": "🛡️ AEGIS PRIME VF | EXECUTIVE REPORT" + (" [HALTED]" if cb_alert else ""),
            "color": 0xFF3B30 if cb_alert else 0x00E676,
            "description": f"**Net Liquidity**: `${float(acc.equity):,.2f}` | **Mode**: `{'PAPER (SIMULATION)' if PAPER_TRADING else 'LIVE (REAL CAPITAL)'}`",
            "fields": [
                {"name": "🤖 AI Market Analysis", "value": f"_{ai_msg}_", "inline": False},
                {"name": "🌍 Macro Regime", "value": f"`{regime}`", "inline": False},
                {"name": "🎯 Target Allocation Map", "value": f"```json\n{json.dumps({k: f'{v:.1%}' for k,v in weights.items() if v > 0.01}, indent=2)}\n```"},
                {"name": "⚡ Execution Tape", "value": "\n".join(trades) if trades else "No rebalance needed (Inside drift tolerance)."}
            ],
            "footer": {"text": "Aegis Prime Kernel • Decoupled Risk Standard"}
        }
        
        payload = {'payload_json': json.dumps({"embeds": [embed]})}
        if has_chart:
            res = requests.post(self.webhook_url, data=payload, files={'file': ('chart.png', buf, 'image/png')})
        else:
            res = requests.post(self.webhook_url, json={"embeds": [embed]})
            
        if res.status_code >= 400:
            logger.error(f"❌ Erreur Discord API ({res.status_code}): {res.text}")
        else:
            logger.info("✅ Discord institutional report broadcasted.")


#MOTEUR QUANTITATIF & EXÉCUTION
class AegisEngine:
    def __init__(self):
        self.api = tradeapi.REST(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), os.getenv("ALPACA_BASE_URL"), 'v2')
        self.reporter = DiscordReporter(self.api, os.getenv("DISCORD_WEBHOOK_URL"))

    def check_intraday_drawdown(self):
        """Intraday Circuit Breaker: Freezes trading if the portfolio drops > 10% today."""
        try:
            hist = self.api.get_portfolio_history(period="1D", timeframe="15Min")
            if not hist.equity: return True
            current_equity = float(self.api.get_account().equity)
            dd = (current_equity - hist.equity[0]) / hist.equity[0]
            if dd < -0.10:
                logger.critical(f"🚨 CIRCUIT BREAKER: Daily drawdown {dd:.1%} exceeds limit.")
                return False
            return True
        except: return True

    @retry_network()
    def get_market_data(self):
        """Ingests historical data using yfinance for superior adjustment/split handling."""
        logger.info("📥 Fetching global market matrix...")
        start_date = (datetime.now(NY_TZ) - timedelta(days=400)).strftime('%Y-%m-%d')
        df = yf.download(UNIVERSE, start=start_date, auto_adjust=True, progress=False)['Close']
        if 'IBIT' in df.columns: 
            # Proxy mapping for missing crypto ETF data
            df['IBIT'] = df['IBIT'].bfill()
        return df.ffill().dropna(thresh=10)

    def calculate_allocation(self, df):
        """Core Mathematical Engine"""
        spy = df['SPY']
        spy_sma200 = spy.rolling(200).mean().iloc[-1]
        spy_vol = spy.pct_change().tail(21).std() * np.sqrt(252)

        # 1. MACRO BUNKER (Priority Override)
        if spy.iloc[-1] < spy_sma200:
            logger.warning("🐻 SPY < 200 SMA: BUNKER MODE ACTIVATED")
            return {'GLD': 0.40, 'TLT': 0.40, 'SHV': 0.20}, "BEAR MARKET (BUNKER MODE)"

        # 2. VOLATILITY REGIMES
        if spy_vol < 0.15: split = [0.90, 0.10]; regime = "BULL AGGRESSIVE (Low Vol)"
        elif spy_vol > 0.25: split = [0.20, 0.80]; regime = "BULL DEFENSIVE (High Vol)"
        else: split = [0.50, 0.50]; regime = "BULL NORMAL (Mid Vol)"

        mom = (df.iloc[-1] / df.iloc[-126]) - 1
        vol = df.pct_change().rolling(60).std().iloc[-1] * np.sqrt(252)

        # 3. GROWTH ENGINE (Risk-Adjusted Momentum)
        g_score = (mom / vol).reindex(ATTACK_ASSETS).dropna().sort_values(ascending=False).head(5)
        
        # Risk Parity Inverse Vol weighting for Attack
        vols_attack = df[g_score.index].pct_change().tail(60).std()
        inv_vols_attack = 1.0 / vols_attack.replace(0, np.nan).fillna(1.0)
        attack_w = inv_vols_attack / inv_vols_attack.sum()

        target = {}
        for t in g_score.index:
            target[t] = attack_w[t] * split[0]
            
        # 4. SHIELD ENGINE (Asymmetric Defense)
        target['GLD'] = 0.5 * split[1]
        target['TLT'] = 0.5 * split[1]

        return target, regime

    def enforce_decoupled_risk(self, weights):
        """The key to the VF: Limits only choke Attack assets, Defense is uncapped."""
        attack_w = {k: v for k, v in weights.items() if k in ATTACK_ASSETS}
        defense_w = {k: v for k, v in weights.items() if k in DEFENSE_ASSETS}

        # Asset Cap
        attack_w = {k: min(v, MAX_POSITION_SIZE) for k, v in attack_w.items()}

        # Sector Cap
        sec_exp = {s: 0.0 for s in SECTORS.keys()}
        for t, w in attack_w.items():
            for s, tkrs in SECTORS.items():
                if t in tkrs: sec_exp[s] += w
                
        for s, exp in sec_exp.items():
            if exp > MAX_SECTOR_WEIGHT:
                for t in SECTORS[s]:
                    if t in attack_w: attack_w[t] *= (MAX_SECTOR_WEIGHT / exp)

        # Recombination & Anti-Leverage Normalization (Max 98% Gross)
        final = {**attack_w, **defense_w}
        tot = sum(final.values())
        if tot > 0:
            target_total = 1.0 - CASH_RESERVE
            final = {k: (v/tot)*target_total for k, v in final.items()}

        return {k: v for k, v in final.items() if v >= 0.01}

    def execute_portfolio(self, target_weights, regime):
        logger.info("⚡ Entering Execution Routing...")
        self.api.cancel_all_orders()
        
        acc = self.api.get_account()
        equity = float(acc.equity)
        # On récupère la valeur ET la quantité réelle exacte possédée
        pos_data = {p.symbol: {"val": float(p.market_value), "qty": float(p.qty)} for p in self.api.list_positions()}
        trades = []

        # 1. SELL PHASE (Freeing Capital)
        for sym, p_info in pos_data.items():
            c_val = p_info["val"]
            c_qty = p_info["qty"]
            t_val = equity * target_weights.get(sym, 0)
            drift = (c_val/equity) - target_weights.get(sym, 0)
            
            if drift > 0.03 or target_weights.get(sym, 0) == 0:
                diff = c_val - t_val
                try:
                    if target_weights.get(sym, 0) == 0:
                        self.api.close_position(sym)
                        trades.append(f"🔴 LIQUIDATED {sym}")
                    else:
                        price = float(self.api.get_latest_trade(sym).price)
                        # On s'assure de ne jamais vendre plus que la quantité possédée
                        qty = min(round(diff / price, 4), c_qty)
                        if qty > 0.001:
                            self.api.submit_order(sym, qty=qty, side='sell', type='market', time_in_force='day')
                            trades.append(f"🔴 SOLD ~${diff:,.0f} of {sym}")
                except Exception as e: logger.error(f"Sell error on {sym}: {e}")

        time.sleep(5) # Wait for Alpaca settlement

        # 2. BUY PHASE (Notional Routing)
        bp = float(self.api.get_account().buying_power)
        for sym, w in target_weights.items():
            t_val = equity * w
            c_val = pos_data.get(sym, {}).get("val", 0)
            
            if w - (c_val/equity) > 0.03:
                # Arrondi strict à 2 décimales pour l'API Alpaca
                notional = round(min(t_val - c_val, bp - 5.0), 2)
                if notional > 10:
                    try:
                        self.api.submit_order(sym, notional=notional, side='buy', type='market', time_in_force='day')
                        trades.append(f"🟢 BOUGHT ${notional:,.0f} of {sym}")
                        bp -= notional
                    except Exception as e: logger.error(f"Buy error on {sym}: {e}")

        self.reporter.send_report(regime, trades, target_weights)

    def run_cycle(self):
        logger.info("="*50)
        logger.info("🚀 INITIATING AEGIS PRIME CYCLE")
        
        if not self.check_intraday_drawdown():
            self.reporter.send_report("CIRCUIT BREAKER", [], {}, cb_alert=True)
            return

        df = self.get_market_data()
        if df.empty: 
            logger.error("Market data missing. Aborting cycle.")
            return

        raw_target, regime = self.calculate_allocation(df)
        final_target = self.enforce_decoupled_risk(raw_target)
        self.execute_portfolio(final_target, regime)
        logger.info("CYCLE COMPLETE.")

#RUNNER
if __name__ == "__main__":
    bot = AegisEngine()
    
    logger.info("="*50)
    logger.info(f"✅ AEGIS PRIME VF (GOLD STANDARD) ONLINE.")
    logger.info(f"⚙️ Mode: {'🧪 PAPER TRADING' if PAPER_TRADING else '🔴 LIVE TRADING'}")
    logger.info("="*50)
    
    # Scheduling standard: 21:45 Paris time = 15:45 NY Time (Weekly rebalance)
    schedule.every().friday.at("15:45").do(bot.run_cycle)
    
    while True:
        schedule.run_pending()
        time.sleep(60)
