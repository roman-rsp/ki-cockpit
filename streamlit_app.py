import streamlit as st
import requests
import json

# -----------------------
# KONFIGURATION
# -----------------------

N8N_WEBHOOK_URL = "https://n8n-f8jg4-u44283.vm.elestio.app/webhook/cockpit-chat"

st.set_page_config(page_title="KI Cockpit", layout="wide")


# -----------------------
# SESSION INIT
# -----------------------

if "messages" not in st.session_state:
    st.session_state.messages = []


# -----------------------
# SIDEBAR
# -----------------------

st.sidebar.title("Projekte")

project = st.sidebar.text_input("Projektname", value="Neues Projekt")

model = st.sidebar.selectbox(
    "KI-Modell",
    ["gpt-4o-mini", "gpt-4.1", "gemini"]
)

master_prompt = st.sidebar.text_area(
    "Master-Plan (Ziel)",
    value="Analysiere das Bild professionell und beschreibe es detailliert."
)


# -----------------------
# HEADER
# -----------------------

st.title("🧠 KI Cockpit")
st.caption("Text & Bildanalyse mit stabiler Upload-API (Variante B)")


# -----------------------
# CHAT HISTORY RENDERING
# -----------------------

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# -----------------------
# USER INPUT
# -----------------------

prompt = st.chat_input("Deine Nachricht …")

uploaded_file = st.file_uploader(
    "Bild hochladen (optional)",
    type=["png", "jpg", "jpeg"]
)

if uploaded_file:
    st.image(uploaded_file, caption="Vorschau", use_column_width=True)


# -----------------------
# SEND REQUEST
# -----------------------

if prompt:
    # Nutzer‐Nachricht speichern
    st.session_state.messages.append({
        "role": "user",
        "content": prompt
    })

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("⏳ **Verbinde mit n8n...**")

        try:
            # -------------------------------
            # FALL A: MIT BILD (MULTIPART)
            # -------------------------------
            if uploaded_file:
                files = {
                    "image": (
                        uploaded_file.name,
                        uploaded_file.getvalue(),
                        uploaded_file.type
                    )
                }

                data = {
                    "message": prompt,
                    "project": project,
                    "model": model,
                    "master_prompt": master_prompt,
                    "history": json.dumps(st.session_state.messages[-5:]),
                }

                response = requests.post(
                    N8N_WEBHOOK_URL,
                    data=data,
                    files=files,
                    timeout=60
                )

            # -------------------------------
            # FALL B: TEXT ONLY
            # -------------------------------
            else:
                payload = {
                    "message": prompt,
                    "project": project,
                    "model": model,
                    "master_prompt": master_prompt,
                    "history": st.session_state.messages[-5:],
                }

                response = requests.post(
                    N8N_WEBHOOK_URL,
                    json=payload,
                    timeout=60
                )

            # -------------------------------
            # RESPONSE OK
            # -------------------------------
            if response.status_code == 200:
                data = response.json()

                if isinstance(data, list) and len(data) > 0:
                    data = data[0]

                answer = data.get("output") or data.get("KI_answer")

                if not answer:
                    answer = "⚠️ n8n hat geantwortet, aber ohne Inhalt."
            else:
                answer = f"❌ Serverfehler {response.status_code}"

        except requests.exceptions.Timeout:
            answer = "⏱️ Timeout – n8n antwortet nicht."

        except Exception as e:
            answer = f"⚠️ Fehler:\n\n{str(e)}"

        # -------------------------------
        # AUSGABE
        # -------------------------------
        placeholder.markdown(answer)

        st.session_state.messages.append({
            "role": "assistant",
            "content": answer
        })
