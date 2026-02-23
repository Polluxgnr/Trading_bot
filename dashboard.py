import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import alpaca_trade_api as tradeapi
import yfinance as yf
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# 1 PAGE CONFIGURATION
st.set_page_config(page_title="Pollux's bot | Command Center", layout="wide", page_icon="🛡️")

# 2 CUSTOM STYLING & DESIGN
st.markdown("""
<style>
    .metric-box { background-color: #151A22; padding: 20px; border-radius: 10px; border-left: 5px solid #00E676; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3); }
    .metric-title { color: #8B949E; font-size: 14px; text-transform: uppercase; letter-spacing: 1px;}
    .metric-value { color: #FFFFFF; font-size: 28px; font-weight: bold; margin-top: 5px; }
    .metric-sub { color: #00E676; font-size: 13px; margin-top: 5px; font-weight: 500;}
    .header-links a { color: #00E676; text-decoration: none; margin-right: 15px; font-weight: bold; }
    .header-links a:hover { text-decoration: underline; }
    .mistral-box { background-color: #0E1117; border: 1px solid #30363D; border-radius: 8px; padding: 15px; margin-bottom: 20px; border-left: 3px solid #AF52DE;}
    .info-text { color: #A3B3BC; font-size: 14px; font-style: italic; margin-bottom: 15px; }
</style>
""", unsafe_allow_html=True)

# 3 SECTOR MAPPING
SECTOR_MAP = {
    'NVDA': 'Technology', 'MSFT': 'Technology', 'GOOGL': 'Technology', 'AMZN': 'Technology', 
    'META': 'Technology', 'AAPL': 'Technology', 'TSLA': 'Technology', 'SMH': 'Technology', 'QQQ': 'Technology',
    'LLY': 'Healthcare', 'UNH': 'Healthcare', 
    'ITA': 'Industrials', 'XLI': 'Industrials', 'RTX': 'Industrials', 
    'XLE': 'Commodities', 'COPX': 'Commodities', 'URA': 'Commodities', 
    'IBIT': 'Alpha (Crypto)', 'BTC-USD': 'Alpha (Crypto)',
    'GLD': 'Defense (Gold)', 'TLT': 'Defense (Bonds)', 'SHV': 'Defense (Cash)', 'SPY': 'Broad Market',
    'CASH (Reserve)': 'Cash Reserve'
}

# 4 HEADER & LINKS
st.markdown("<h1>🛡️ Pollux's trading bot</h1>", unsafe_allow_html=True)
st.markdown("""
<div class="header-links">
    <a href="https://github.com/Polluxgnr/Trading_bot" target="_blank">🔗 GitHub Repository</a> | 
    <a href="https://polluxgronier.me" target="_blank">💼 Portfolio</a>
</div><br>
""", unsafe_allow_html=True)

# 5 API INITIALIZATION
load_dotenv()
try:
    api = tradeapi.REST(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), os.getenv("ALPACA_BASE_URL"), 'v2')
    account = api.get_account()
except Exception as e:
    st.error(f"API Connection Failed: {e}. Check your .env credentials.")
    st.stop()

# LANGUAGE TOGGLE
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/000000/shield.png", width=50)
    lang = st.radio("🌐 Interface Language", ['🇬🇧 English', '🇫🇷 Français'])
    is_fr = lang == '🇫🇷 Français'
    st.write("---")

# 6 ROBUST CACHING FUNCTIONS
@st.cache_data(ttl=300) 
def fetch_portfolio_history(period="1M"):
    try:
        hist = api.get_portfolio_history(period=period, timeframe="1D")
        df = pd.DataFrame({'equity': hist.equity}, index=pd.to_datetime(hist.timestamp, unit='s', utc=True))
        df.index = df.index.tz_convert('US/Eastern')
        # Filter out $0 starting points from unfunded Alpaca accounts
        return df[df['equity'] > 0].dropna()
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_radar_data(universe, start_d):
    try:
        df = yf.download(universe, start=start_d, progress=False)['Close']
        return df.ffill().dropna(thresh=10)
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_trade_activities():
    try:
        acts = api.get_activities(activity_types='FILL')
        return [{"symbol": a.symbol, "side": a.side, "qty": float(a.qty), "price": float(a.price), "date": str(a.transaction_time)} for a in acts]
    except Exception:
        return []

@st.cache_data(ttl=3600)
def generate_mistral_insight(top_holdings_str):
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key: return "Mistral API Key missing. Analysis disabled."
    try:
        from mistralai import Mistral
        client = Mistral(api_key=api_key)
        prompt = f"Act as a quantitative hedge fund manager. My current top holdings are: {top_holdings_str}. Write exactly 2 concise sentences explaining this specific allocation and market stance. Professional and institutional tone only."
        response = client.chat.complete(model="mistral-tiny", messages=[{"role":"user","content":prompt}])
        return response.choices[0].message.content
    except Exception:
        return f"Mistral Analysis unavailable at this time."
    
