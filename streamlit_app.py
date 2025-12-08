import streamlit as st
import requests

# --- KONFIGURATION ---
N8N_WEBHOOK_URL = "https://n8n-f8jg4-u44283.vm.elestio.app/webhook/cockpit-chat"

# --- SEITENLAYOUT ---
st.set_page_config(page_title="KI Entwicklungs-Studio", layout="wide")
st.title("🤖 Mein KI Entwicklungs-Studio")
st.markdown("---")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📂 Projekte")

    selected_project = st.selectbox(
        "Aktuelles Projekt:",
        ["Neues Projekt...", "InDesign Skripte", "Website SEO", "Nano Banana Prompts"]
    )

    selected_model = st.selectbox(
        "KI-Modell wählen:",
        [
            "gpt-4o-mini",
            "gpt-4o",
            "gemini-2.5-pro"
        ]
    )

    st.divider()

    st.subheader("🎯 Master-Plan (Ziel)")
    master_prompt = st.text_area(
        "Projekt-Ziel:",
        value="Beispiel: Erstelle ein InDesign Script für Version 2024...",
        height=150
    )

    if st.button("💾 Master-Plan speichern"):
        st.success("Master-Plan gespeichert")

# --- SESSION-STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- CHAT VERLAUF ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- CHAT INPUT ---
if prompt := st.chat_input("Was möchtest du tun?"):

    # USER-NACHRICHT
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # ASSISTENT
    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("⏳ *Verbinde mit n8n...*")

        try:
            payload = {
                "message": prompt,
                "project": selected_project,
                "model": selected_model,
                "master_prompt": master_prompt,
                "history": st.session_state.messages[:-1]
            }

            response = requests.post(
                N8N_WEBHOOK_URL,
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()

                # ✅ Falls n8n LIST statt OBJECT liefert
                if isinstance(data, list) and len(data) > 0:
                    data = data[0]

                # ✅ Beide Varianten abfangen
                answer = str(
                    data.get("output") or
                    data.get("ki_answer") or
                    ""
                ).strip()

                if not answer:
                    answer = "⚠️ n8n hat geantwortet, aber ohne Inhalt."

                # 🧪 Debug (nur falls nötig)
                # st.json(data)

            else:
                answer = f"❌ n8n meldet Fehler {response.status_code}"

        except requests.exceptions.Timeout:
            answer = "⌛ Timeout: n8n antwortet nicht."

        except Exception as e:
            answer = f"🚨 Fehler:\n\n{str(e)}"

        # ANTWORT ANZEIGEN
        placeholder.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})
