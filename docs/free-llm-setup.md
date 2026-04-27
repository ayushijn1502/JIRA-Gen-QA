# Gemini-only setup (free tier / POC)

This project uses **Google Gemini** only. There is no local LLM server.

## Checklist

1. **Create an API key**  
   Open [Google AI Studio](https://aistudio.google.com/apikey), create a key, and copy it.

2. **Put the key in config**  
   In `config.yaml` under `gemini:` set `api_key`, or export  
   `AUTOTEST_GEMINI__API_KEY`.

3. **Pick a cheap model** (recommended for free tier)  
   In `config.yaml`:

   ```yaml
   gemini:
     model_name: "gemini-2.5-flash-lite"
   ```

   Alternates if you hit limits: `gemini-2.5-flash`, `gemini-flash-latest`.  
   See [Gemini models](https://ai.google.dev/gemini-api/docs/models/gemini).

4. **Preflight (before each run)**  
   With `gemini.run_preflight: true` (default), the CLI calls the Generative Language API once to **verify the key and model** (`GET …/models/{model}`). It does **not** show “remaining” free quota—Google does not expose that in this API.

5. **Token guards (built in)**  
   - **`gemini.max_total_tokens_per_run`**: soft cap; the app refuses new LLM calls if the next call would likely exceed the budget, based on **cumulative `usage_metadata` from successful responses** plus a rough estimate for the next prompt. Set to `null` to disable.  
   - **`gemini.max_output_tokens`**: caps each response size (default `8192`).  
   - **`poc.max_test_scenarios: 2`**: only **two** planned tests (positive + negative) to limit prompt and output size.  
   - **`max_retries`**: each retry runs **generate** again (extra API calls); keep this low (default `2`).

6. **Run**  

   ```bash
   python main.py run YOUR-TICKET-KEY
   ```

   After a successful run, the CLI prints **reported cumulative tokens** for that process.

## “Could not reach generativelanguage.googleapis.com”

The preflight call uses the same host as normal Gemini chat. Check:

- Browser can open `https://ai.google.dev` or `https://generativelanguage.googleapis.com`
- VPN if your network or region blocks Google APIs
- Corporate proxy: set `HTTPS_PROXY` / `HTTP_PROXY` in the environment (the app uses `requests`, which picks these up)
- TLS issues: see the full chained error in the terminal; on macOS run **Install Certificates.command** for your Python build

To skip only the metadata check (not recommended until chat works too): `gemini.run_preflight: false`.

## Quota errors (429 / RESOURCE_EXHAUSTED)

The app retries with backoff. If errors persist: wait, switch to **flash-lite**, reduce `max_retries`, or use a paid tier / different project key.

## Optional: disable preflight

If you are offline from Google’s API except for chat calls, set `gemini.run_preflight: false` (not recommended for first-time setup).
