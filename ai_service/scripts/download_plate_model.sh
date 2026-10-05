#!/usr/bin/env bash
# Télécharge le modèle YOLOv8 de détection de plaques pré-entraîné, pour
# éviter tout entraînement local. Source (MIT) :
# https://github.com/Muhammad-Zeerak-Khan/Automatic-License-Plate-Recognition-using-YOLOv8
#
# Utilisation :
#   bash scripts/download_plate_model.sh
set -euo pipefail

MODEL_URL="https://raw.githubusercontent.com/Muhammad-Zeerak-Khan/Automatic-License-Plate-Recognition-using-YOLOv8/main/license_plate_detector.pt"
DEST_DIR="$(dirname "$0")/../models"
DEST_FILE="${DEST_DIR}/plate_detector.pt"

mkdir -p "${DEST_DIR}"

if [ -f "${DEST_FILE}" ]; then
    echo "Le modèle existe déjà : ${DEST_FILE} (supprime-le pour forcer le re-téléchargement)."
    exit 0
fi

echo "Téléchargement du modèle plaque pré-entraîné..."
curl -L -o "${DEST_FILE}" "${MODEL_URL}"
echo "OK -> ${DEST_FILE}"
