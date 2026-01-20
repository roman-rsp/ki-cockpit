import streamlit as st
import requests
import base64
import uuid
from typing import Any

# ------------------------------------------------------------
# KONFIGURATION (Secrets aus Streamlit Cloud)
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

# Freeze-Mechanik: wir speichern Anhänge beim Senden in Session-State
if "frozen_images" not in st.session_state:
    st.session_state.frozen_images = []

if "frozen_pdf" not in st.session_state:
    st.session_state.frozen_pdf = None

# Models Cache
if "models_cache" not in st.session_state:
    st.session_state.models_cache = []
if "models_error" not in st.session_state:
    st.session_state.models_error = None

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
# MODELS: Fetch + Normalize
# ------------------------------------------------------------
def normalize_models_response(payload: Any) -> list[dict]:
    """
    Erwartete Formen:
    - {"models":[...]}
    - [{"models":[...]}]
    - direkt: [...]
    """
    if isinstance(payload, list):
        if len(payload) == 0:
            return []
        # häufig: [{"models":[...]}]
        if isinstance(payload[0], dict) and "models" in payload[0]:
            models = payload[0].get("models")
            return models if isinstance(models, list) else []
        # alternativ: direkt Liste von Modellen
        if all(isinstance(x, dict) and "id" in x for x in payload):
            return payload
        return []

    if isinstance(payload, dict):
        models = payload.get("models")
        return models if isinstance(models, list) else []

    return []

def fetch_models() -> list[dict]:
    r = requests.get(
        N8N_MODELS_URL,
        auth=(N8N_BASIC_USER, N8N_BASIC_PASS),
        timeout=30,
        headers={"accept": "application/json"},
    )
    r.raise_for_status()
    data = r.json()
    models = normalize_models_response(data)

    # dedupe + stabile Sortierung nach label
    seen = set()
    clean = []
    for m in models:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        label = m.get("label") or mid
        provider = m.get("provider") or "unknown"
        cap = m.get("cap") if isinstance(m.get("cap"), list) else []
        key = (provider, mid)
        if not mid or key in seen:
            continue
        seen.add(key)
        clean.append({"id": mid, "label": str(label), "provider": str(provider), "cap": cap})

    clean.sort(key=lambda x: x["label"].lower())
    return clean

def refresh_models():
    try:
        st.session_state.models_cache = fetch_models()
        st.session_state.models_error = None
    except Exception as e:
        st.session_state.models_error = str(e)
        # Cache nicht wegwerfen – lieber alte Liste behalten

# initial einmal laden (ohne Button)
if not st.session_state.models_cache and st.session_state.models_error is None:
    refresh_models()

# ------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------
st.sidebar.title("Projekte")

project = st.sidebar.text_input("Projektname", value="Neues Projekt")

debug_mode = st.sidebar.toggle("Debug anzeigen", value=False)

with st.sidebar.expander("Modelle", expanded=True):
    col_a, col_b = st.columns([1, 2])
    with col_a:
        if st.button("Aktualisieren"):
            refresh_models()
            st.rerun()

    models = st.session_state.models_cache
    st.caption(f"{len(models)} Modelle")

    if st.session_state.models_error:
        st.warning(f"Models-Endpoint Fehler: {st.session_state.models_error}")

    if debug_mode:
        st.json({"models_preview": models[:10]})

# Auswahl: falls leer -> fallback
if st.session_state.models_cache:
    selected_model = st.sidebar.selectbox(
        "KI-Modell",
        st.session_state.models_cache,
        format_func=lambda m: m["label"],
        index=0,
    )
    model_id = selected_model["id"]
    model_provider = selected_model["provider"]
else:
    # Fallback (damit UI nicht bricht)
    model_id = "gpt-4o-mini"
    model_provider = "openai"
    st.sidebar.selectbox("KI-Modell", [f"{model_provider} · {model_id}"], index=0)

master_prompt = st.sidebar.text_area(
    "Master-Plan",
    value="Analysiere das Bild professionell.",
)

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

# Vorschau: kleiner darstellen
THUMB_WIDTH = 160

if uploaded_images:
    if len(uploaded_images) > 3:
        st.warning("⚠️ Maximal 3 Bilder erlaubt. Es werden nur die ersten 3 verwendet.")
        uploaded_images = uploaded_images[:3]

    cols = st.columns(min(3, len(uploaded_images)))
    for i, img in enumerate(uploaded_images):
        with cols[i % len(cols)]:
            st.image(img, caption=img.name, width=THUMB_WIDTH)

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

        # Wichtig: id + provider getrennt schicken (robuster fürs Routing)
        "model": model_id,
        "provider": model_provider,

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
