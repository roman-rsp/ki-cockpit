import streamlit as st
import requests
import base64
import uuid
from PIL import Image
import io

# ------------------------------------------------------------
# KONFIGURATION (Secrets aus Streamlit Cloud)
# ------------------------------------------------------------
N8N_WEBHOOK_URL = st.secrets["N8N_WEBHOOK_URL"]
N8N_MODELS_URL = st.secrets.get("N8N_MODELS_URL")  # z.B. https://.../webhook/models
N8N_BASIC_USER = st.secrets["N8N_BASIC_USER"]
N8N_BASIC_PASS = st.secrets["N8N_BASIC_PASS"]

st.set_page_config(page_title="KI Cockpit", layout="wide")

# ------------------------------------------------------------
# SESSION STATE DEFAULTS
# ------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_payload" not in st.session_state:
    st.session_state.pending_payload = None

if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

# Freeze-Mechanik: wir speichern Anhänge beim Senden in Session-State
if "frozen_images" not in st.session_state:
    st.session_state.frozen_images = []

if "frozen_pdf" not in st.session_state:
    st.session_state.frozen_pdf = None


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


def build_history(max_items: int = 20) -> list[dict]:
    hist = []
    for m in st.session_state.messages:
        role = m.get("role")
        content = m.get("content")
        if role not in ("user", "assistant"):
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        hist.append({"role": role, "content": content.strip()})
    return hist[-max_items:]


def extract_text(data) -> str:
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


def reset_uploads():
    st.session_state.frozen_images = []
    st.session_state.frozen_pdf = None
    st.session_state.uploader_key += 1


# ------------------------------------------------------------
# MODELLKATALOG (aus n8n: GET /models)
# ------------------------------------------------------------
DEFAULT_MODELS = [
    {"id": "gpt-4o-mini", "label": "GPT-4o mini", "provider": "openai"},
    {"id": "gpt-4.1", "label": "GPT-4.1", "provider": "openai"},
    {"id": "gemini-1.5-flash", "label": "Gemini 1.5 Flash", "provider": "gemini"},
]

@st.cache_data(ttl=600)  # 10 Minuten
def fetch_models() -> list[dict]:
    if not N8N_MODELS_URL:
        return DEFAULT_MODELS

    try:
        r = requests.get(
            N8N_MODELS_URL,
            auth=(N8N_BASIC_USER, N8N_BASIC_PASS),
            timeout=10,
        )
        if r.status_code != 200:
            return DEFAULT_MODELS

        data = r.json()
        # Erwartet: {"models":[{id,label,provider,...}, ...]} oder direkt Liste
        models = data.get("models") if isinstance(data, dict) else data
        if not isinstance(models, list) or not models:
            return DEFAULT_MODELS

        cleaned = []
        for m in models:
            if not isinstance(m, dict):
                continue
            mid = (m.get("id") or "").strip()
            label = (m.get("label") or mid).strip()
            provider = (m.get("provider") or "").strip()
            if not mid:
                continue
            cleaned.append({"id": mid, "label": label, "provider": provider})

        return cleaned or DEFAULT_MODELS
    except Exception:
        return DEFAULT_MODELS


# ------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------
st.sidebar.title("Projekte")

project = st.sidebar.text_input("Projektname", value="Neues Projekt")

models = fetch_models()
model_labels = [m["label"] for m in models]

# stabiler Default: wenn "gpt-4o-mini" vorhanden, sonst erstes Modell
default_id = "gpt-4o-mini"
default_index = 0
for i, m in enumerate(models):
    if m["id"] == default_id:
        default_index = i
        break

selected_label = st.sidebar.selectbox(
    "KI-Modell",
    model_labels,
    index=default_index,
)

# Wir senden an n8n immer die model-id
selected_model = next((m["id"] for m in models if m["label"] == selected_label), models[default_index]["id"])

master_prompt = st.sidebar.text_area(
    "Master-Plan",
    value="Analysiere das Bild professionell.",
)

