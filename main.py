import os, time, logging, json, requests, io, schedule
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import alpaca_trade_api as tradeapi
from alpaca_trade_api.rest import TimeFrame
from mistralai import Mistral
from dotenv import load_dotenv

# CONFIGURATION & ENVIRONMENT
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.FileHandler("aegis_core.log"), logging.StreamHandler()]
)
logger = logging.getLogger("AEGIS_CORE")

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


# REPORTING MODULE & AI ANALYST

class DiscordReporter:
    def __init__(self, api, webhook_url):
        self.api = api
        self.webhook_url = webhook_url
        self.mistral_key = os.getenv("MISTRAL_API_KEY")
        self.ai_client = Mistral(api_key=self.mistral_key) if self.mistral_key else None

    def get_ai_risk_scores(self, target_weights):
        """Demande à Mistral de moduler les poids selon le risque macro actuel"""
        if not self.ai_client:
            return {k: 1.0 for k in target_weights.keys()}

        tickers = list(target_weights.keys())
        prompt = f"""
        You are the Chief Risk Officer at a quant hedge fund. Assess the current qualitative/news risk for these assets: {tickers}.
        Provide a risk multiplier for each asset between 0.5 (high risk/bad news -> reduce allocation) and 1.5 (strong momentum/good news -> increase allocation). 1.0 is neutral.
        You MUST respond ONLY with a valid JSON dictionary containing the tickers as keys and the float multipliers as values. Nothing else.
        Example: {{"AAPL": 1.0, "GLD": 1.2, "TSLA": 0.8}}
        """
        try:
            response = self.ai_client.chat.complete(
                model="mistral-tiny",
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.choices[0].message.content
            
            # Nettoyage du JSON au cas où l'IA rajoute des balises Markdown
            if "```json" in content: content = content.split("```json")[1].split("```")[0]
            elif "```" in content: content = content.split("```")[1].split("```")[0]
            
            scores = json.loads(content)
            
            # Sécurité: Forcer les limites entre 0.5 et 1.5 pour éviter les dérives
            final_scores = {}
            for t in tickers:
                raw_score = float(scores.get(t, 1.0))
                final_scores[t] = max(0.5, min(1.5, raw_score))
            
            logger.info(f"🧠 AI Multipliers Generated: {final_scores}")
            return final_scores
        except Exception as e:
            logger.error(f"AI Risk Scoring Failed (Fallback to 1.0): {e}")
            return {k: 1.0 for k in target_weights.keys()}

    def get_ai_briefing(self, regime, split_desc, target_weights):
        if not self.ai_client:
            return "*AI not configured (Missing Mistral API Key).*"
        
        assets_str = ", ".join(target_weights.keys()) if target_weights else "CASH"
        prompt = f"""
        You are the Senior Portfolio Manager at AEGIS PRIME, a quantitative fund.
        CONTEXT:
        - Market Regime: {regime}
        - Strategy Split: {split_desc}
        - Target Allocation: {assets_str}
        
        TASK:
        Write a very concise, professional briefing (max 3 sentences) for the fund's investors.
        Explain WHY this specific allocation was chosen given the current regime.
        Use institutional financial terminology. Do not use greetings.
        """
        try:
            response = self.ai_client.chat.complete(
                model="mistral-tiny",
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"AI Analysis Error: {e}")
            return "*AI Analysis temporarily unavailable.*"

    def send_report(self, regime, split_desc, trades, weights):
        if not self.webhook_url: return
        try:
            acc = self.api.get_account()
            hist = self.api.get_portfolio_history(period="1M", timeframe="1D")
            df = pd.DataFrame({'equity': hist.equity}, index=pd.to_datetime(hist.timestamp, unit='s'))
            
            rets = df['equity'].pct_change().dropna()
            sharpe = (rets.mean() / rets.std()) * np.sqrt(252) if len(rets) > 2 else 0
            
            plt.style.use('dark_background')
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.plot(df.index, df['equity'], color='#00FFAA', lw=2)
            ax.set_title(f"Portfolio Performance | Sharpe: {sharpe:.2f}")
            ax.grid(alpha=0.1)
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png', facecolor='#0E1117')
            buf.seek(0)

            ai_comment = self.get_ai_briefing(regime, split_desc, weights)
            display_weights = {k: f"{v:.1%}" for k, v in weights.items() if v > 0}
            
            payload = {
                "embeds": [{
                    "title": "🛡️ AEGIS PRIME | STRATEGY REPORT",
                    "color": 0x00FFAA,
                    "description": f"**Net Equity**: `${float(acc.equity):,.2f}`",
                    "fields": [
                        {"name": "🧠 AI Analyst (Mistral)", "value": f"_{ai_comment}_", "inline": False},
                        {"name": "🌍 Regime", "value": f"`{regime}`", "inline": True},
                        {"name": "⚙️ Model", "value": f"`{split_desc}`", "inline": True},
                        {"name": "🔭 Target Allocation", "value": f"```json\n{json.dumps(display_weights, indent=2)}\n```"},
                        {"name": "⚡ Trades Executed", "value": "\n".join(trades) if trades else "No rebalance needed."}
                    ],
                    "footer": {"text": "Aegis Prime Kernel V25.1 • Fractional & AI Module"}
                }]
            }
            requests.post(self.webhook_url, data={'payload_json': json.dumps(payload)}, files={'file': ('chart.png', buf, 'image/png')})
            logger.info("✅ Discord Report Transmitted.")
        except Exception as e: logger.error(f"Report Error: {e}")


# TRADING ENGINE

class AegisEngine:
    def __init__(self):
        self.api = tradeapi.REST(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), os.getenv("ALPACA_BASE_URL"), 'v2')
        self.reporter = DiscordReporter(self.api, os.getenv("DISCORD_WEBHOOK_URL"))

    def get_market_data(self):
        end = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        start = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        try:
            bars = self.api.get_bars(ALL_TICKERS, TimeFrame.Day, start=start, end=end, adjustment='all').df
            if bars.empty: return pd.DataFrame()
            return bars.pivot_table(index='timestamp', columns='symbol', values='close').ffill()
        except Exception as e:
            logger.error(f"Data Error: {e}")
            return pd.DataFrame()

    def get_growth_target(self, df):
        if df['SPY'].iloc[-1] < df['SPY'].rolling(200).mean().iloc[-1]:
            return {'GLD': 0.4, 'TLT': 0.4, 'SHV': 0.2}
        
        mom = (df.iloc[-1] / df.iloc[-126]) - 1
        vol = df.pct_change().rolling(60).std().iloc[-1]
        score = (mom / vol).reindex(ATTACK_ASSETS).dropna().sort_values(ascending=False).head(5)
        return {s: 1.0/len(score) for s in score.index}

    def get_shield_target(self, df):
        vol = df.pct_change().rolling(60).std().iloc[-1]
        mom = (df.iloc[-1] / df.iloc[-126]) - 1
        score = (mom / vol).reindex(ATTACK_ASSETS).dropna().sort_values(ascending=False).head(6)
        inv_v = 1 / vol[score.index]
        return {k: v/inv_v.sum() for k, v in inv_v.items()}

    def execute_portfolio(self, target_weights, regime, split_desc):
        logger.info("⚡ Entering Fractional Execution Engine...")
        try:
            # Annulation des ordres bloqués
            self.api.cancel_all_orders()
            logger.info("🧹 Cleared pending orders.")
            
            acc = self.api.get_account()
            equity = float(acc.equity)
            positions = {p.symbol: float(p.market_value) for p in self.api.list_positions()}
            trades = []

            # Ventes (Libération de capital)
            for sym, curr_val in positions.items():
                target_val = equity * target_weights.get(sym, 0)
                if target_val < curr_val * 0.90:
                    diff = curr_val - target_val
                    try:
                        price = float(self.api.get_latest_trade(sym).price)
                        qty = round(diff / price, 4)
                        if qty > 0.001:
                            self.api.submit_order(symbol=sym, qty=qty, side='sell', type='market', time_in_force='day')
                            trades.append(f"🔴 SOLD {qty} {sym}")
                    except: pass

            time.sleep(3) # Pause pour s'assurer que le cash est dispo

            # Achats (Fractionné)
            for sym, w in target_weights.items():
                target_val = equity * w
                curr_val = positions.get(sym, 0)
                if target_val > curr_val + 5: # Seuil minimum $5
                    notional = round(target_val - curr_val, 2)
                    try:
                        self.api.submit_order(symbol=sym, notional=notional, side='buy', type='market', time_in_force='day')
                        trades.append(f"🟢 BOUGHT ${notional} of {sym}")
                        logger.info(f"🟢 Executed: ${notional} {sym}")
                    except Exception as e: logger.error(f"Buy Error {sym}: {e}")

            self.reporter.send_report(regime, split_desc, trades, target_weights)
        except Exception as e: logger.error(f"Engine Crash: {e}")

    def run_cycle(self):
        logger.info("🚀 Starting Trading Cycle...")
        df = self.get_market_data()
        if df.empty: return
        
        # 1. Régime Mathématique
        spy_vol = df['SPY'].pct_change().rolling(21).std().iloc[-1] * np.sqrt(252)
        if spy_vol < 0.18: split = [0.9, 0.1]; regime = "AGGRESSIVE (Low Vol)"
        elif spy_vol > 0.28: split = [0.2, 0.8]; regime = "DEFENSIVE (High Vol)"
        else: split = [0.5, 0.5]; regime = "BALANCED (Normal Vol)"

        t_growth = self.get_growth_target(df)
        t_shield = self.get_shield_target(df)
        
        # 2. Allocation Quantitative Initiale
        base_target = {}
        all_assets = set(list(t_growth.keys()) + list(t_shield.keys()))
        for a in all_assets:
            w = (t_growth.get(a, 0) * split[0]) + (t_shield.get(a, 0) * split[1])
            if w > 0.02: base_target[a] = w
            
        # 3. INTERVENTION DE L'IA (Modulation des pondérations)
        logger.info("🧠 Requesting AI Risk adjustment from Mistral...")
        ai_multipliers = self.reporter.get_ai_risk_scores(base_target)
        
        final_target = {}
        for a in base_target:
            # On applique le multiplicateur (0.5 à 1.5) défini par l'IA
            final_target[a] = base_target[a] * ai_multipliers.get(a, 1.0)
            
        # 4. Normalisation de Sécurité Finale (Buffer de 98%)
        total = sum(final_target.values())
        if total > 0: 
            final_target = {k: (v/total) * 0.98 for k, v in final_target.items()}
        
        self.execute_portfolio(final_target, regime, f"{int(split[0]*100)}% G / {int(split[1]*100)}% S")

    def watchdog(self):
        try:
            for p in self.api.list_positions():
                if float(p.unrealized_intraday_plpc) < -0.05:
                    self.api.close_position(p.symbol)
                    logger.warning(f"🚨 CRASH PROTECTION: Liquidated {p.symbol}")
        except: pass

# RUNNER

if __name__ == "__main__":
    bot = AegisEngine()
    schedule.every().friday.at("21:45").do(bot.run_cycle)
    schedule.every(1).minutes.do(bot.watchdog)
    
    logger.info("✅ AEGIS PRIME V25.1 ONLINE. Awaiting schedule...")
    while True:
        schedule.run_pending()
        time.sleep(10)
