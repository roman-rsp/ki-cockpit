import streamlit as st
import requests

# --- KONFIGURATION ---
# Das hier ist die Adresse, an die dein Chat die Nachrichten schickt.
# Wir müssen diesen Link später noch durch deinen ECHTEN n8n-Link ersetzen.
N8N_WEBHOOK_URL = "https://n8n-f8jg4-u44283.vm.elestio.app/webhook/cockpit-chat"

# --- SEITEN-LAYOUT ---
st.set_page_config(page_title="KI Entwickler-Studio", layout="wide")

# Titel & Header
st.title("🤖 Mein KI Entwicklungs-Studio")
st.markdown("---")

# --- SIDEBAR (Projekte) ---
with st.sidebar:
    st.header("📂 Projekte")
    # Dropdown Menü für deine Projekte
    selected_project = st.selectbox(
        "Aktuelles Projekt:",
        ["Neues Projekt...", "InDesign Skripte", "Website SEO", "Nano Banana Prompts"]
    )
    
    st.divider()
    
    # Der Master-Plan (Das Ziel des Projekts)
    st.subheader("🎯 Master-Plan (Ziel)")
    st.info("Hier steht später das Ziel des ausgewählten Projekts, damit die KI den Fokus behält.")
    master_prompt = st.text_area(
        "Projekt-Ziel bearbeiten:",
        value="Beispiel: Erstelle ein InDesign Script für Version 2024...",
        height=150
    )
    if st.button("💾 Master-Plan speichern"):
        st.success("Gespeichert! (Simulation)")

# --- CHAT BEREICH ---
# Hier speichern wir den Chat-Verlauf im Browser-Zwischenspeicher
if "messages" not in st.session_state:
    st.session_state.messages = []

# Alte Nachrichten aus dem Verlauf anzeigen
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- EINGABE & KOMMUNIKATION ---
# Das Eingabefeld unten am Bildschirm
if prompt := st.chat_input("Was möchtest du tun?"):
    # 1. Deine Nachricht anzeigen
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
                "master_prompt": master_prompt,
                "history": st.session_state.messages[:-1]
            }
            
            # An n8n senden (POST Request)
            # Timeout auf 30 Sekunden, damit wir nicht ewig warten
            response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=30)
            
            if response.status_code == 200:
                # Versuchen, die Antwort zu lesen
                data = response.json()
                # Wir erwarten ein Feld "output" oder "text" von n8n
                answer = data.get("output", data.get("text", "n8n hat geantwortet, aber der Text war leer."))
            else:
                answer = f"⚠️ Fehler: n8n meldet Status {response.status_code}"
                
        except Exception as e:
            # Fallback, wenn die Verbindung noch nicht steht
            answer = f"ℹ️ **Hinweis:** Ich konnte n8n noch nicht erreichen.\n\nGrund: `{str(e)}`\n\n*Das ist normal, wenn wir den Webhook in n8n noch nicht aktiviert haben.*"

        # 3. Antwort anzeigen
        message_placeholder.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})
