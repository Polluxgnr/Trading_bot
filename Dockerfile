# =====================================================================
# 🛡️ AEGIS PRIME - INSTITUTIONAL DOCKERFILE
# Core: Python 3.12 Slim (Optimized for low-latency & low-storage)
# =====================================================================
FROM python:3.12-slim

# --- 1. ENVIRONMENT VARIABLES (Python Optimization) ---
# Empêche Python de créer des fichiers .pyc inutiles (économise du disque)
ENV PYTHONDONTWRITEBYTECODE=1
# Force l'affichage des logs en temps réel (crucial pour le watchdog et le debugging)
ENV PYTHONUNBUFFERED=1

# --- 2. WORKSPACE ---
WORKDIR /app

# --- 3. SYSTEM DEPENDENCIES (Build Tools) ---
# Installation des outils C pour compiler scipy/pandas, 
# suivi d'un nettoyage massif et immédiat du cache système Linux.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# --- 4. PYTHON DEPENDENCIES (Anti-Saturation Protocol) ---
# Copie du requirements.txt seul pour maximiser le cache Docker
COPY requirements.txt .

# Installation des dépendances avec purge chirurgicale des caches (Évite le crash "Disk Full")
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache/pip && \
    rm -rf /tmp/*

# --- 5. SOURCE CODE & PERSISTENCE ---
# Copie du reste des scripts (aegis_bot.py, dashboard.py, etc.)
COPY . .

# Création des répertoires locaux au cas où ils manqueraient
RUN mkdir -p logs data

# --- 6. NETWORKING ---
# Exposition du port pour le Terminal Streamlit
EXPOSE 8501

# Commande de fallback (Sera écrasée par le docker-compose pour faire tourner
# le bot et le dashboard en parallèle sur deux conteneurs distincts)
CMD ["python", "aegis_bot.py"]
