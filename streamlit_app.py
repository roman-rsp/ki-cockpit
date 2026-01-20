import streamlit as st
import requests
import base64
import uuid

# ------------------------------------------------------------
# KONFIGURATION (Secrets)
# ------------------------------------------------------------
N8N_WEBHOOK_URL = st.secrets["N8N_WEBHOOK_URL"]
N8N_MODELS_URL  = st.secrets["N8N_MODELS_URL"]
N8N_BASIC_USER  = st.secrets["N8N_BASIC_USER"]
N8N_BASIC_PASS  = st.secrets["N8N_BASIC_PASS"]

st.set_page_config(page_title="KI Cockpit", layout="wide")

# ------------------------------------------------------------
# SESSION STATE
# ------------------------------------------------------------
st.session_state.setdefault("messages", [])
st.session_state.setdefault("models", [])
st.session_state.setdefault("model_map", {})
st.session_state.setdefault("models_loaded", False)
st.session_state.setdefault("uploader_key", 0)

# ------------------------------------------------------------
# HELPER
# ------------------------------------------------------------
def auth():
    return (N8N_BASIC_USER, N8N_BASIC_PASS)


def load_models():
    try:
        r = requests.get(N8N_MODELS_URL, auth=auth(), timeout=10)
        r.raise_for_status()
        data = r.json()

        models = data.get("models", [])
        model_map = {m["label"]: m["id"] for m in models}

        st.session_state.models = models
        st.session_state.model_map = model_map
        st.session_state.models_loaded = True

    except Exception as e:
        st.session_state.models = []
        st.session_state.model_map = {}
        st.session_state.models_loaded = False
        st.error(f"Modelle konnten nicht geladen werden: {e}")


def add_message(role, content, meta=None):
    st.session_state.messages.append({
        "id": str(uuid.uuid4()),
        "role": role,
        "content": content,
        "meta": meta or {}
    })


# ------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------
st.sidebar.title("Projekte")

project = st.sidebar.text_input("Projektname", "Neues Projekt")

debug_mode = st.sidebar.toggle("Debug anzeigen", False)

st.sidebar.divider()
st.sidebar.subheader("Modelle")

col1, col2 = st.sidebar.columns([1, 2])
with col1:
    if st.button("↻"):
        load_models()

with col2:
    st.caption(f"{len(st.session_state.models)} Modelle")

if not st.session_state.models_loaded:
    st.info("Bitte Modelle aktualisieren")

if st.session_state.model_map:
    selected_label = st.sidebar.selectbox(
        "KI-Modell",
        list(st.session_state.model_map.keys())
    )
    selected_model = st.session_state.model_map[selected_label]
else:
    selected_model = None
    st.sidebar.selectbox("KI-Modell", ["– keine Modelle –"])

master_prompt = st.sidebar.text_area(
    "Master-Plan",
    "Analysiere das Bild professionell."
)

# ------------------------------------------------------------
# HEADER
# ------------------------------------------------------------
st.title("🧠 KI Cockpit")

# ------------------------------------------------------------
# CHAT
# ------------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if debug_mode and msg["meta"]:
            st.json(msg["meta"])

# ------------------------------------------------------------
# INPUT
# ------------------------------------------------------------
st.divider()
st.caption("📎 Anhänge (optional)")

uploaded_images = st.file_uploader(
    "Bilder (max. 3)",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
    key=f"img_{st.session_state.uploader_key}",
    label_visibility="collapsed"
)

uploaded_pdf = st.file_uploader(
    "PDF",
    type=["pdf"],
    key=f"pdf_{st.session_state.uploader_key}",
    label_visibility="collapsed"
)

# 🔽 kleinere Bild-Vorschau
if uploaded_images:
    cols = st.columns(min(3, len(uploaded_images)))
    for i, img in enumerate(uploaded_images[:3]):
        with cols[i]:
            st.image(img, width=140)

prompt = st.chat_input("Deine Nachricht …")

# ------------------------------------------------------------
# SENDEN
# ------------------------------------------------------------
if prompt and selected_model:
    add_message("user", prompt)

    images_payload = []
    for img in (uploaded_images or [])[:3]:
        images_payload.append({
            "filename": img.name,
            "mime": img.type,
            "b64": base64.b64encode(img.getvalue()).decode()
        })

    pdfs_payload = []
    if uploaded_pdf:
        pdfs_payload.append({
            "filename": uploaded_pdf.name,
            "mime": uploaded_pdf.type,
            "b64": base64.b64encode(uploaded_pdf.getvalue()).decode()
        })

    payload = {
        "request_id": str(uuid.uuid4()),
        "project": project,
        "model": selected_model,
        "message": prompt,
        "master_prompt": master_prompt,
        "images": images_payload,
        "pdfs": pdfs_payload,
    }

    r = requests.post(
        N8N_WEBHOOK_URL,
        json=payload,
        auth=auth(),
        timeout=60
    )

    if r.ok:
        data = r.json()
        answer = data.get("output") or data.get("content") or "⚠️ Leere Antwort"
        add_message("assistant", answer, data if debug_mode else None)
    else:
        add_message("assistant", f"❌ Fehler {r.status_code}")

    st.session_state.uploader_key += 1
    st.rerun()
