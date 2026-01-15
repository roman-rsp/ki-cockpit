import streamlit as st
import requests
import base64
import uuid

# -----------------------
# KONFIGURATION
# -----------------------
N8N_WEBHOOK_URL = "https://n8n-f8jg4-u44283.vm.elestio.app/webhook/cockpit-chat"

st.set_page_config(page_title="KI Cockpit", layout="wide")

# -----------------------
# SESSION STATE DEFAULTS
# -----------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

# Pending-Mechanik, damit die User-Nachricht sofort sichtbar wird
# und der Request erst im nächsten Run sauber ausgeführt wird.
if "pending_payload" not in st.session_state:
    st.session_state.pending_payload = None


# -----------------------
# HELPER: Nachrichten sauber hinzufügen (ohne append)
# -----------------------
def add_message(role: str, content: str, meta: dict | None = None):
    st.session_state.messages = st.session_state.messages + [{
        "id": str(uuid.uuid4()),
        "role": role,
        "content": content,
        "meta": meta or {},
    }]


# -----------------------
# HELPER: Antwort robust extrahieren
# -----------------------
def extract_text(data) -> str:
    """
    Robust: unterstützt verschiedene Response-Formate.
    Priorität: output / KI_answer / content / OpenAI raw_response.output[].content[].text
    """
    if isinstance(data, list) and data:
        data = data[0]

    if not isinstance(data, dict):
        return ""

    # 1) Direkte Felder
    for key in ("output", "KI_answer", "content"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()

    # 2) OpenAI Responses API (Fallback)
    rr = data.get("raw_response") or {}
    try:
        out = rr.get("output", [])
        for item in out:
            parts = item.get("content", [])
            for p in parts:
                if p.get("type") == "output_text" and isinstance(p.get("text"), str):
                    txt = p["text"].strip()
                    if txt:
                        return txt
    except Exception:
        pass

    return ""


def extract_debug(data) -> dict:
    """
    Kleine Debug-Zusammenfassung fürs UI.
    Keine Secrets, nur Meta.
    """
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return {"type": str(type(data))}

    return {
        "provider": data.get("provider"),
        "model": data.get("model"),
        "role": data.get("role"),
        "has_raw_response": bool(data.get("raw_response")),
        "keys": sorted(list(data.keys()))[:50],
        "error": data.get("error"),
        "project_id": data.get("project_id"),
        "request_id": data.get("request_id"),
    }


# -----------------------
# SIDEBAR
# -----------------------
st.sidebar.title("Projekte")

project = st.sidebar.text_input("Projektname", value="Neues Projekt")

model = st.sidebar.selectbox(
    "KI-Modell",
    ["gpt-4o-mini", "gpt-4.1", "gemini-1.5-flash"],
)

master_prompt = st.sidebar.text_area(
    "Master-Plan",
    value="Analysiere das Bild professionell.",
)

debug_mode = st.sidebar.toggle("Debug anzeigen", value=False)

# -----------------------
# HEADER
# -----------------------
st.title("🧠 KI Cockpit")

# -----------------------
# UPLOAD
# -----------------------
uploaded_file = st.file_uploader("Bild hochladen (optional)", type=["png", "jpg", "jpeg"])
if uploaded_file:
    st.image(uploaded_file, caption="Vorschau", use_column_width=True)

# -----------------------
# CHAT RENDER (immer aus session_state)
# -----------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        # Debug pro Assistant-Message (wenn vorhanden)
        if debug_mode and msg["role"] == "assistant":
            meta = msg.get("meta") or {}
            if meta:
                st.caption("Debug (Response-Meta):")
                st.json(meta)

# -----------------------
# INPUT
# -----------------------
prompt = st.chat_input("Deine Nachricht …")

# -----------------------
# 1) USER-EINGABE: sofort speichern + Request für nächsten Run vorbereiten
# -----------------------
if prompt:
    request_id = str(uuid.uuid4())

    # User Message sofort in Chat-Historie (damit sie direkt sichtbar wird)
    add_message("user", prompt)

    # Payload vorbereiten (wird im nächsten Run verarbeitet)
    payload = {
        "request_id": request_id,
        "message": prompt,
        "project": project,
        "model": model,
        "master_prompt": master_prompt,
    }

    # Optionales Bild
    if uploaded_file:
        image_bytes = uploaded_file.getvalue()
        payload["image_base64"] = base64.b64encode(image_bytes).decode("utf-8")
        payload["image_mime"] = uploaded_file.type
        payload["image_name"] = uploaded_file.name

    st.session_state.pending_payload = payload

    # Wichtig: sofort neu rendern, damit die User-Frage ohne Debug-Toggle sichtbar ist
    st.rerun()

# -----------------------
# 2) PENDING REQUEST: Webhook call + Assistant speichern
# -----------------------
if st.session_state.pending_payload:
    payload = st.session_state.pending_payload
    st.session_state.pending_payload = None

    # Wir rendern die Antwort im nächsten Run über die normale Chat-Liste,
    # damit UI-Zustände nicht "halb" bleiben.
    try:
        response = requests.post(
            N8N_WEBHOOK_URL,
            json=payload,
            headers={"X-Request-Id": payload["request_id"]},
            timeout=60,
        )

        if response.status_code == 200:
            data = response.json()
            answer = extract_text(data) or "⚠️ Antwort leer."
            meta = extract_debug(data) if debug_mode else {}
        else:
            answer = f"❌ Fehler {response.status_code}: {response.text}"
            meta = {"error": "http_error", "status_code": response.status_code}

    except Exception as e:
        answer = f"⚠️ Exception: {e}"
        meta = {"error": "exception", "message": str(e)}

    add_message("assistant", answer, meta=meta)

    # Nochmals rerun, damit die Assistant-Antwort sauber im Chat erscheint
    st.rerun()
