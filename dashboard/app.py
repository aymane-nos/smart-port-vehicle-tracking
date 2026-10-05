"""
Dashboard de supervision du système de tracking portuaire.
Consomme uniquement l'API REST du backend (aucun accès direct à la BDD),
ce qui garde le dashboard totalement découplé de l'implémentation interne.
"""
import os
from datetime import datetime

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://backend:8000/api/v1")
REFRESH_SECONDS = int(os.getenv("DASHBOARD_REFRESH_SECONDS", "5"))

st.set_page_config(
    page_title="Smart Port — Monitoring",
    layout="wide",
)


@st.cache_data(ttl=REFRESH_SECONDS)
def fetch_json(endpoint: str, params: dict | None = None):
    try:
        with httpx.Client(base_url=BACKEND_API_URL, timeout=8.0) as client:
            response = client.get(endpoint, params=params or {})
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        st.error(f"Erreur d'accès à l'API backend ({endpoint}) : {exc}")
        return None


def render_header():
    st.title(" Smart Port — Vehicle Tracking & ALPR")
    st.caption(
        f"Dernière actualisation : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
        f"— rafraîchissement auto toutes les {REFRESH_SECONDS}s"
    )


def render_occupancy():
    st.subheader("📊 Occupation actuelle du port")
    data = fetch_json("/analytics/occupancy")
    if not data:
        return

    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("Véhicules présents dans le port", data.get("total_in_port", 0))

    with col2:
        by_type = data.get("by_vehicle_type", {})
        if by_type:
            df = pd.DataFrame({"type": list(by_type.keys()), "count": list(by_type.values())})
            fig = px.bar(df, x="type", y="count", title="Répartition par type de véhicule")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Aucun véhicule dans le port actuellement.")


def render_traffic():
    st.subheader("Trafic (entrées / sorties, 24 dernières heures)")
    data = fetch_json("/analytics/traffic", params={"hours": 24})
    if not data:
        st.info("Pas encore de données de trafic.")
        return

    df = pd.DataFrame(data)
    if df.empty:
        st.info("Pas encore de données de trafic.")
        return

    df_melted = df.melt(id_vars="period", value_vars=["entries", "exits"], var_name="direction", value_name="count")
    fig = px.line(df_melted, x="period", y="count", color="direction", markers=True)
    st.plotly_chart(fig, use_container_width=True)


def render_alerts():
    st.subheader("🚨 Alertes récentes")
    data = fetch_json("/analytics/alerts", params={"limit": 20})
    if not data:
        st.success("Aucune alerte active.")
        return

    for alert in data:
        icon = "⛔" if alert["type"] == "UNAUTHORIZED_VEHICLE" else "⚠️"
        st.warning(
            f"{icon} **{alert['plate']}** — {alert['message']} "
            f"({alert['timestamp']})"
        )


def render_vehicle_table():
    st.subheader("Véhicules")
    status_filter = st.selectbox(
        "Filtrer par statut", ["Tous", "IN_PORT", "OUT", "UNKNOWN"], index=1
    )
    params = {} if status_filter == "Tous" else {"status": status_filter}
    data = fetch_json("/vehicles", params=params)
    if not data:
        st.info("Aucun véhicule trouvé.")
        return

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_detections_log():
    st.subheader("Historique des détections")
    plate_search = st.text_input("Rechercher une plaque (partielle)", "")
    params = {"limit": 50}
    if plate_search:
        params["plate"] = plate_search

    data = fetch_json("/detections", params=params)
    if not data:
        st.info("Aucune détection enregistrée.")
        return

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_daily_summary():
    st.subheader("📦 Agrégats journaliers (pipeline ETL)")
    st.caption(
        "Table de faits produite chaque jour à 01:00 UTC par le job ETL batch "
        " à partir des détections brutes."
    )
    data = fetch_json("/analytics/daily-summary", params={"days": 14})
    if not data:
        st.info(
            "Pas encore d'agrégats disponibles — le job tourne une fois par jour. "
            "Tu peux le déclencher manuellement : "
            "`docker compose exec backend python -m etl.aggregate_daily_traffic --date AAAA-MM-JJ`"
        )
        return

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    fig = px.bar(
        df, x="summary_date", y="entries_count", color="vehicle_type",
        title="Entrées par jour et type de véhicule", barmode="group",
    )
    st.plotly_chart(fig, use_container_width=True)


def main():
    render_header()

    tab_overview, tab_vehicles, tab_history, tab_etl = st.tabs(
        ["Vue d'ensemble", "Véhicules", "Historique détections", "Agrégats ETL"]
    )

    with tab_overview:
        render_occupancy()
        render_traffic()
        render_alerts()

    with tab_vehicles:
        render_vehicle_table()

    with tab_history:
        render_detections_log()

    with tab_etl:
        render_daily_summary()

    st.sidebar.header("⚙️ Configuration")
    st.sidebar.text(f"API backend : {BACKEND_API_URL}")
    if st.sidebar.button("🔄 Rafraîchir maintenant"):
        st.cache_data.clear()
        st.rerun()


if __name__ == "__main__":
    main()
