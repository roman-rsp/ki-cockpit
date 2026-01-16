import streamlit as st
import requests
import base64
import uuid

# ------------------------------------------------------------
# KONFIGURATION (Secrets aus Streamlit Cloud)
# ------------------------------------------------------------
N8N_WEBHOOK_URL = st.secrets["N8N_WEBHOOK_URL"]
N8N_BASIC_USER = st.secrets["N8N_BASIC_USER"]
N8N_BASIC_PASS = st.secrets["N8N_BASIC_PASS"]

st.set_page_config(page_title="KI Cockpit", layout="wide")

# ------------------------------------------------------------
# SESSION STATE DEFAULTS
# ------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

# Pending-Mechanik:
# User-Nachricht sofort sichtbar, Request im nächsten Run
if "pending_payload" not in st.session_state:
    st.session_state.pending_payload = None

# Uploader-Reset (damit ein Bild nicht bei der nächsten Anfrage erneut mitgesendet wird)
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

# ------------------------------------------------------------
# HELPER: Nachrichten sauber hinzufügen
# ------------------------------------------------------------
def add_message(role: str, content: str, meta: dict | None = None):
    st.session_state.messages = st.session_state.messages + [{
        "id": str(uuid.uuid4()),
        "role": role,
        "content": content,
        "meta": meta or {},
    }]

# ------------------------------------------------------------
# HELPER: Chat-History für Backend bauen (nur role+content)
# ------------------------------------------------------------
def build_history(max_items: int = 20) -> list[dict]:
    """
    Baut eine schlanke History:
    - nur user/assistant
    - nur role + content
    - begrenzt auf die letzten max_items Messages
    """
    hist = []
    for m in st.session_state.messages:
        role = m.get("role")
        content = m.get("content")
        if role not in ("user", "assistant"):
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        hist.append({"role": role, "content": content.strip()})

    # Nur die letzten N Einträge senden
    return hist[-max_items:]

# ------------------------------------------------------------
# HELPER: Antwort robust extrahieren
# ------------------------------------------------------------
def extract_text(data) -> str:
    """
    Priorität:
    output / KI_answer / content /
    OpenAI raw_response.output[].content[].text
    """
    if isinstance(data, list) and data:
        data = data[0]

    if not isinstance(data, dict):
        return ""

    for key in ("output", "KI_answer", "content"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()

    rr = data.get("raw_response") or {}
    try:
        for item in rr.get("output", []):
            for p in item.get("content", []):
                if p.get("type") == "output_text" and isinstance(p.get("text"), str):
                    txt = p["text"].strip()
                    if txt:
                        return txt
    except Exception:
        pass

    return ""

def extract_debug(data) -> dict:
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

# ------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------
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

# ------------------------------------------------------------
# HEADER
# ------------------------------------------------------------
st.title("🧠 KI Cockpit")

# ------------------------------------------------------------
# UPLOAD
# ------------------------------------------------------------
uploaded_file = st.file_uploader(
    "Bild hochladen (optional)",
    type=["png", "jpg", "jpeg"],
    key=f"uploader_{st.session_state.uploader_key}",
)

if uploaded_file:
    st.image(uploaded_file, caption="Vorschau", width=320)

# ------------------------------------------------------------
# CHAT RENDER
# ------------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        if debug_mode and msg["role"] == "assistant":
            meta = msg.get("meta") or {}
            if meta:
                st.caption("Debug (Response-Meta):")
                st.json(meta)

# ------------------------------------------------------------
# INPUT
# ------------------------------------------------------------
prompt = st.chat_input("Deine Nachricht …")

# ------------------------------------------------------------
# 1) USER-EINGABE
# ------------------------------------------------------------
if prompt:
    request_id = str(uuid.uuid4())

    # History VOR dem Hinzufügen der neuen User-Message bauen
    history = build_history(max_items=20)

    # User-Message sofort im Chat anzeigen
    add_message("user", prompt)

    payload = {
        "request_id": request_id,
        "message": prompt,
        "project": project,
        "model": model,
        "master_prompt": master_prompt,
        "history": history,
    }

    if uploaded_file:
        image_bytes = uploaded_file.getvalue()
        payload["image_base64"] = base64.b64encode(image_bytes).decode("utf-8")
        payload["image_mime"] = uploaded_file.type
        payload["image_name"] = uploaded_file.name

    st.session_state.pending_payload = payload
    st.rerun()

# ------------------------------------------------------------
# 2) PENDING REQUEST → n8n
# ------------------------------------------------------------
if st.session_state.pending_payload:
    payload = st.session_state.pending_payload
    st.session_state.pending_payload = None

    try:
        response = requests.post(
            N8N_WEBHOOK_URL,
            json=payload,
            auth=(N8N_BASIC_USER, N8N_BASIC_PASS),
            headers={"X-Request-Id": payload["request_id"]},
            timeout=60,
        )

        if response.status_code in (401, 403):
            answer = "❌ Zugriff verweigert (Auth)."
            meta = {"error": "auth"}

        elif response.status_code == 200:
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

    # Uploader leeren, damit das Bild nicht bei der nächsten Anfrage erneut mitgesendet wird
    st.session_state.uploader_key += 1

    st.rerun()
