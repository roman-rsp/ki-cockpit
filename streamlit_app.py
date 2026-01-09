import streamlit as st
import requests
import base64
import uuid

# -----------------------
# KONFIGURATION
# -----------------------
N8N_WEBHOOK_URL = "https://n8n-f8jg4-u44283.vm.elestio.app/webhook/cockpit-chat"

st.set_page_config(page_title="KI Cockpit", layout="wide")

if "messages" not in st.session_state:
    st.session_state.messages = []


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
    Kleine Debug-Zusammenfassung fürs UI (wenn Debug-Switch aktiv ist).
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
        "keys": sorted(list(data.keys()))[:25],
        "error": data.get("error"),
    }


# -----------------------
# SIDEBAR
# -----------------------
st.sidebar.title("Projekte")

project = st.sidebar.text_input("Projektname", value="Neues Projekt")

model = st.sidebar.selectbox(
    "KI-Modell",
    # Empfehlung: Gemini als konkretes Modell wählen (Routing wird einfacher)
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
    # User Message im UI speichern
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("⏳ sende…")

        try:
            request_id = str(uuid.uuid4())

            # ✅ Minimales, stabiles Payload: KEINE history vom Client
            payload = {
                "request_id": request_id,
                "message": prompt,
                "project": project,
                "model": model,
                "master_prompt": master_prompt,
            }

            # ✅ Bild als Base64 (optional)
            if uploaded_file:
                image_bytes = uploaded_file.getvalue()
                payload["image_base64"] = base64.b64encode(image_bytes).decode("utf-8")
                payload["image_mime"] = uploaded_file.type
                payload["image_name"] = uploaded_file.name

            response = requests.post(
                N8N_WEBHOOK_URL,
                json=payload,
                headers={"X-Request-Id": request_id},
                timeout=60,
            )

            if response.status_code == 200:
                data = response.json()
                answer = extract_text(data) or "⚠️ Antwort leer."

                if debug_mode:
                    st.caption("Debug (Response-Meta):")
                    st.json(extract_debug(data))
            else:
                answer = f"❌ Fehler {response.status_code}: {response.text}"

        except Exception as e:
            answer = f"⚠️ Exception: {e}"

        placeholder.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})
