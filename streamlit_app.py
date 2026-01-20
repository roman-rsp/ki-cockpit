import streamlit as st
import requests
import base64
import uuid

# ------------------------------------------------------------
# SECRETS
# ------------------------------------------------------------
N8N_WEBHOOK_URL = st.secrets["N8N_WEBHOOK_URL"]
N8N_MODELS_URL = st.secrets["N8N_MODELS_URL"]
N8N_BASIC_USER = st.secrets["N8N_BASIC_USER"]
N8N_BASIC_PASS = st.secrets["N8N_BASIC_PASS"]

st.set_page_config(page_title="KI Cockpit", layout="wide")

# ------------------------------------------------------------
# SESSION STATE
# ------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "models" not in st.session_state:
    st.session_state.models = []

if "models_loaded" not in st.session_state:
    st.session_state.models_loaded = False

if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

if "frozen_images" not in st.session_state:
    st.session_state.frozen_images = []

if "frozen_pdf" not in st.session_state:
    st.session_state.frozen_pdf = None

# ------------------------------------------------------------
# MODEL CATALOG FETCH
# ------------------------------------------------------------
def load_models():
    try:
        r = requests.get(
            N8N_MODELS_URL,
            auth=(N8N_BASIC_USER, N8N_BASIC_PASS),
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()

        # 🔴 KRITISCHER PUNKT
        models = data[0]["models"] if isinstance(data, list) else data["models"]

        st.session_state.models = models
        st.session_state.models_loaded = True

    except Exception as e:
        st.error(f"❌ Modelle konnten nicht geladen werden: {e}")
        st.session_state.models = []

# ------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------
st.sidebar.title("Projekte")

project = st.sidebar.text_input("Projektname", value="Neues Projekt")
debug_mode = st.sidebar.toggle("Debug anzeigen", value=False)

st.sidebar.divider()

with st.sidebar.expander("Modelle", expanded=True):
    col1, col2 = st.columns([1, 2])

    with col1:
        if st.button("Aktualisieren"):
            load_models()

    with col2:
        st.caption(f"{len(st.session_state.models)} Modelle")

    if debug_mode:
        st.json(st.session_state.models)

# Auto-Load beim ersten Start
if not st.session_state.models_loaded:
    load_models()

# Dropdown
model_options = {
    f"{m['label']}": m["id"]
    for m in st.session_state.models
}

selected_model_label = st.sidebar.selectbox(
    "KI-Modell",
    list(model_options.keys()),
)

selected_model = model_options[selected_model_label]

master_prompt = st.sidebar.text_area(
    "Master-Plan",
    value="Analysiere das Bild professionell.",
)

# ------------------------------------------------------------
# CHAT RENDER
# ------------------------------------------------------------
st.title("🧠 KI Cockpit")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if debug_mode and msg.get("meta"):
            st.json(msg["meta"])

# ------------------------------------------------------------
# UPLOADS
# ------------------------------------------------------------
st.divider()
st.caption("📎 Anhänge (optional)")

uploaded_images = st.file_uploader(
    "Bilder (max. 3)",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
    key=f"img_{st.session_state.uploader_key}",
)

uploaded_pdf = st.file_uploader(
    "PDF",
    type=["pdf"],
    key=f"pdf_{st.session_state.uploader_key}",
)

# Vorschau (kleiner!)
if uploaded_images:
    uploaded_images = uploaded_images[:3]
    cols = st.columns(len(uploaded_images))
    for i, img in enumerate(uploaded_images):
        with cols[i]:
            st.image(img, caption=img.name, width=180)

if uploaded_pdf:
    st.caption(f"📄 {uploaded_pdf.name}")

# ------------------------------------------------------------
# INPUT
# ------------------------------------------------------------
prompt = st.chat_input("Deine Nachricht …")

if prompt:
    request_id = str(uuid.uuid4())

    st.session_state.messages.append({
        "role": "user",
        "content": prompt,
    })

    images = []
    for img in uploaded_images or []:
        images.append({
            "filename": img.name,
            "mime": img.type,
            "b64": base64.b64encode(img.getvalue()).decode(),
        })

    pdfs = []
    if uploaded_pdf:
        pdfs.append({
            "filename": uploaded_pdf.name,
            "mime": uploaded_pdf.type,
            "b64": base64.b64encode(uploaded_pdf.getvalue()).decode(),
        })

    payload = {
        "request_id": request_id,
        "project": project,
        "message": prompt,
        "model": selected_model,
        "master_prompt": master_prompt,
        "images": images,
        "pdfs": pdfs,
    }

    try:
        r = requests.post(
            N8N_WEBHOOK_URL,
            json=payload,
            auth=(N8N_BASIC_USER, N8N_BASIC_PASS),
            timeout=90,
        )
        r.raise_for_status()
        data = r.json()

        answer = data.get("content") or data.get("output") or "⚠️ Keine Antwort"
        meta = data if debug_mode else {}

    except Exception as e:
        answer = f"❌ Fehler: {e}"
        meta = {}

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "meta": meta,
    })

    st.session_state.uploader_key += 1
    st.rerun()
