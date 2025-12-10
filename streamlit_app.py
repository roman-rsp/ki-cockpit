import streamlit as st
import requests
import json
import base64

# -----------------------
# KONFIGURATION
# -----------------------

N8N_WEBHOOK_URL = "https://n8n-f8jg4-u44283.vm.elestio.app/webhook/cockpit-chat"

st.set_page_config(page_title="KI Cockpit", layout="wide")

if "messages" not in st.session_state:
    st.session_state.messages = []


# -----------------------
# SIDEBAR
# -----------------------

st.sidebar.title("Projekte")

project = st.sidebar.text_input("Projektname", value="Neues Projekt")
model = st.sidebar.selectbox("KI-Modell", ["gpt-4o-mini", "gpt-4.1", "gemini"])
master_prompt = st.sidebar.text_area("Master-Plan", value="Analysiere das Bild professionell.")


# -----------------------
# HEADER
# -----------------------

st.title("🧠 KI Cockpit")


# -----------------------
# CHAT
# -----------------------

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Deine Nachricht …")

uploaded_file = st.file_uploader("Bild hochladen", type=["png", "jpg", "jpeg"])

if uploaded_file:
    st.image(uploaded_file, caption="Vorschau", use_column_width=True)


# -----------------------
# SEND
# -----------------------

if prompt:

    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("⏳ sende…")

        try:
            payload = {
                "message": prompt,
                "project": project,
                "model": model,
                "master_prompt": master_prompt,
                "history": st.session_state.messages[-5:]
            }

            # ✅ BILD ALS BASE64
            if uploaded_file:
                image_bytes = uploaded_file.getvalue()
                image_base64 = base64.b64encode(image_bytes).decode("utf-8")

                payload["image_base64"] = image_base64
                payload["image_mime"] = uploaded_file.type
                payload["image_name"] = uploaded_file.name

            response = requests.post(
                N8N_WEBHOOK_URL,
                json=payload,
                timeout=60
            )

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    data = data[0]

                answer = data.get("output") or data.get("KI_answer") or "⚠️ Antwort leer."
            else:
                answer = f"❌ Fehler {response.status_code}"

        except Exception as e:
            answer = f"⚠️ Exception: {e}"

        placeholder.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})