@st.cache_data(ttl=3600)
def get_recent_news(symbol):
    try:
        news_data = yf.Ticker(symbol).news[:3]
        parsed_news = []
        for n in news_data:
            # Nouvelle structure Yahoo Finance (imbriquée dans 'content')
            if 'content' in n:
                content = n['content']
                title = content.get('title', 'No Title')
                link = content.get('clickThroughUrl', {}).get('url', '#')
                date_str = content.get('pubDate', '')
                pub_time = date_str[:10] if date_str else "Recent"
            # Ancienne structure Yahoo Finance (plate)
            else:
                title = n.get('title', 'No Title')
                link = n.get('link', '#')
                pub_time_raw = n.get('providerPublishTime')
                try:
                    pub_time = datetime.fromtimestamp(pub_time_raw).strftime('%Y-%m-%d') if pub_time_raw else "Recent"
                except:
                    pub_time = "Recent"
            
            # On ne garde que les articles valides
            if title != 'No Title':
                parsed_news.append({'title': title, 'link': link, 'date': pub_time})
        return parsed_news
    except Exception:
        return []

def get_system_logs(lines=15):
    try:
        with open("aegis_production.log", "r") as f:
            return "".join(f.readlines()[-lines:])
    except FileNotFoundError:
        return "Log file not found." if not is_fr else "Fichier journal introuvable."

# 7 TOP METRICS & MISTRAL AI
equity = float(account.equity)
cash = float(account.cash)

# Calculate All-Time Net Profit securely
df_all = fetch_portfolio_history(period="all")
if not df_all.empty and len(df_all) > 0:
    base_equity = df_all['equity'].iloc[0]
    net_profit_dol = equity - base_equity
    net_profit_pct = (net_profit_dol / base_equity) * 100
else:
    net_profit_dol, net_profit_pct = 0.0, 0.0

c1, c2, c3, c4 = st.columns(4)
with c1: st.markdown(f'<div class="metric-box"><div class="metric-title">Net Liquidity</div><div class="metric-value">${equity:,.2f}</div></div>', unsafe_allow_html=True)
with c2: st.markdown(f'<div class="metric-box"><div class="metric-title">Cash Reserve</div><div class="metric-value">${cash:,.2f}</div></div>', unsafe_allow_html=True)
with c3: st.markdown(f'<div class="metric-box"><div class="metric-title">All-Time Net Profit</div><div class="metric-value">${net_profit_dol:,.2f}</div><div class="metric-sub" style="color:{"#00E676" if net_profit_pct>=0 else "#FF3B30"}">{net_profit_pct:+.2f}%</div></div>', unsafe_allow_html=True)
with c4:
    mode = "🔴 LIVE" if "paper" not in os.getenv("ALPACA_BASE_URL", "paper") else "🧪 PAPER"
    st.markdown(f'<div class="metric-box" style="border-left-color: #007AFF;"><div class="metric-title">System Status</div><div class="metric-value">{mode}</div><div class="metric-sub">Zero Leverage Enforced</div></div>', unsafe_allow_html=True)

st.write("")

# Mistral AI Block
positions = api.list_positions()
top_symbols = ", ".join([p.symbol for p in sorted(positions, key=lambda x: float(x.market_value), reverse=True)[:5]]) if positions else "100% Cash"
mistral_text = generate_mistral_insight(top_symbols)

st.markdown(f"""
<div class="mistral-box">
    <div style="color: #AF52DE; font-weight: bold; font-size: 14px; margin-bottom: 5px;">🤖 MISTRAL AI • LIVE PORTFOLIO INSIGHT</div>
    <div style="color: #C9D1D9; font-size: 15px; font-style: italic;">"{mistral_text}"</div>
</div>
""", unsafe_allow_html=True)

# 8 NAVIGATION TABS
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📈 Live Performance" if not is_fr else "📈 Performance en Direct", 
    "🎯 Portfolio & Allocation" if not is_fr else "🎯 Portefeuille & Allocation", 
    "🏆 Extremes & Alpha",
    "🧾 Execution & News" if not is_fr else "🧾 Exécution & Actualités",
    "🔮 Monte Carlo", 
    "📡 Global Radar" if not is_fr else "📡 Radar Global",
    "🧠 Strategy Deep Dive" if not is_fr else "🧠 Stratégie Détaillée"
])

