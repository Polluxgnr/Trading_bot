#Image de base officielle Python (Version Slim pour la légèreté)
FROM python:3.9-slim

#Variables d'environnement pour optimiser Python dans Docker
# Empêche Python d'écrire des fichiers .pyc inutiles
ENV PYTHONDONTWRITEBYTECODE=1
# Force les logs à s'afficher en temps réel dans le terminal (crucial pour le debugging)
ENV PYTHONUNBUFFERED=1

#Définition du répertoire de travail dans le conteneur
WORKDIR /app

#Installation des dépendances système basiques
# (Nécessaire pour compiler certaines libs mathématiques comme numpy/pandas si besoin)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Installation des dépendances Python
# On copie d'abord le requirements.txt pour profiter du cache Docker
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

#Copie du reste du code source
COPY . .

#Création des dossiers de persistance (au cas où ils n'existent pas)
RUN mkdir -p logs data

#Exposition du port pour Streamlit (Dashboard)
EXPOSE 8501

#Commande par défaut (Sera surchargée par le docker-compose, mais bonne pratique)
# Vérifie la santé du script principal
CMD ["python", "main.py"]