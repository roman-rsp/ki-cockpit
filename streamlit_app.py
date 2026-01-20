import streamlit as st
import requests
import base64
import uuid

# ------------------------------------------------------------
# KONFIGURATION (Secrets aus Streamlit Cloud)
# ------------------------------------------------------------
N8N_WEBHOOK_URL = st.secrets["N8N_WEBHOOK_URL"]
N8N_MODELS_URL = st.secrets.get("N8N_MODELS_URL", "")
N8N_BASIC_USER = st.secrets["N8N_BASIC_USER"]
N8N_BASIC_PASS = st.secrets["N8N_BASIC_PASS"]

st.set_page_config(page_title="KI Cockpit", layout="wide")

THUMB_W = 160  # Thumbnail-Breite für Bildvorschau

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

# Model Catalog Cache
if "model_catalog" not in st.session_state:
    st.session_state.model_catalog = []

if "selected_model" not in st.session_state:
    st.session_state.selected_model = None

if "debug_mode" not in st.session_state:
    st.session_state.debug_mode = False


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
# MODEL CATALOG (aus n8n laden)
# ------------------------------------------------------------
def fetch_models() -> list[dict]:
    """
    Erwartet Response von n8n wie:
    { "models": [ { "id": "...", "label": "...", "provider": "...", "cap": [...] }, ... ] }
    """
    if not N8N_MODELS_URL:
        return []

    try:
        r = requests.get(
            N8N_MODELS_URL,
            auth=(N8N_BASIC_USER, N8N_BASIC_PASS),
            timeout=20,
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        data = r.json()

        models = data.get("models", [])
        if not isinstance(models, list):
            return []

        cleaned: list[dict] = []
        for m in models:
            if not isinstance(m, dict):
                continue

            mid = (m.get("id") or "").strip()
            provider = (m.get("provider") or "").strip()

            # Label fallback
            label = (m.get("label") or "").strip()
            if not label:
                label = f"{provider} · {mid}".strip(" ·")

            cap = m.get("cap") if isinstance(m.get("cap"), list) else []

            if mid and provider:
                cleaned.append({
                    "id": mid,
                    "provider": provider,
                    "label": label,
                    "cap": cap,
                })

        return cleaned

    except Exception as e:
        if st.session_state.get("debug_mode"):
            st.sidebar.caption(f"Model-Fetch Fehler: {e}")
        return []


def ensure_models_loaded():
    if not st.session_state.model_catalog:
        st.session_state.model_catalog = fetch_models()

    if st.session_state.model_catalog and not st.session_state.selected_model:
        st.session_state.selected_model = st.session_state.model_catalog[0]


# ------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------
st.sidebar.title("Projekte")

project = st.sidebar.text_input("Projektname", value="Neues Projekt")

# Debug Toggle in Session-State spiegeln
debug_mode = st.sidebar.toggle("Debug anzeigen", value=st.session_state.debug_mode)
st.session_state.debug_mode = debug_mode

# Modelle laden (initial)
ensure_models_loaded()

with st.sidebar.expander("Modelle", expanded=True):
    col_a, col_b = st.columns([1, 2])
    with col_a:
        if st.button("Aktualisieren"):
            st.session_state.model_catalog = fetch_models()
            if st.session_state.model_catalog:
                # Auswahl beibehalten, falls möglich
                if st.session_state.selected_model:
                    cur = st.session_state.selected_model
                    match = next(
                        (m for m in st.session_state.model_catalog
                         if m["id"] == cur.get("id") and m["provider"] == cur.get("provider")),
                        None
                    )
                    st.session_state.selected_model = match or st.session_state.model_catalog[0]
                else:
                    st.session_state.selected_model = st.session_state.model_catalog[0]
            st.rerun()

    models = st.session_state.model_catalog or []
    st.caption(f"{len(models)} Modelle")

    if debug_mode:
        st.sidebar.json({"models_preview": models[:10]})

# Fallback, falls gar keine Modelle geladen
if not st.session_state.model_catalog:
    st.session_state.model_catalog = [{
        "id": "gpt-4o-mini",
        "provider": "openai",
        "label": "OpenAI · gpt-4o-mini",
        "cap": ["text"],
    }]
    if not st.session_state.selected_model:
        st.session_state.selected_model = st.session_state.model_catalog[0]

# Selectbox: komplette Dicts als Options → zeigt garantiert alle
models = st.session_state.model_catalog
default_idx = 0
if st.session_state.selected_model:
    for i, m in enumerate(models):
        if m["id"] == st.session_state.selected_model.get("id") and m["provider"] == st.session_state.selected_model.get("provider"):
            default_idx = i
            break

st.sidebar.caption("KI-Modell")
selected_model = st.sidebar.selectbox(
    "KI-Modell",
    options=models,
    index=default_idx,
    format_func=lambda m: m.get("label") or f'{m.get("provider")} · {m.get("id")}',
    label_visibility="collapsed",
)
st.session_state.selected_model = selected_model

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

# Vorschau (kleiner)
if uploaded_images:
    if len(uploaded_images) > 3:
        st.warning("⚠️ Maximal 3 Bilder erlaubt. Es werden nur die ersten 3 verwendet.")
        uploaded_images = uploaded_images[:3]

    cols = st.columns(min(3, len(uploaded_images)))
    for i, img in enumerate(uploaded_images):
        with cols[i % len(cols)]:
            st.image(img, width=THUMB_W)
            st.caption(img.name)

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

    # Gewähltes Modell sauber senden
    selected = st.session_state.selected_model or {"id": "gpt-4o-mini", "provider": "openai"}

    payload = {
        "request_id": request_id,
        "message": prompt,
        "project": project,
        "provider": selected["provider"],  # <-- wichtig
        "model": selected["id"],
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
            headers={
                "X-Request-Id": payload["request_id"],
                "Accept": "application/json",
            },
            timeout=60,
        )

        if response.status_code in (401, 403):
            answer = "❌ Zugriff verweigert (Auth)."
            meta = {"error": "auth", "status_code": response.status_code}

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