# ==========================================
# TAB 1: LIVE PERFORMANCE & DRAWDOWN
# ==========================================
with tab1:
    st.subheader("Account Evolution Tracker (Percentage Growth)" if not is_fr else "Évolution du Compte (Croissance en %)")
    
    desc_tab1 = "Track the live equity curve and risk metrics of your portfolio. The Drawdown chart below highlights the distance from the all-time high, allowing you to monitor the algorithm's resilience during market corrections." if not is_fr else "Suivez la courbe de performance et les métriques de risque de votre portefeuille. Le graphique de Drawdown ci-dessous met en évidence la chute depuis le dernier sommet historique, permettant d'évaluer la résilience de l'algorithme."
    st.markdown(f"<div class='info-text'>{desc_tab1}</div>", unsafe_allow_html=True)

    timeframes = {"1 Week": "1W", "1 Month": "1M", "3 Months": "3M", "1 Year": "1A", "All Time": "all"} if not is_fr else {"1 Semaine": "1W", "1 Mois": "1M", "3 Mois": "3M", "1 An": "1A", "Tout l'historique": "all"}
    tf_sel = st.radio("Select Period:" if not is_fr else "Sélectionner la Période :", list(timeframes.keys()), horizontal=True, index=4)
    
    df_hist = fetch_portfolio_history(period=timeframes[tf_sel])
    if not df_hist.empty and len(df_hist) > 1:
        df_hist['pct_growth'] = (df_hist['equity'] / df_hist['equity'].iloc[0] - 1) * 100
        
        peak = df_hist['equity'].cummax()
        drawdown = (df_hist['equity'] / peak - 1) * 100
        max_dd = drawdown.min()
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_hist.index, y=df_hist['pct_growth'], 
            mode='lines', line=dict(color='#00E676', width=3), 
            fill='tozeroy', fillcolor='rgba(0, 230, 118, 0.1)',
            hovertemplate='%{x|%Y-%m-%d %H:%M}<br>Growth: %{y:.2f}%<extra></extra>' if not is_fr else '%{x|%d/%m/%Y %H:%M}<br>Croissance: %{y:.2f}%<extra></extra>'
        ))
        fig.update_layout(template='plotly_dark', plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis_title="", yaxis_title="Growth (%)" if not is_fr else "Croissance (%)", height=400, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)
        
        c1, c2, c3, c4 = st.columns(4)
        start_eq = df_hist['equity'].iloc[0]
        pl_dol = df_hist['equity'].iloc[-1] - start_eq
        c1.metric(f"Period P&L" if not is_fr else "P&L de la Période", f"${pl_dol:,.2f}", f"{(pl_dol / start_eq) * 100:.2f}%")
        
        daily_rets = df_hist['equity'].pct_change().dropna()
        if len(daily_rets) > 1 and daily_rets.std() > 0:
            c2.metric("Realized Volatility (Ann.)" if not is_fr else "Volatilité Réalisée (Ann.)", f"{daily_rets.std() * np.sqrt(252) * 100:.2f}%")
            c3.metric("Live Sharpe Ratio" if not is_fr else "Ratio de Sharpe Actuel", f"{(daily_rets.mean() / daily_rets.std()) * np.sqrt(252):.2f}")
        else:
            c2.metric("Realized Volatility (Ann.)" if not is_fr else "Volatilité Réalisée (Ann.)", "Calibrating..." if not is_fr else "Calibration...")
            c3.metric("Live Sharpe Ratio" if not is_fr else "Ratio de Sharpe Actuel", "Calibrating..." if not is_fr else "Calibration...")
        
        c4.metric("Max Drawdown", f"{max_dd:.2f}%")

        st.markdown("#### Stress Test: Historical Drawdown" if not is_fr else "#### Test de Résistance : Drawdown Historique")
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            x=drawdown.index, y=drawdown, 
            mode='lines', fill='tozeroy', 
            line=dict(color='#FF3B30', width=2), fillcolor='rgba(255, 59, 48, 0.2)',
            hovertemplate='DD: %{y:.2f}%<extra></extra>'
        ))
        fig_dd.update_layout(template='plotly_dark', height=200, margin=dict(t=10, b=10, l=0, r=0), yaxis=dict(title="Drawdown (%)", range=[min(-5.0, max_dd * 1.2), 0]))
        st.plotly_chart(fig_dd, use_container_width=True)
        
    else:
        st.info("Awaiting sufficient trading data to map the equity curve. If you just funded the account, the chart will appear tomorrow." if not is_fr else "En attente de données suffisantes pour tracer la courbe. Si le compte vient d'être financé, le graphique apparaîtra demain.")


