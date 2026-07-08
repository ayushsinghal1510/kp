"""Real-time speech translation with Soniox — configurable languages.

Everything real-time happens in the browser: the page captures the microphone,
opens a WebSocket straight to Soniox's real-time API, and renders the translation
live. That avoids WebRTC/media-proxy problems in hosted/proxied environments
(e.g. Lightning Studio) — the only outbound connection is a plain WSS from the
browser to Soniox.

The Python side:
  1. reads SONIOX_API_KEY (env or .env),
  2. mints a short-lived *temporary* API key so the real key never reaches the
     browser (https://soniox.com/docs/api-reference/auth/create_temporary_api_key),
  3. builds the STT/translation config from the sidebar controls.

Soniox translation notes (docs/translation/supported-languages):
  * 60 languages, same set usable as source or target ("3600+ language pairs").
  * one_way  -> translates ANY detected input language into ONE target_language.
  * two_way  -> bidirectional between exactly TWO languages (language_a/b).
  * There is no multi-target mode: one output language per stream (two for two_way).

Run with:
    uv run --package lv streamlit run lv/src/lv/app.py
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# Ground-truth docs:
#   https://soniox.com/docs/stt/api-reference/websocket-api
#   https://soniox.com/docs/stt/rt/real-time-translation
#   https://soniox.com/docs/translation/supported-languages
SONIOX_WS_URL = "wss://stt-rt.soniox.com/transcribe-websocket"
SONIOX_TEMP_KEY_URL = "https://api.soniox.com/v1/auth/temporary-api-key"
SONIOX_MODEL = "stt-rt-v5"

# All 60 Soniox-supported languages (name -> ISO code). Same set for source/target.
LANGUAGES: dict[str, str] = {
    "Afrikaans": "af", "Albanian": "sq", "Arabic": "ar", "Azerbaijani": "az",
    "Basque": "eu", "Belarusian": "be", "Bengali": "bn", "Bosnian": "bs",
    "Bulgarian": "bg", "Catalan": "ca", "Chinese": "zh", "Croatian": "hr",
    "Czech": "cs", "Danish": "da", "Dutch": "nl", "English": "en",
    "Estonian": "et", "Finnish": "fi", "French": "fr", "Galician": "gl",
    "German": "de", "Greek": "el", "Gujarati": "gu", "Hebrew": "he",
    "Hindi": "hi", "Hungarian": "hu", "Indonesian": "id", "Italian": "it",
    "Japanese": "ja", "Kannada": "kn", "Kazakh": "kk", "Korean": "ko",
    "Latvian": "lv", "Lithuanian": "lt", "Macedonian": "mk", "Malay": "ms",
    "Malayalam": "ml", "Marathi": "mr", "Norwegian": "no", "Persian": "fa",
    "Polish": "pl", "Portuguese": "pt", "Punjabi": "pa", "Romanian": "ro",
    "Russian": "ru", "Serbian": "sr", "Slovak": "sk", "Slovenian": "sl",
    "Spanish": "es", "Swahili": "sw", "Swedish": "sv", "Tagalog": "tl",
    "Tamil": "ta", "Telugu": "te", "Thai": "th", "Turkish": "tr",
    "Ukrainian": "uk", "Urdu": "ur", "Vietnamese": "vi", "Welsh": "cy",
}
CODE_TO_NAME = {code: name for name, code in LANGUAGES.items()}
LANGUAGE_NAMES = list(LANGUAGES.keys())


# --- Server-side key handling ------------------------------------------------
def _load_api_key() -> str | None:
    """Return SONIOX_API_KEY from the environment or a nearby .env file."""
    key = os.environ.get("SONIOX_API_KEY")
    if key:
        return key.strip()

    here = Path(__file__).resolve()
    candidates = [
        Path.cwd() / ".env",
        here.parent / ".env",              # src/lv/
        here.parents[2] / ".env",          # lv/
        here.parents[3] / ".env",          # kp/
    ]
    for env_path in candidates:
        if not env_path.is_file():
            continue
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if line.startswith("SONIOX_API_KEY"):
                _, _, value = line.partition("=")
                return value.strip().strip("'\"")
    return None


def _create_temporary_key(main_key: str) -> tuple[str, str]:
    """Mint a temporary API key scoped to the real-time WebSocket."""
    body = json.dumps(
        {"usage_type": "transcribe_websocket", "expires_in_seconds": 3600}
    ).encode()
    req = urllib.request.Request(
        SONIOX_TEMP_KEY_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {main_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data["api_key"], data.get("expires_at", "")


def _get_temp_key(main_key: str) -> str:
    """Cache a temp key in the session, refreshing well before it expires."""
    cached = st.session_state.get("temp_key")
    created_at = st.session_state.get("temp_key_at", 0.0)
    if cached and (time.time() - created_at) < 3000:  # 3600s TTL, refresh at 50m
        return cached
    key, _expires = _create_temporary_key(main_key)
    st.session_state.temp_key = key
    st.session_state.temp_key_at = time.time()
    return key


# --- Browser component (mic capture + Soniox WebSocket + live render) --------
def _component_html(
    temp_key: str, stt_config: dict, primary_label: str, secondary_label: str
) -> str:
    template = r"""
