import streamlit as st
import requests
import base64
import uuid
from typing import Any

# ------------------------------------------------------------
# KONFIGURATION (Secrets)
# ------------------------------------------------------------
N8N_WEBHOOK_URL = st.secrets["N8N_WEBHOOK_URL"]
N8N_MODELS_URL = st.secrets["N8N_MODELS_URL"]
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

# Freeze-Mechanik: Anhänge beim Senden einfrieren
if "frozen_images" not in st.session_state:
    st.session_state.frozen_images = []

if "frozen_pdf" not in st.session_state:
    st.session_state.frozen_pdf = None

# Model-Catalog Cache
if "models_cache" not in st.session_state:
    st.session_state.models_cache = []  # list[dict]
if "models_error" not in st.session_state:
    st.session_state.models_error = None  # str|None

# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------
def add_message(role: str, content: str, meta: dict | None = None):
    st.session_state.messages = st.session_state.messages + [{
        "id": str(uuid.uuid4()),
        "role": role,
        "content": content,
        "meta": meta or {},
    }]

def build_history(max_items: int = 20) -> list[dict]:
    hist: list[dict] = []
    for m in st.session_state.messages:
        role = m.get("role")
        content = m.get("content")
        if role not in ("user", "assistant"):
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        hist.append({"role": role, "content": content.strip()})
    return hist[-max_items:]

def extract_text(data: Any) -> str:
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

def extract_debug(data: Any) -> dict:
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

def model_key(m: dict) -> str:
    # eindeutiger Key
    return f"{m.get('provider','')}:{m.get('id','')}".strip(":")

def parse_model_key(k: str) -> tuple[str, str]:
    # "openai:gpt-4o-mini" -> ("openai","gpt-4o-mini")
    if not isinstance(k, str) or ":" not in k:
        return ("openai", "gpt-4o-mini")
    provider, mid = k.split(":", 1)
    provider = (provider or "openai").strip().lower()
    mid = (mid or "gpt-4o-mini").strip()
    return provider, mid

def load_models():
    st.session_state.models_error = None
    try:
        r = requests.get(
            N8N_MODELS_URL,
            auth=(N8N_BASIC_USER, N8N_BASIC_PASS),
            timeout=30,
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        data = r.json()
        # n8n liefert: {"models":[...]}  (oder manchmal [{ "models": [...] }])
        if isinstance(data, list) and data:
            data = data[0]
        models = []
        if isinstance(data, dict):
            models = data.get("models") or []
        if not isinstance(models, list):
            models = []
        # minimale Validierung
        cleaned = []
        for m in models:
            if not isinstance(m, dict):
                continue
            if not m.get("id") or not m.get("provider") or not m.get("label"):
                continue
            cleaned.append(m)
        st.session_state.models_cache = cleaned
    except Exception as e:
        st.session_state.models_cache = []
        st.session_state.models_error = str(e)

# ------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------
st.sidebar.title("Projekte")

project = st.sidebar.text_input("Projektname", value="Neues Projekt")
debug_mode = st.sidebar.toggle("Debug anzeigen", value=False)

st.sidebar.divider()

with st.sidebar.expander("Modelle", expanded=True):
    col_a, col_b = st.columns([1, 2], vertical_alignment="center")
    with col_a:
        if st.button("Aktualisieren"):
            load_models()
    with col_b:
        st.caption(f"{len(st.session_state.models_cache)} Modelle")

    if st.session_state.models_error:
        st.error(f"Modelle konnten nicht geladen werden: {st.session_state.models_error}")

# Wenn noch keine Modelle geladen: einmalig versuchen (ohne Polling-Schleife)
# Nur beim ersten Start, nicht bei jedem Rerun.
if not st.session_state.models_cache and st.session_state.models_error is None:
    load_models()

# Dropdown: Werte sind model_key, Anzeige kommt aus label
models = st.session_state.models_cache
model_options = [model_key(m) for m in models] if models else ["openai:gpt-4o-mini"]

# Label-Mapping für format_func
label_map = {model_key(m): m.get("label", model_key(m)) for m in models}
def format_model(k: str) -> str:
    return label_map.get(k, k)

# Default Auswahl stabil halten
if "selected_model_key" not in st.session_state:
    st.session_state.selected_model_key = model_options[0] if model_options else "openai:gpt-4o-mini"

selected_model_key = st.sidebar.selectbox(
    "KI-Modell",
    options=model_options,
    index=model_options.index(st.session_state.selected_model_key) if st.session_state.selected_model_key in model_options else 0,
    format_func=format_model,
)

st.session_state.selected_model_key = selected_model_key
routing_provider, routing_model = parse_model_key(selected_model_key)

master_prompt = st.sidebar.text_area(
    "Master-Plan",
    value="Analysiere das Bild professionell.",
)

st.sidebar.divider()
col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("Anhänge leeren"):
        reset_uploads()
        st.rerun()
with col2:
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

# Vorschau (kleiner darstellen)
if uploaded_images:
    if len(uploaded_images) > 3:
        st.warning("⚠️ Maximal 3 Bilder erlaubt. Es werden nur die ersten 3 verwendet.")
        uploaded_images = uploaded_images[:3]

    cols = st.columns(min(3, len(uploaded_images)))
    for i, img in enumerate(uploaded_images):
        with cols[i % len(cols)]:
            # deutlich kleinere Vorschau:
            st.image(img, caption=img.name, width=180)

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

    # Anhänge einfrieren
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

        # NEU: eindeutiges Routing
        "routing": {
            "provider": routing_provider,
            "model": routing_model,
            "label": format_model(selected_model_key),
        },

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

    reset_uploads()
    st.rerun()