# ==========================================
# TAB 2: PORTFOLIO MAP & ALLOCATION
# ==========================================
with tab2:
    st.subheader("Interactive Allocation Map" if not is_fr else "Carte d'Allocation Interactive")
    
    desc_tab2 = "Explore your portfolio's structure. The Sunburst and Treemap charts provide a multi-layered view, breaking down your exposure from Sector level down to specific Assets." if not is_fr else "Explorez la structure de votre portefeuille. Les graphiques Sunburst et Treemap offrent une vue multicouche, décomposant votre exposition du Secteur global jusqu'à l'Actif spécifique."
    st.markdown(f"<div class='info-text'>{desc_tab2}</div>", unsafe_allow_html=True)
    
    pos_data = [{"Symbol": "CASH", "Market Value ($)": cash, "Weight (%)": (cash/equity)*100, "Unrealized P&L ($)": 0.0, "Unrealized P&L (%)": 0.0, "Current Price": 1.0, "Avg Entry": 1.0, "Sector": "Cash Reserve"}]
    
    if positions:
        pos_data += [{"Symbol": p.symbol, "Market Value ($)": float(p.market_value), "Weight (%)": (float(p.market_value) / equity) * 100, "Unrealized P&L ($)": float(p.unrealized_pl), "Unrealized P&L (%)": float(p.unrealized_plpc) * 100, "Current Price": float(p.current_price), "Avg Entry": float(p.avg_entry_price), "Sector": SECTOR_MAP.get(p.symbol, 'Other')} for p in positions]
    
    df_pos = pd.DataFrame(pos_data)
    df_pos = df_pos.sort_values(by="Market Value ($)", ascending=False).reset_index(drop=True)
    
    active_pos_count = len(positions)
    top_sector = df_pos.groupby('Sector')['Market Value ($)'].sum().idxmax()
    top_asset = df_pos.iloc[0]['Symbol'] if active_pos_count > 0 else "CASH"
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Active Assets" if not is_fr else "Actifs en cours", f"{active_pos_count}")
    m2.metric("Dominant Sector" if not is_fr else "Secteur Dominant", top_sector)
    m3.metric("Largest Holding" if not is_fr else "Plus Grosse Position", top_asset)
    st.write("---")

    view_type = st.radio("Visualization Mode:" if not is_fr else "Mode de Visualisation :", ["Sunburst Chart (Multi-Layer)", "Nested Treemap (Heatmap)"], horizontal=True)
    
    hover_temp = '<b>%{label}</b><br>Value: $%{value:,.2f}<br>P&L: %{color:.2f}%<extra></extra>' if not is_fr else '<b>%{label}</b><br>Valeur: $%{value:,.2f}<br>P&L: %{color:.2f}%<extra></extra>'

    if view_type == "Sunburst Chart (Multi-Layer)":
        fig_map = px.sunburst(df_pos, path=['Sector', 'Symbol'], values='Market Value ($)', color='Unrealized P&L (%)', color_continuous_scale='RdYlGn', color_continuous_midpoint=0, hover_data=['Weight (%)'])
        fig_map.update_traces(hovertemplate=hover_temp)
    else:
        fig_map = px.treemap(df_pos, path=['Sector', 'Symbol'], values='Market Value ($)', color='Unrealized P&L (%)', color_continuous_scale='RdYlGn', color_continuous_midpoint=0, hover_data=['Weight (%)'])
        fig_map.update_traces(hovertemplate=hover_temp)
        
    fig_map.update_layout(template='plotly_dark', margin=dict(t=10, l=0, r=0, b=0), height=500)
    st.plotly_chart(fig_map, use_container_width=True)
    
    st.markdown("### Full Holdings Ledger" if not is_fr else "### Grand Livre des Positions")
    
    df_display = df_pos.copy()
    if is_fr:
        df_display = df_display.rename(columns={
            "Symbol": "Symbole", 
            "Market Value ($)": "Valeur ($)", 
            "Weight (%)": "Poids (%)", 
            "Unrealized P&L ($)": "P&L Latent ($)", 
            "Unrealized P&L (%)": "P&L Latent (%)", 
            "Current Price": "Prix Actuel", 
            "Avg Entry": "Prix d'Entrée", 
            "Sector": "Secteur"
        })
        st.dataframe(df_display.style.format({"Valeur ($)": "${:,.2f}", "Poids (%)": "{:.2f}%", "P&L Latent ($)": "${:,.2f}", "P&L Latent (%)": "{:.2f}%", "Prix Actuel": "${:,.2f}", "Prix d'Entrée": "${:,.2f}"}).background_gradient(subset=['P&L Latent (%)'], cmap='RdYlGn'), use_container_width=True)
    else:
        st.dataframe(df_display.style.format({"Market Value ($)": "${:,.2f}", "Weight (%)": "{:.2f}%", "Unrealized P&L ($)": "${:,.2f}", "Unrealized P&L (%)": "{:.2f}%", "Current Price": "${:,.2f}", "Avg Entry": "${:,.2f}"}).background_gradient(subset=['Unrealized P&L (%)'], cmap='RdYlGn'), use_container_width=True)


