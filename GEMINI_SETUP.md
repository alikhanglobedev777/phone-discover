# Gemini setup

Mobile Discovery supports Gemini for AI-written recommendation explanations while keeping
catalog filtering, scoring, prices, and rankings deterministic. If Gemini is unavailable or
the free quota is exhausted, the API automatically returns the built-in explanation.

## Configure the key on Windows

From the project root, run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\configure-gemini.ps1 -TestConnection
```

The script prompts for the key securely, stores it only in `backend/.env.local`, selects
Gemini, and verifies the configured model. Do not put the key in React, source files, Git,
screenshots, or chat messages.

Start or restart Django:

```powershell
.\scripts\run-backend-native.ps1 -SkipInfrastructure
```

The startup banner shows the active provider. You can check it without exposing the key:

```powershell
cd .\backend
& .\.venv\Scripts\python.exe manage.py check_ai_provider
```

Add `--live` to contact Gemini and verify the key, model, quota, and connection.

## Provider modes

- `AI_PROVIDER=gemini`: use Gemini and fall back to deterministic explanations on errors.
- `AI_PROVIDER=openai`: use OpenAI and fall back to deterministic explanations on errors.
- `AI_PROVIDER=auto`: prefer Gemini when its key exists, otherwise OpenAI, otherwise deterministic.
- `AI_PROVIDER=deterministic`: never contact an external AI provider.

The default Gemini model is `gemini-3.6-flash`. Change `GEMINI_CHAT_MODEL` in
`backend/.env.local` if your Google AI Studio account exposes a different free-tier model.
