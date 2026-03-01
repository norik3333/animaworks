# Voice Chat Guide

Reference for voice conversations with Anima.
Browser microphone input → STT (speech recognition) → chat pipeline → TTS (speech synthesis) → browser playback.

## Architecture Overview

```
Browser (AudioWorklet 16kHz PCM)
  → WebSocket /ws/voice/{name}
    → VoiceSTT (faster-whisper)
      → ProcessSupervisor IPC → Anima chat (existing pipeline)
    → StreamingSentenceSplitter (sentence splitting)
      → TTS Provider (VOICEVOX / SBV2 / ElevenLabs)
    ← audio binary + JSON control messages
  ← VoicePlayback (Web Audio API)
```

Voice chat goes through the existing text chat pipeline. From Anima's perspective, it is processed the same as a normal chat message (the text has already been converted by STT).

---

## Dependencies and Installation

### STT (Speech Recognition)

Requires `faster-whisper`:

```bash
pip install faster-whisper
```

The Whisper model (default: `large-v3-turbo`) is downloaded automatically on first STT run.
For GPU use, a CUDA-capable `ctranslate2` is required.

### TTS (Speech Synthesis)

TTS runs as an external service and must be started separately:

| Provider | Features | How to Start | Default URL |
|----------|----------|--------------|-------------|
| **VOICEVOX** | Free, Japanese-focused, many character voices | Docker: `docker run -p 50021:50021 voicevox/voicevox_engine` | `http://localhost:50021` |
| **Style-BERT-VITS2** | High quality, custom voice models | Start SBV2 or AivisSpeech Engine | `http://localhost:5000` |
| **ElevenLabs** | Cloud API, multilingual, high quality | Set env var `ELEVENLABS_API_KEY` | Cloud (no local start) |

---

## Configuration

### Global Config (config.json `voice` section)

Default settings for all Anima:

```json
{
  "voice": {
    "stt_model": "large-v3-turbo",
    "stt_device": "auto",
    "stt_compute_type": "default",
    "stt_language": null,
    "stt_refine_enabled": false,
    "default_tts_provider": "voicevox",
    "audio_format": "wav",
    "voicevox": { "base_url": "http://localhost:50021" },
    "elevenlabs": { "api_key_env": "ELEVENLABS_API_KEY", "model_id": "eleven_flash_v2_5" },
    "style_bert_vits2": { "base_url": "http://localhost:5000" }
  }
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `stt_model` | `large-v3-turbo` | Whisper model name. Options: `tiny`, `base`, `small`, `medium`, `large-v3`, `large-v3-turbo` |
| `stt_device` | `auto` | `auto` (GPU preferred) / `cpu` / `cuda` |
| `stt_compute_type` | `default` | CTranslate2 quantization type: `default`, `int8`, `float16` |
| `stt_language` | `null` | Language code (`ja`, `en`, etc.). `null` for auto-detect |
| `stt_refine_enabled` | `false` | LLM post-processing of STT results (adds 1–3s latency when enabled) |
| `default_tts_provider` | `voicevox` | Default TTS provider: `voicevox` / `style_bert_vits2` / `elevenlabs` |
| `audio_format` | `wav` | TTS output audio format |

### Per-Anima Voice Config (status.json `voice` section)

Each Anima's `status.json` can have a `voice` key for per-Anima settings:

```json
{
  "voice": {
    "tts_provider": "voicevox",
    "voice_id": "3",
    "speed": 1.0,
    "pitch": 0.0,
    "extra": {}
  }
}
```

| Field | Description |
|-------|-------------|
| `tts_provider` | TTS provider for this Anima. Uses global default if unset |
| `voice_id` | Provider-specific voice ID (see below) |
| `speed` | Speech rate (1.0 = normal) |
| `pitch` | Pitch (0.0 = normal) |
| `extra` | Provider-specific additional parameters (optional) |

#### How to specify voice_id

| Provider | voice_id format | How to check |
|----------|-----------------|--------------|
| VOICEVOX | Speaker ID (numeric string), e.g. `"3"` = Zundamon | `curl http://localhost:50021/speakers` for list |
| Style-BERT-VITS2 | `model_id:speaker_id` or `model_id:speaker_id:style`. e.g. `0:0` | `curl http://localhost:5000/models/info` for list |
| ElevenLabs | voice_id string | ElevenLabs dashboard or API |

If unset or empty, the provider's default voice is used.

---

## WebSocket Protocol

Endpoint: `ws://HOST/ws/voice/{anima_name}`

### Authentication

On connect, authentication is performed by one of:

- **local_trust mode**: No authentication required
- **trust_localhost enabled and localhost connection**: Loopback connections require no auth (CSRF validation applied)
- **Otherwise**: Validated via `session_token` cookie. Invalid sessions are closed with 4001 Unauthorized

WebSocket sends cookies on HTTP Upgrade, so a logged-in browser is authenticated automatically.

### Connection Limits

- **1 Anima = 1 active session**: A new connection to the same Anima replaces the existing session (existing session is closed with 4000 "Replaced by new session")
- **Invalid name**: If `name` contains `/` or `..`, is empty, or starts with `.`, connection is closed with 4000 "Invalid anima name"

### Client → Server