# ==========================================
# TAB 3: EXTREMES & ALPHA ATTRIBUTION
# ==========================================
with tab3:
    st.subheader("Performance Extremes & True Edge Discovery" if not is_fr else "Extrêmes de Performance & Découverte de l'Alpha")
    
    desc_tab3 = "This tab separates your <b>Active Trades</b> (Sprint) from your <b>Historical Edge</b> (Marathon). It helps identify which assets generate consistent returns over time versus short-term momentum." if not is_fr else "Cet onglet sépare vos <b>Trades Actifs</b> (Sprint) de votre <b>Avantage Historique</b> (Marathon). Il aide à identifier les actifs générant de la performance sur le long terme par rapport aux fluctuations à court terme."
    st.markdown(f"<div class='info-text'>{desc_tab3}</div>", unsafe_allow_html=True)
    
    if positions:
        df_real = df_pos[df_pos['Symbol'] != "CASH"].sort_values(by="Unrealized P&L (%)", ascending=False)
        if not df_real.empty:
            top_perf, worst_perf = df_real.iloc[0], df_real.iloc[-1]
            
            col_w, col_l = st.columns(2)
            with col_w:
                st.success("🟢 **BEST ACTIVE POSITION (Sprint)**" if not is_fr else "🟢 **MEILLEURE POSITION ACTIVE (Sprint)**")
                st.metric(label=top_perf['Symbol'], value=f"${top_perf['Market Value ($)']:,.2f}", delta=f"{top_perf['Unrealized P&L (%)']:.2f}% (${top_perf['Unrealized P&L ($)']:,.2f})")
                st.markdown(f"- **Sector:** {top_perf['Sector']} | **Weight:** {top_perf['Weight (%)']:.1f}%" if not is_fr else f"- **Secteur:** {top_perf['Sector']} | **Poids:** {top_perf['Weight (%)']:.1f}%")
            with col_l:
                st.error("🔴 **WORST ACTIVE POSITION (Sprint)**" if not is_fr else "🔴 **PIRE POSITION ACTIVE (Sprint)**")
                st.metric(label=worst_perf['Symbol'], value=f"${worst_perf['Market Value ($)']:,.2f}", delta=f"{worst_perf['Unrealized P&L (%)']:.2f}% (${worst_perf['Unrealized P&L ($)']:,.2f})")
                st.markdown(f"- **Sector:** {worst_perf['Sector']} | **Weight:** {worst_perf['Weight (%)']:.1f}%" if not is_fr else f"- **Secteur:** {worst_perf['Sector']} | **Poids:** {worst_perf['Weight (%)']:.1f}%")
            
    st.write("---")
    st.markdown("#### All-Time Profit by Asset (Marathon)" if not is_fr else "#### Profit Total par Actif (Marathon)")
    st.caption("Combines realized and unrealized gains. Identifies the real drivers of your edge." if not is_fr else "Combine les gains réalisés et non réalisés. Identifie les vrais moteurs de votre performance.")
    
    activities = fetch_trade_activities()
    if activities:
        df_act = pd.DataFrame(activities)
        df_act['cash_flow'] = df_act.apply(lambda x: x['qty'] * x['price'] * (-1 if x['side'] == 'buy' else 1), axis=1)
        pnl_tracker = df_act.groupby('symbol')['cash_flow'].sum()
        
        for p in positions:
            pnl_tracker[p.symbol] = pnl_tracker.get(p.symbol, 0) + float(p.market_value)
            
        pnl_tracker = pnl_tracker.sort_values(ascending=True)
        
        fig_attr = px.bar(pnl_tracker, x=pnl_tracker.values, y=pnl_tracker.index, orientation='h', color=pnl_tracker.values, color_continuous_scale='RdYlGn', color_continuous_midpoint=0)
        
        hover_temp_bar = '<b>%{y}</b><br>Net P&L: $%{x:,.2f}<extra></extra>' if not is_fr else '<b>%{y}</b><br>P&L Net: $%{x:,.2f}<extra></extra>'
        fig_attr.update_traces(hovertemplate=hover_temp_bar)
        
        fig_attr.update_layout(template='plotly_dark', height=400, xaxis_title="Net Profit/Loss ($)" if not is_fr else "Profit/Perte Net ($)", yaxis_title="", margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_attr, use_container_width=True)
    else:
        st.info("Not enough history to compute alpha attribution." if not is_fr else "Pas assez d'historique pour calculer l'attribution d'alpha.")


