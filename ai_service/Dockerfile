FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Dépendances système requises par OpenCV / EasyOCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Sans GPU : on force les wheels CPU-only de PyTorch AVANT ultralytics/easyocr,
# sinon pip télécharge par défaut les builds CUDA (~2,5 Go inutiles ici).
# Gain : install plus rapide + image plus légère, aucune perte de fonctionnalité
# (l'inférence tourne simplement sur CPU, plus lente mais fonctionnelle).
RUN pip install --no-cache-dir torch==2.4.1 torchvision==0.19.1 \
    --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/media /app/models

# Le modèle véhicule (yolov8n.pt) est téléchargé automatiquement par
# Ultralytics au premier lancement. Le modèle plaque (models/plate_detector.pt)
# n'est PAS versionné dans git (poids binaire, voir .gitignore) : on le
# télécharge ici au build si absent du contexte de build local.
# Source (MIT) : Muhammad-Zeerak-Khan/Automatic-License-Plate-Recognition-using-YOLOv8
RUN bash scripts/download_plate_model.sh || echo "⚠️ Téléchargement du modèle plaque échoué — fallback heuristique utilisé au runtime."

CMD ["python", "main_ai.py"]
