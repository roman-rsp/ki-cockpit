import streamlit as st
import requests
import base64
from typing import Any, Dict, List, Optional

# -----------------------
# KONFIGURATION
# -----------------------
N8N_WEBHOOK_URL = "https://n8n-f8jg4-u44283.vm.elestio.app/webhook/cockpit-chat"
TIMEOUT_SECONDS = 60
HISTORY_LIMIT = 12  # genug Kontext fürs Testen, nicht zu groß

st.set_page_config(page_title="KI Cockpit", layout="wide")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_response_meta" not in st.session_state:
    st.session_state.last_response_meta = {}

# -----------------------
# HELPER
# -----------------------
def to_base64(file) -> Dict[str, str]:
    image_bytes = file.getvalue()
    return {
        "image_base64": base64.b64encode(image_bytes).decode("utf-8"),
        "image_mime": file.type,
        "image_name": file.name,
    }

def normalize_history(messages: List[Dict[str, str]], limit: int) -> List[Dict[str, str]]:
    # Nur role/content, nur user/assistant, leere Inhalte raus
    cleaned = []
    for m in messages:
        role = (m.get("role") or "").strip()
        content = (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            cleaned.append({"role": role, "content": content})
    return cleaned[-limit:]

def pick_answer(data: Any) -> str:
    """
    Erwartet entweder dict oder list[dict].
    Rückgabe: bestmöglicher Antworttext.
    """
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return "⚠️ Unerwartetes Response-Format."

    # Häufigste Felder, absteigend nach Priorität
    for key in ("output", "content", "ki_answer", "KI_answer", "answer", "text"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    # Falls n8n “raw_response” mitliefert: nicht alles dumpen, nur Hinweis
    if data.get("raw_response") is not None:
        return "⚠️ Antwort leer, aber raw_response vorhanden (Debug aktivieren)."

    return "⚠️ Antwort leer."

def extract_meta(data: Any, status_code: int) -> Dict[str, Any]:
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return {"status_code": status_code}

    return {
        "status_code": status_code,
        "provider": data.get("provider") or data.get("model_provider"),
        "model": data.get("model"),
        "error": data.get("error"),
        "usage": data.get("usage"),
        "id": (data.get("raw_response") or {}).get("id") if isinstance(data.get("raw_response"), dict) else data.get("id"),
    }

# -----------------------
# SIDEBAR
# -----------------------
st.sidebar.title("Projekte")

project = st.sidebar.text_input("Projektname", value="Neues Projekt")

# Saubere Modellwerte: echte Strings, die dein Router sicher unterscheiden kann
model = st.sidebar.selectbox(
    "KI-Modell",
    [
        "gpt-4o-mini",
        "gpt-4.1",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ],
    index=0,
)

master_prompt = st.sidebar.text_area(
    "Master-Plan",
    value="Analysiere das Bild professionell.",
    height=120,
)

show_debug = st.sidebar.toggle("Debug anzeigen", value=False)

# -----------------------
# HEADER
# -----------------------
st.title("🧠 KI Cockpit")

# -----------------------
# UPLOAD (oben, damit klar ist: optional)
# -----------------------
uploaded_file = st.file_uploader("Bild hochladen (optional)", type=["png", "jpg", "jpeg"])

if uploaded_file:
    st.image(uploaded_file, caption="Vorschau", use_column_width=True)

# -----------------------
# CHAT RENDER
# -----------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Deine Nachricht …")

# -----------------------
# SEND
# -----------------------
if prompt:
    prompt = prompt.strip()
    if prompt:
        # 1) User message speichern (UI)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # 2) Payload bauen
        payload: Dict[str, Any] = {
            "message": prompt,
            "project": project,
            "model": model,
            "master_prompt": master_prompt,
            "history": normalize_history(st.session_state.messages, HISTORY_LIMIT),
            # Optional: Module-Flagging für dein n8n-Konzept
            "active_modules": ["n8n", "openai_vision" if model.startswith("gpt") else "gemini"],
        }

        if uploaded_file:
            payload.update(to_base64(uploaded_file))
        else:
            payload["image_base64"] = None

        # 3) Request ausführen + UI-Feedback
        with st.chat_message("assistant"):
            placeholder = st.empty()
            placeholder.markdown("⏳ sende…")

            try:
                resp = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=TIMEOUT_SECONDS)
                status = resp.status_code

                if status == 200:
                    data = resp.json()
                    answer = pick_answer(data)
                    st.session_state.last_response_meta = extract_meta(data, status)
                else:
                    answer = f"❌ Fehler {status}: {resp.text[:300]}"
                    st.session_state.last_response_meta = {"status_code": status, "error": resp.text[:500]}

            except Exception as e:
                answer = f"⚠️ Exception: {e}"
                st.session_state.last_response_meta = {"status_code": None, "error": str(e)}

            placeholder.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})

        # Optional: Nach dem Senden Upload “lösen” (Streamlit kann uploader nicht direkt resetten)
        # -> pragmatisch: Hinweis + ggf. in UI "neues Bild" wählen

# -----------------------
# DEBUG PANEL
# -----------------------
if show_debug:
    st.divider()
    st.subheader("Debug")
    st.json(
        {
            "webhook": N8N_WEBHOOK_URL,
            "selected_model": model,
            "project": project,
            "last_response_meta": st.session_state.last_response_meta,
        }
    )