# ==========================================
# TAB 4: EXECUTION TAPE & NEWS
# ==========================================
with tab4:
    st.subheader("🧾 " + ("Journal d'Exécution, Logs & Actualités" if is_fr else "Execution Ledger, Logs & News"))
    
    desc_tab4 = "Monitor the algorithm's pulse. This tab provides a transparent audit trail of raw market orders, live system logs for technical health, and real-time news for your top holdings to understand the macro context." if not is_fr else "Surveillez le pouls de l'algorithme. Cet onglet fournit une piste d'audit transparente des ordres de marché, les logs du système en direct pour surveiller sa santé technique, et les actualités en temps réel de vos principales positions."
    st.markdown(f"<div class='info-text'>{desc_tab4}</div>", unsafe_allow_html=True)
    
    col_tape, col_news = st.columns([1.2, 1])
    
    with col_tape:
        # EXECUTION LEDGER
        st.markdown("### 📝 " + ("Dernières Transactions" if is_fr else "Recent Market Orders"))
        activities = fetch_trade_activities()
        if activities:
            logs = []
            for a in activities[:15]:
                logs.append({
                    "Date": pd.to_datetime(a['date']).strftime('%Y-%m-%d %H:%M'), 
                    "Action": "🟢 ACHAT" if a['side'] == 'buy' and is_fr else "🟢 BUY" if a['side'] == 'buy' else ("🔴 VENTE" if is_fr else "🔴 SELL"), 
                    "Symbole" if is_fr else "Ticker": a['symbol'], 
                    "Prix" if is_fr else "Price": f"${a['price']:.2f}", 
                    "Qté" if is_fr else "Qty": a['qty']
                })
            st.dataframe(pd.DataFrame(logs), use_container_width=True, hide_index=True)
        else:
            st.write("Aucune transaction exécutée." if is_fr else "No executed trades yet.")
            
        st.write("---")
        
        # SYSTEM LOGS
        st.markdown("### ⚙️ " + ("Logs du Serveur en Direct" if is_fr else "Live System Logs"))
        st.caption("aegis_production.log")
        sys_logs = get_system_logs(15)
        st.code(sys_logs, language="bash")

    with col_news:
        st.markdown("### 📡 " + ("Contexte Macro (Top 3 Actifs)" if is_fr else "Market Context (Top 3 Holdings)"))
        if positions:
            top_3 = sorted(positions, key=lambda x: float(x.market_value), reverse=True)[:3]
            for p in top_3:
                st.markdown(f"**{'Actualités pour' if is_fr else 'News for'} {p.symbol}**")
                news_items = get_recent_news(p.symbol)
                if news_items:
                    for n in news_items:
                        st.markdown(f"- [{n['title']}]({n['link']}) *(Yahoo Finance, {n['date']})*")
                else:
                    st.caption("Aucune actualité récente." if is_fr else "No recent news found.")
                st.write("---")
        else:
            st.info("Portefeuille en Cash. Aucune actualité spécifique." if is_fr else "Portfolio in Cash. No specific news.")
