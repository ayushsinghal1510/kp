# lv — Vietnamese → English live translation

Streamlit app that shows the **English** translation live as you speak
**Vietnamese**, using the
[Soniox real-time WebSocket API](https://soniox.com/docs/stt/api-reference/websocket-api)
(one-way translation, model `stt-rt-v5`).

## Run

```bash
# Put your key in lv/.env  ->  SONIOX_API_KEY=xxxxx   (env var also works)
uv run --package lv streamlit run lv/src/lv/app.py
```

Press **Start**, allow microphone access, and speak Vietnamese. The English
translation renders word-by-word; the original Vietnamese is shown underneath.

## Architecture

Real-time audio does **not** go through the Python server or WebRTC (which fails
behind hosted proxies like Lightning Studio). Instead:

- The Python side reads `SONIOX_API_KEY` and mints a short-lived **temporary API
  key** (`POST /v1/auth/temporary-api-key`, 1-hour TTL) so the real key never
  reaches the browser.
- A small JS component in the page captures the mic, downsamples to 16 kHz mono
  PCM, and opens a WebSocket **directly** from the browser to
  `wss://stt-rt.soniox.com/transcribe-websocket` — the only network hop is an
  outbound WSS to Soniox, so no media proxy or TURN server is needed.
- Tokens tagged `translation_status: "translation"` are the English output;
  `"original"` tokens are the Vietnamese transcript. `is_final` tokens are locked;
  non-final tokens render as live interim text.

## Requirements

- The page must be served over **https** (or localhost) — `getUserMedia`
  requires a secure context. Lightning Studio's proxy URL is https, so it works.
- Allow microphone access when the browser prompts.
