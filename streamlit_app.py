import streamlit as st
import requests

# --- KONFIGURATION ---
# Deine echte n8n-Adresse
N8N_WEBHOOK_URL = "https://n8n-f8jg4-u44283.vm.elestio.app/webhook/cockpit-chat"

# --- SEITEN-LAYOUT ---
st.set_page_config(page_title="KI Entwickler-Studio", layout="wide")

# Titel & Header
st.title("🤖 Mein KI Entwicklungs-Studio")
st.markdown("---")

# --- SIDEBAR (Projekte & Einstellungen) ---
with st.sidebar:
    st.header("📂 Projekte")
    
    # 1. Projektauswahl
    selected_project = st.selectbox(
        "Aktuelles Projekt:",
        ["Neues Projekt...", "InDesign Skripte", "Website SEO", "Nano Banana Prompts"]
    ) # <--- Hier fehlte vorher die Klammer
    
    # 2. KI-Modell Auswahl (Die Weiche)
    selected_model = st.selectbox(
        "KI-Modell wählen:",
        ["gpt-4o-mini (Schnell & Günstig)", "gpt-4o (Der Denker)", "gemini-1.5-pro (Google)"]
    )

    st.divider()
    
    # 3. Der Master-Plan
    st.subheader("🎯 Master-Plan (Ziel)")
    st.info("Hier steht das Ziel des Projekts, damit die KI den Fokus behält.")
    master_prompt = st.text_area(
        "Projekt-Ziel bearbeiten:",
        value="Beispiel: Erstelle ein InDesign Script für Version 2024...",
        height=150
    )
    
    if st.button("💾 Master-Plan speichern"):
        st.success("Gespeichert! (Simulation)")

# --- CHAT BEREICH ---
# Chat-Verlauf initialisieren
if "messages" not in st.session_state:
    st.session_state.messages = []

# Alte Nachrichten anzeigen
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- EINGABE & KOMMUNIKATION ---
if prompt := st.chat_input("Was möchtest du tun?"):
    # 1. User-Nachricht anzeigen
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 2. Nachricht an n8n senden
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("⏳ *Verbinde mit n8n...*")
        
        try:
            # Datenpaket schnüren
            payload = {
                "message": prompt,
                "project": selected_project,
                "model": selected_model,        # <--- WICHTIG: Das Modell mitsenden!
                "master_prompt": master_prompt,
                "history": st.session_state.messages[:-1]
            }
            
            # An n8n senden (30 Sekunden Timeout)
            response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                # Antwort auslesen (Fallback, falls leer)
                answer = data.get("output", data.get("text", "n8n hat geantwortet, aber der Text war leer."))
            else:
                answer = f"⚠️ Fehler: n8n meldet Status {response.status_code}"
                
        except Exception as e:
            answer = f"ℹ️ **Verbindungsfehler:**\n\n`{str(e)}`"

        # 3. Antwort anzeigen
        message_placeholder.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})