# ==========================================
# TAB 5: MONTE CARLO FORECAST
# ==========================================
with tab5:
    st.subheader("Stochastic Portfolio Projection (1 Year)" if not is_fr else "Projection Stochastique du Portefeuille (1 An)")
    
    desc_tab5 = "This Monte Carlo simulation runs 100 random price paths for the next 252 trading days. It uses the historical volatility (23.81%) and CAGR (32.57%) from the V-Chimera audited backtest to project potential future equity. The top line represents a highly optimistic scenario (top 5%), the middle is the median expectation, and the bottom is the pessimistic scenario (bottom 5%)." if not is_fr else "Cette simulation Monte Carlo génère 100 trajectoires de prix aléatoires pour les 252 prochains jours de bourse. Elle utilise la volatilité historique (23.81%) et le CAGR (32.57%) audités du backtest V-Chimera pour projeter le capital futur. La ligne supérieure représente le scénario très optimiste (top 5%), la ligne du milieu l'attente médiane, et la ligne inférieure le scénario pessimiste (bottom 5%)."
    st.markdown(f"<div class='info-text'>{desc_tab5}</div>", unsafe_allow_html=True)
    
    cagr_exact, vol_exact, days, simulations = 0.3257, 0.2381, 252, 100
    daily_drift = (cagr_exact - 0.5 * vol_exact**2) / days
    daily_vol = vol_exact / np.sqrt(days)
    
    paths = np.zeros((days, simulations))
    paths[0] = equity
    for t in range(1, days):
        shock = np.random.normal(0, 1, simulations)
        paths[t] = paths[t-1] * np.exp(daily_drift + daily_vol * shock)
        
    df_mc = pd.DataFrame(paths)
    fig_mc = go.Figure()
    for col in df_mc.columns:
        fig_mc.add_trace(go.Scatter(x=df_mc.index, y=df_mc[col], mode='lines', line=dict(width=1, color='rgba(0, 230, 118, 0.05)'), showlegend=False))
        
    mean_path = df_mc.mean(axis=1)
    top_path = df_mc.quantile(0.95, axis=1)
    bot_path = df_mc.quantile(0.05, axis=1)
    
    fig_mc.add_trace(go.Scatter(x=df_mc.index, y=mean_path, mode='lines', line=dict(width=3, color='white'), name='Median Expected' if not is_fr else 'Médiane Attendue'))
    fig_mc.add_trace(go.Scatter(x=df_mc.index, y=top_path, mode='lines', line=dict(width=2, color='#00E676', dash='dash'), name='Optimistic (Top 5%)' if not is_fr else 'Optimiste (Top 5%)'))
    fig_mc.add_trace(go.Scatter(x=df_mc.index, y=bot_path, mode='lines', line=dict(width=2, color='#FF3B30', dash='dash'), name='Pessimistic (Bottom 5%)' if not is_fr else 'Pessimiste (Derniers 5%)'))
    
    fig_mc.update_layout(template='plotly_dark', xaxis_title="Trading Days (1 Year)" if not is_fr else "Jours de Bourse (1 An)", yaxis_title="Projected Equity ($)" if not is_fr else "Capital Projeté ($)", height=500)
    st.plotly_chart(fig_mc, use_container_width=True)
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Optimistic Target (+1yr)" if not is_fr else "Cible Optimiste (+1an)", f"${top_path.iloc[-1]:,.0f}")
    c2.metric("Median Target (+1yr)" if not is_fr else "Cible Médiane (+1an)", f"${mean_path.iloc[-1]:,.0f}")
    c3.metric("Pessimistic Target (+1yr)" if not is_fr else "Cible Pessimiste (+1an)", f"${bot_path.iloc[-1]:,.0f}")

# ==========================================
# TAB 6: GLOBAL RADAR
# ==========================================
# (Keep your existing Tab 6 code here)