| Type | Format | Description |
|------|--------|-------------|
| Audio data | binary | 16kHz mono 16-bit PCM binary |
| `{"type": "speech_end"}` | JSON | End-of-utterance notification → triggers STT |
| `{"type": "interrupt"}` | JSON | Stop TTS playback (barge-in) |

### Server → Client

| Type | Format | Description |
|------|--------|-------------|
| `{"type": "status", "state": "loading"}` | JSON | Session initializing (STT loading) |
| `{"type": "status", "state": "ready"}` | JSON | Session ready |
| `{"type": "transcript", "text": "..."}` | JSON | STT result text |
| `{"type": "response_start"}` | JSON | Anima response stream started |
| `{"type": "response_text", "text": "...", "done": false}` | JSON | Anima response text (chunk) |
| `{"type": "response_done", "emotion": "..."}` | JSON | Anima response complete (with emotion metadata) |
| `{"type": "thinking_status", "thinking": true/false}` | JSON | Extended thinking start/end |
| `{"type": "thinking_delta", "text": "..."}` | JSON | Extended thinking text chunk |
| TTS audio data | binary | TTS audio binary |
| `{"type": "tts_start"}` | JSON | TTS audio send start |
| `{"type": "tts_done"}` | JSON | TTS audio send complete |
| `{"type": "error", "message": "..."}` | JSON | Error notification |

---

## Frontend UI

The mic button appears on both dashboard and workspace chat screens.

After connecting, the server sends `status: loading` → `status: ready`; voice input can begin once ready.

### Voice Input Modes

| Mode | Action | Description |
|------|--------|-------------|
| **PTT (Push-to-Talk)** | Hold mic → release | Reliable control. Records only while pressed |
| **VAD (Voice Activity Detection)** | Automatic | Auto-detects speech start, records, sends when silent |

Toggled in the UI.

### Features

- **Volume control**: TTS playback volume slider
- **TTS indicator**: Visual feedback while Anima is speaking (separate from recording indicator)
- **Barge-in**: Talking while TTS is playing automatically interrupts Anima's voice

---

## TTS Provider Details

### VOICEVOX

- Free, open-source Japanese TTS engine
- 50+ character voices
- Runs locally (no internet needed)
- Docker: `docker run -p 50021:50021 voicevox/voicevox_engine`
- GPU: `docker run --gpus all -p 50021:50021 voicevox/voicevox_engine`

### Style-BERT-VITS2 / AivisSpeech

- High-quality Japanese TTS
- Can train and use custom voice models
- AivisSpeech Engine is a simpler SBV2-compatible option
- Runs locally

### ElevenLabs

- Cloud multilingual TTS API
- High-quality, natural voice
- Requires API key (env var `ELEVENLABS_API_KEY`)
- Usage-based billing

---

## Troubleshooting

### STT not working

- Confirm `faster-whisper` is installed: `pip show faster-whisper`
- On GPU, verify CUDA version of `ctranslate2`
- Try CPU mode: set `stt_device: "cpu"`

### TTS returns no audio

- Confirm TTS provider is running
  - VOICEVOX: `curl http://localhost:50021/speakers` returns response
  - SBV2: `curl http://localhost:5000/models/info` returns response
  - ElevenLabs: `ELEVENLABS_API_KEY` is set
- Check server logs for `TTS unavailable` errors
- If TTS is unavailable, only text responses are returned (no audio)

### Audio cuts out / high latency

- Check network bandwidth (streaming is real-time)
- Use a lighter `stt_model` (`base`, `small`)
- Ensure `stt_refine_enabled: false` (LLM post-processing adds latency)
- Run VOICEVOX/SBV2 in GPU mode

### Invalid voice_id, no audio

- Verify the `voice_id` exists for the provider
- Invalid IDs fall back to default voice and log a warning
- VOICEVOX: `curl http://localhost:50021/speakers | jq` to see valid IDs
- SBV2: `curl http://localhost:5000/models/info` for model list, specify as `model_id:speaker_id`

---

## Technical Notes

### VoiceSession internals

`core/voice/session.py` manages a single voice conversation session:

1. **Audio buffer**: Up to 60 seconds (16kHz × 16bit × 60s ≈ 1.9MB). Cleared on overflow
2. **Minimum utterance filter**: Audio under 0.35s or below RMS threshold (silence) is discarded
3. **STT**: Transcribes buffered audio when `speech_end` is received
4. **Voice mode suffix**: Appends `[voice-mode: Voice conversation. Respond concisely in spoken style, under 200 chars...]` to the message before sending to Anima
5. **Chat integration**: Sends text to existing chat pipeline via ProcessSupervisor IPC
6. **TTS pre-sanitization**: Strips Markdown and emotion tags before TTS
7. **Streaming response**: Splits Anima response into sentences (punctuation: 。！？、…)
8. **Sentence TTS**: TTS per sentence to minimize first-byte latency
9. **TTS health check**: Checks provider availability on first call (result cached)
10. **Concurrency guard**: Prevents multiple `speech_end` handlers from running in parallel

### StreamingSentenceSplitter

Japanese sentence splitting for streaming:
- Split immediately on sentence punctuation (。！？)
- Split on commas (、) and ellipsis (…) (improves latency for short responses)
- Split on line breaks
- Buffers incomplete sentences

### Barge-in

When the user starts talking during TTS:
1. Client sends `{"type": "interrupt"}`
2. Server stops current TTS processing
3. Client clears playback queue
4. Processing of new user utterance starts