<div id="root">
  <style>
    #root { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #e8e8ec; }
    #bar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
    #btn { border: 0; border-radius: 999px; padding: 12px 22px; font-size: 15px; font-weight: 600;
           cursor: pointer; color: #fff; background: #16a34a; transition: background .15s; }
    #btn.rec { background: #dc2626; }
    #status { font-size: 13px; color: #9aa0aa; }
    #status .dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%;
                   background: #dc2626; margin-right: 6px; animation: pulse 1.1s infinite; }
    @keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: .25 } }
    .label { font-size: 12px; text-transform: uppercase; letter-spacing: .08em; color: #7c828d; margin: 14px 0 4px; }
    #en { font-size: 26px; line-height: 1.35; min-height: 40px; font-weight: 500; }
    #vi { font-size: 15px; line-height: 1.4; color: #9aa0aa; min-height: 22px; }
    .err { color: #f87171 !important; }
  </style>
  <div id="bar">
    <button id="btn">▶ Start</button>
    <span id="status">Idle — press Start and allow the microphone.</span>
  </div>
  <div class="label">__PRIMARY_LABEL__</div>
  <div id="en">…</div>
  <div class="label">__SECONDARY_LABEL__</div>
  <div id="vi">…</div>
</div>
<script>
(function () {
  const WS_URL = "__WS_URL__";
  const API_KEY = "__API_KEY__";
  const STT_CONFIG = __STT_CONFIG__;

  const btn = document.getElementById("btn");
  const statusEl = document.getElementById("status");
  const enEl = document.getElementById("en");
  const viEl = document.getElementById("vi");

  let ws = null, audioCtx = null, stream = null, procNode = null, srcNode = null;
  let running = false;
  let finalTr = "", finalOr = "";

  // srcdoc iframes are same-origin with the parent, so we can grant our own
  // frame microphone permission defensively before requesting the mic.
  try {
    const frames = window.parent.document.querySelectorAll("iframe");
    for (const f of frames) {
      if (f.contentWindow === window) f.setAttribute("allow", "microphone; camera");
    }
  } catch (e) { /* cross-origin: ignore */ }

  function setStatus(msg, isErr) {
    statusEl.innerHTML = (running && !isErr ? '<span class="dot"></span>' : '') + msg;
    statusEl.classList.toggle("err", !!isErr);
  }

  function handle(data) {
    if (data.error_code) { setStatus("Soniox error " + data.error_code + ": " + data.error_message, true); return; }
    let interimTr = "", interimOr = "";
    for (const t of (data.tokens || [])) {
      const text = t.text || "";
      if (!text) continue;
      const isTr = t.translation_status === "translation";
      if (t.is_final) { if (isTr) finalTr += text; else finalOr += text; }
      else { if (isTr) interimTr += text; else interimOr += text; }
    }
    enEl.textContent = (finalTr + interimTr).trim() || "…";
    viEl.textContent = (finalOr + interimOr).trim() || "…";
  }

  function floatToPCM16(float32) {
    const out = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
      let s = Math.max(-1, Math.min(1, float32[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }

  async function start() {
    finalTr = ""; finalOr = ""; enEl.textContent = "…"; viEl.textContent = "…";
    setStatus("Requesting microphone…");
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    } catch (e) {
      setStatus("Microphone blocked: " + e.name + " — " + e.message, true);
      return;
    }

    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    await audioCtx.resume();

    setStatus("Connecting to Soniox…");
    ws = new WebSocket(WS_URL);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      const config = Object.assign({ api_key: API_KEY }, STT_CONFIG);
      config.sample_rate = audioCtx.sampleRate;  // trust the real context rate
      ws.send(JSON.stringify(config));
      running = true;
      btn.textContent = "■ Stop"; btn.classList.add("rec");
      setStatus("Listening — speak now…");

      srcNode = audioCtx.createMediaStreamSource(stream);
      procNode = audioCtx.createScriptProcessor(4096, 1, 1);
      srcNode.connect(procNode);
      procNode.connect(audioCtx.destination);
      procNode.onaudioprocess = (ev) => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        ws.send(floatToPCM16(ev.inputBuffer.getChannelData(0)).buffer);
      };
    };

    ws.onmessage = (ev) => {
      try { const d = JSON.parse(ev.data); handle(d); if (d.finished) cleanup(); } catch (e) {}
    };
    ws.onerror = () => setStatus("WebSocket error — check the API key / network.", true);
    ws.onclose = () => { if (running) setStatus("Connection closed.", false); };
  }

  function cleanup() {
    running = false;
    btn.textContent = "▶ Start"; btn.classList.remove("rec");
    try { if (procNode) { procNode.disconnect(); procNode.onaudioprocess = null; } } catch (e) {}
    try { if (srcNode) srcNode.disconnect(); } catch (e) {}
    try { if (audioCtx) audioCtx.close(); } catch (e) {}
    try { if (stream) stream.getTracks().forEach(t => t.stop()); } catch (e) {}
    procNode = srcNode = audioCtx = stream = null;
  }

  function stop() {
    setStatus("Finishing…");
    try { if (ws && ws.readyState === WebSocket.OPEN) ws.send(new ArrayBuffer(0)); } catch (e) {}
    cleanup();
  }

  btn.onclick = () => { running ? stop() : start(); };
})();
</script>
"""
    return (
        template.replace("__WS_URL__", SONIOX_WS_URL)
        .replace("__API_KEY__", temp_key)
        .replace("__STT_CONFIG__", json.dumps(stt_config))
        .replace("__PRIMARY_LABEL__", primary_label)
        .replace("__SECONDARY_LABEL__", secondary_label)
    )


# --- Sidebar: build the STT/translation config -------------------------------
def _sidebar_config() -> tuple[dict, str, str]:
    st.sidebar.header("Translation settings")
    mode = st.sidebar.radio(
        "Mode",
        ["One-way", "Two-way"],
        help=(
            "One-way: translate any spoken language into one target.\n\n"
            "Two-way: bidirectional between two languages."
        ),
    )

    base = {
        "model": SONIOX_MODEL,
        "audio_format": "pcm_s16le",
        "sample_rate": 16000,
        "num_channels": 1,
        "enable_endpoint_detection": True,
    }

    if mode == "One-way":
        target_name = st.sidebar.selectbox(
            "Translate INTO (target)", LANGUAGE_NAMES,
            index=LANGUAGE_NAMES.index("English"),
        )
        st.sidebar.markdown("**Spoken language(s)** — the input")
        auto = st.sidebar.checkbox("Auto-detect any language", value=False)
        if auto:
            hints: list[str] = []
        else:
            hint_names = st.sidebar.multiselect(
                "Language hints (input)", LANGUAGE_NAMES, default=["Vietnamese"],
                help="Guides detection. Leave empty (or tick auto-detect) for any language.",
            )
            hints = [LANGUAGES[n] for n in hint_names]
        strict = st.sidebar.checkbox(
            "Restrict strictly to these languages", value=False,
            help="Sets language_hints_strict — only the hinted languages are recognized.",
            disabled=auto or not hints,
        )

        config = {
            **base,
            "translation": {"type": "one_way", "target_language": LANGUAGES[target_name]},
        }
        if hints:
            config["language_hints"] = hints
            if strict:
                config["language_hints_strict"] = True
        return config, f"{target_name} (translation)", "Original (as spoken)"

    # Two-way
    lang_a = st.sidebar.selectbox(
        "Language A", LANGUAGE_NAMES, index=LANGUAGE_NAMES.index("Vietnamese"),
    )
    lang_b = st.sidebar.selectbox(
        "Language B", LANGUAGE_NAMES, index=LANGUAGE_NAMES.index("English"),
    )
    if lang_a == lang_b:
        st.sidebar.warning("Pick two different languages for two-way mode.")
    config = {
        **base,
        "language_hints": [LANGUAGES[lang_a], LANGUAGES[lang_b]],
        "translation": {
            "type": "two_way",
            "language_a": LANGUAGES[lang_a],
            "language_b": LANGUAGES[lang_b],
        },
    }
    return config, f"Translation ({lang_a} ↔ {lang_b})", "Original (as spoken)"


# --- Streamlit page ----------------------------------------------------------
st.set_page_config(page_title="Soniox Live Translation", page_icon="🎙️")
st.title("🎙️ Live Speech Translation")

main_key = _load_api_key()
if not main_key:
    st.error(
        "No `SONIOX_API_KEY` found. Set it in the environment or add it to a "
        "`.env` file (in the project or `lv/` directory) as `SONIOX_API_KEY=...`."
    )
    st.stop()

stt_config, primary_label, secondary_label = _sidebar_config()

try:
    temp_key = _get_temp_key(main_key)
except Exception:  # noqa: BLE001
    st.session_state.pop("temp_key", None)
    st.error("Could not start the translation service. Please try again.")
    st.stop()

components.html(
    _component_html(temp_key, stt_config, primary_label, secondary_label),
    height=420,
    scrolling=True,
)
