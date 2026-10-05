# Captures à fournir pour le README principal

Ce dossier doit contenir les fichiers suivants (noms exacts, déjà référencés
dans le README racine — une fois déposés ici, les images s'affichent
automatiquement) :

| Fichier | Contenu attendu | Comment l'obtenir |
|---|---|---|
| `dashboard-overview.png` | Onglet **« Vue d'ensemble »** du dashboard, avec de vraies données (lance `python -m scripts.seed_fake_data` avant pour avoir un dashboard bien rempli, pas vide) | http://localhost:8501 → capture plein écran du navigateur |
| `dashboard-etl.png` | Onglet **« Agrégats ETL »**, montrant le tableau + le graphique par type de véhicule | Même endroit, clique sur l'onglet |
| `api-swagger.png` | La page Swagger de l'API, avec idéalement un endpoint déplié (ex: `POST /detections`) | http://localhost:8000/docs |
| `demo.gif` | 10-15 secondes montrant le flux complet : lancement d'`ai-service` sur une vidéo de test dans un terminal → bascule sur le dashboard qui se met à jour | Voir instructions GIF ci-dessous |

## Prendre les captures (Windows)

1. Seed d'abord des données réalistes pour que ça ne ressemble pas à une
   démo vide : `docker compose exec backend python -m scripts.seed_fake_data`
2. Ouvre le dashboard, règle la fenêtre à une taille propre (évite de
   capturer la barre de favoris du navigateur).
3. **Win + Maj + S** (Outil Capture d'écran Windows intégré) → capture de
   zone → colle dans Paint ou directement enregistre → sauvegarde en `.png`
   ici avec le nom exact attendu.

## Faire le GIF de démo

Outil recommandé : **ScreenToGif** (gratuit, léger, fait exactement ça) —
https://www.screentogif.com/

1. Lance l'enregistreur, cadre une zone qui montre à la fois le terminal
   (logs `ai-service`) et le navigateur (dashboard) si ton écran le permet,
   sinon fais deux clips et garde le plus parlant.
2. Lance `docker compose up ai-service` sur une vidéo de test courte,
   laisse tourner jusqu'à voir `Détection envoyée: plaque=...` dans les logs.
3. Bascule sur le dashboard, clique sur « 🔄 Rafraîchir maintenant » pour
   montrer la détection apparaître.
4. Arrête l'enregistrement, exporte en `.gif` (ScreenToGif a un export
   direct), vise un fichier **sous 5-8 Mo** pour que GitHub l'affiche bien
   (compresse si besoin — ScreenToGif a une option de réduction de
   palette de couleurs).
5. Sauvegarde ici sous `demo.gif`.

## Une fois les fichiers ajoutés

```powershell
git add docs/screenshots/*.png docs/screenshots/*.gif
git commit -m "Ajout captures et démo GIF au README"
git push
```