debug_mode = st.sidebar.toggle("Debug anzeigen", value=False)

st.sidebar.divider()
col_a, col_b = st.sidebar.columns(2)
with col_a:
    if st.button("Anhänge leeren"):
        reset_uploads()
        st.rerun()
with col_b:
    if st.button("Chat leeren"):
        st.session_state.messages = []
        reset_uploads()
        st.rerun()


# ------------------------------------------------------------
# HEADER
# ------------------------------------------------------------
st.title("🧠 KI Cockpit")

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
# INPUT-BEREICH
# ------------------------------------------------------------
st.divider()
st.caption("📎 Anhänge (optional)")

uploaded_images = st.file_uploader(
    "Bilder (max. 3)",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
    label_visibility="collapsed",
    key=f"uploader_images_{st.session_state.uploader_key}",
)

uploaded_pdf = st.file_uploader(
    "PDF (optional)",
    type=["pdf"],
    accept_multiple_files=False,
    label_visibility="collapsed",
    key=f"uploader_pdf_{st.session_state.uploader_key}",
)

# Vorschau (kleiner)
THUMB_WIDTH = 160  # px

def render_thumb(file):
    try:
        img = Image.open(file)
        img = img.convert("RGB")
        # proportional verkleinern
        w, h = img.size
        if w > THUMB_WIDTH:
            new_h = int((THUMB_WIDTH / w) * h)
            img = img.resize((THUMB_WIDTH, new_h))
        st.image(img, caption=file.name, width=THUMB_WIDTH)
    except Exception:
        # Fallback ohne PIL
        st.image(file, caption=file.name, width=THUMB_WIDTH)

if uploaded_images:
    if len(uploaded_images) > 3:
        st.warning("⚠️ Maximal 3 Bilder erlaubt. Es werden nur die ersten 3 verwendet.")
        uploaded_images = uploaded_images[:3]

    cols = st.columns(3)
    for i, img in enumerate(uploaded_images):
        with cols[i % 3]:
            render_thumb(img)

if uploaded_pdf:
    st.caption(f"📄 {uploaded_pdf.name} ({uploaded_pdf.size / 1024:.1f} KB)")

prompt = st.chat_input("Deine Nachricht …")

# ------------------------------------------------------------
# 1) USER-EINGABE
# ------------------------------------------------------------
if prompt:
    request_id = str(uuid.uuid4())
    history = build_history(max_items=20)

    add_message("user", prompt)

    # Anhänge "einfrieren" (damit sich zwischen Reruns nichts ändert)
    frozen_images = []
    if uploaded_images:
        imgs = uploaded_images[:3]
        for img in imgs:
            img_bytes = img.getvalue()
            frozen_images.append({
                "filename": img.name,
                "mime": img.type,
                "b64": base64.b64encode(img_bytes).decode("utf-8"),
            })

    frozen_pdf = None
    if uploaded_pdf:
        pdf_bytes = uploaded_pdf.getvalue()
        frozen_pdf = {
            "filename": uploaded_pdf.name,
            "mime": uploaded_pdf.type or "application/pdf",
            "b64": base64.b64encode(pdf_bytes).decode("utf-8"),
        }

    st.session_state.frozen_images = frozen_images
    st.session_state.frozen_pdf = frozen_pdf

    payload = {
        "request_id": request_id,
        "message": prompt,
        "project": project,
        "model": selected_model,  # <-- dynamisch!
        "master_prompt": master_prompt,
        "history": history,
        "images": st.session_state.frozen_images,
        "pdfs": [st.session_state.frozen_pdf] if st.session_state.frozen_pdf else [],
    }

    # Rückwärtskompatibilität (alt)
    if payload["images"] and len(payload["images"]) == 1:
        payload["image_base64"] = payload["images"][0]["b64"]
        payload["image_mime"] = payload["images"][0]["mime"]
        payload["image_name"] = payload["images"][0]["filename"]

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

    # Uploads wirklich leeren
    reset_uploads()

    st.rerun()