# ==========================================
# TAB 7: STRATEGY DEEP DIVE (THEORY & LOGIC)
# ==========================================
with tab7:
    if not is_fr:
        st.markdown("""
        ## 🧠 Aegis Prime: V-Chimera Engine Theory
        
        This system is a deterministic, emotionless **Global Macro quantitative engine**. It does not predict the future; it adapts mathematically to the present. The V-Chimera architecture represents an institutional-grade evolution, combining trend quality filters, dynamic inflation tracking, and severe kinetic risk controls.
        
        ### 🌍 Phase 1: The Regime Sentinel (Two-Speed Hysteresis)
        Capital preservation is the absolute priority. Before seeking yield, the algorithm evaluates the structural integrity of the broader market.
        - **Indicators:** S&P 500 (SPY) vs its 200-day and 50-day Simple Moving Averages, combined with a 60-day drawdown tracker.
        - **Action:** If the SPY is below both moving averages and experiencing a significant drawdown, the system initiates **Bunker Mode**.
        
        ### 🔥 Phase 2: The Inflation Sentinel
        During Bunker Mode, the system must decide *where* to hide. It analyzes the broader commodity market (DBC) to determine the nature of the crisis.
        - **Deflationary Crisis (e.g., 2008, 2020):** Heavy allocation to Long-Term Treasuries (TLT), which surge as central banks cut rates.
        - **Inflationary Shock (e.g., 2022):** Treasuries are abandoned. Capital rotates heavily into Gold (GLD), Commodities (DBC), and Cash (SHY).
        
        ### 🌡️ Phase 3: Adaptive Volatility & The Kinetic Brake
        When the market is in a confirmed uptrend, the system dictates the balance between Offense and Defense.
        - **Volatility Cap:** The historical percentile rank of the SPY's 21-day volatility dynamically scales the maximum offensive exposure (from 97% down to 30%).
        - **Kinetic Brake:** A severe failsafe. If the live portfolio experiences an intra-strategy drawdown greater than 10%, offensive exposure is slashed by 50%. If the drawdown exceeds 15%, offense is slashed by 80%, forcing the portfolio into defensive assets to stop the bleeding.
        
        ### 🎯 Phase 4: Asset Selection (Score-Convex Rank)
        When permitted to attack, the Growth Engine scans the offensive universe (Tech, Healthcare, Alpha proxies).
        - **Trend Quality Filter:** Assets must exhibit a clean, straight-line uptrend, measured by the $R^2$ of their linear regression. 
        - **Dual Momentum:** It demands positive momentum across both 6-month and 12-month timeframes.
        - **Allocation:** Capital is distributed among the top 7 assets using a convex blend: 60% based on their rank conviction, and 40% smoothed by Inverse Volatility Risk Parity.
        
        ### ✂️ Phase 5: Institutional Risk Management
        The system applies asymmetrical constraints to mathematically prevent catastrophic wipeouts:
        - **Strict Offense Caps:** No single offensive asset can exceed **12%** of the portfolio. No single sector can exceed **28%**.
        - **Zero Leverage Protocol:** The gross exposure is mathematically hard-capped at **98%**, maintaining a permanent 2% cash buffer. The system is physically incapable of borrowing money, completely eliminating margin call risk.
        """)
    else:
        st.markdown("""
        ## 🧠 Aegis Prime : Théorie du Moteur V-Chimera
        
        Ce système est un **moteur quantitatif Global Macro** déterministe et sans émotion. Il ne prédit pas l'avenir ; il s'adapte mathématiquement au présent. L'architecture V-Chimera représente une évolution de niveau institutionnel, combinant des filtres de qualité de tendance, un suivi dynamique de l'inflation et des contrôles de risque cinétiques sévères.
        
        ### 🌍 Phase 1 : La Sentinelle de Régime (Hystérésis à Deux Vitesses)
        La préservation du capital est la priorité absolue. Avant de chercher du rendement, l'algorithme évalue l'intégrité structurelle du marché global.
        - **Indicateurs :** Le S&P 500 (SPY) par rapport à ses moyennes mobiles à 200 jours et 50 jours, combiné à un traqueur de drawdown sur 60 jours.
        - **Action :** Si le SPY est sous ces deux moyennes mobiles et subit un drawdown significatif, le système déclenche le **Bunker Mode**.
        
        ### 🔥 Phase 2 : La Sentinelle d'Inflation
        Pendant le Bunker Mode, le système doit décider *où* se cacher. Il analyse le marché des matières premières (DBC) pour déterminer la nature de la crise.
        - **Crise Déflationniste (ex: 2008, 2020) :** Allocation massive aux obligations à long terme (TLT), qui explosent à la hausse lorsque les banques centrales baissent les taux.
        - **Choc Inflationniste (ex: 2022) :** Les obligations sont abandonnées. Le capital pivote massivement vers l'Or (GLD), les Matières Premières (DBC) et le Cash (SHY).
        
        ### 🌡️ Phase 3 : Volatilité Adaptative & Frein Cinétique
        Quand le marché est dans une tendance haussière confirmée, le système dicte l'équilibre entre Attaque et Défense.
        - **Plafond de Volatilité :** Le rang centile historique de la volatilité à 21 jours du SPY ajuste dynamiquement l'exposition offensive maximale (de 97% jusqu'à 30%).
        - **Frein Cinétique (Kinetic Brake) :** Une sécurité sévère. Si le portefeuille subit un drawdown en direct supérieur à 10%, l'exposition offensive est amputée de 50%. Si le drawdown dépasse 15%, l'attaque est coupée de 80%, forçant le portefeuille vers des actifs défensifs pour stopper l'hémorragie.
        
        ### 🎯 Phase 4 : Sélection des Actifs (Classement Convexe)
        Lorsqu'il est autorisé à attaquer, le moteur de croissance scanne l'univers offensif (Tech, Santé, Proxys Alpha).
        - **Filtre de Qualité de Tendance :** Les actifs doivent afficher une tendance haussière propre et linéaire, mesurée par le $R^2$ de leur régression linéaire.
        - **Double Momentum :** Il exige un momentum positif sur 6 mois ET 12 mois.
        - **Allocation :** Le capital est distribué parmi les 7 meilleurs actifs selon un mix convexe : 60% basé sur leur rang de conviction, et 40% lissé par la Parité des Risques par Volatilité Inverse.
        
        ### ✂️ Phase 5 : Gestion des Risques Institutionnelle
        Le système applique des contraintes asymétriques pour prévenir mathématiquement les baisses catastrophiques :
        - **Plafonds stricts sur l'Offensive :** Aucun actif offensif ne peut dépasser **12%** du portefeuille. Aucun secteur ne peut dépasser **28%**.
        - **Protocole Zéro Levier :** L'exposition brute est mathématiquement plafonnée à **98%**, maintenant une réserve permanente de 2% en cash. Le système est physiquement incapable d'emprunter de l'argent, éliminant tout risque d'appel de marge.
        """)
