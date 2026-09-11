# Research: multimodal models for the camera price check (#10)

Question: which vision LLM should the backend call (server-side, from a mobile web camera capture) to pull **amount + currency** off a price tag or menu photo? And is on-device OCR a workable fallback?

Researched 2026-09-11. All prices come from the vendors' own pricing and vision docs (links below). Latency and accuracy numbers are **not published** for this task by any vendor, so they have to come from our own benchmark (see "Next step").

## TL;DR

- **Default: Gemini Flash-Lite** (2.5 Flash-Lite at $0.10/M input tokens, or 3.1 Flash-Lite at $0.25/M), called through the existing `gemini` entry in `backend/app/agent/providers.py`. A ~1 MP photo costs about **$0.0001–0.0003**.
- **Accuracy escalation: Claude Haiku 4.5** (~$0.0013 per 1 MP image). It needs a native Anthropic Messages call, since the current adapter only speaks OpenAI-compatible APIs. Alternatively, reach it through OpenRouter, which is already a provider.
- **Avoid gpt-4o-mini for images.** Its image tokens carry a large multiplier (2833 base + 5667 per tile), so a 1 MP photo costs about $0.004, roughly 15–40x Gemini Flash-Lite, even though its text price is low.
- **Ambiguous symbols ($, kr, ¥, R) cannot be resolved from the pixels.** Have the model return `{amount, currency_symbol, iso_candidates[], confidence}`. Resolve to an ISO code server-side using the user's location or home/travel currency, and ask the user when it's still ambiguous. Don't trust a guessed ISO code.
- **On-device fallback: Tesseract.js is the only real option for a mobile *web* app.** ML Kit Text Recognition v2 is Android/iOS native only, with no web SDK. Tesseract.js returns raw text only, so amount and currency parsing becomes our regex/heuristics. Use it offline or when the LLM call fails, not as the main path.

## Cost per image (≈1000×1000 px JPEG, ~50 output tokens, output cost ignored)

| Model | Image token rule (primary source) | Tokens | Input price /1M | ≈ $/image |
|---|---|---|---|---|
| Gemini 2.5 Flash-Lite | 258 tokens per 768 px tile (≤384 px = 258 flat) | ~1032 | $0.10 | **$0.0001** |
| Gemini 3.1 Flash-Lite | same; `media_resolution` caps tokens/image | ~1032 | $0.25 | $0.00026 |
| Gemini 3.7/3.8 Flash | same | ~1032 | $0.75 (promo to 2026-12-31, then $1.50) | $0.0008 |
| Claude Haiku 4.5 | ⌈w/28⌉×⌈h/28⌉; standard tier caps at 1568 px / 1568 tokens | 1296 | $1.00 | $0.0013 (Anthropic's own example: $1.30/1k) |
| Claude Opus 5 | same; high-res tier to 2576 px / 4784 tokens | 1296 | $5.00 | $0.0065 |
| gpt-4o-mini (current adapter default) | tile-based: 2833 base + 5667/tile (high detail) | ~25,500 | $0.15 | $0.0038 |

Downscale on the client to about 1000–1300 px on the long edge before upload. Every vendor caps or tiles above that anyway, and a smaller upload means less mobile upload latency. Anthropic warns that heavy JPEG compression hurts text legibility.

## Integration notes (our codebase)

- `providers.py` already sends OpenAI-compatible `/chat/completions` to openai, deepseek, groq, openrouter and gemini (Gemini via its OpenAI-compat endpoint). An image goes in as an `image_url` content part with a `data:` URI, so Gemini, OpenAI and OpenRouter vision models need no new adapter. The default models (`gemini-2.0-flash`, `gpt-4o-mini`) need to be overridden per call to the models above.
- DeepSeek (`deepseek-chat`) and the Groq default are text-only, so the price check must pin a vision-capable provider or model rather than use the user's chat provider.
- OpenRouter charges the underlying provider's price and exposes Claude/Gemini/GPT/Qwen-VL behind one key. It's the cheapest way to A/B models without new adapter code.
- Use structured output (JSON schema / `response_format`) and reject results with confidence below a threshold.

## On-device OCR fallback

| Option | Runs in mobile browser? | Output | Notes |
|---|---|---|---|
| Tesseract.js | Yes (WASM, browser + Node) | raw text + boxes | Apache-2.0; wraps the unmodified Tesseract engine, so it's weak on stylised or angled price tags; needs a language data download |
| ML Kit Text Recognition v2 | **No**, Android/iOS SDK only | blocks/lines/symbols + confidence | Latin, Chinese, Devanagari, Japanese, Korean; free and on-device, but only useful if we ever ship a native wrapper (Capacitor, etc.) |

The fallback flow: OCR the text, regex for numbers next to currency symbols or codes, resolve the currency the same way as the LLM path, and have the user confirm.

## Next step (to get latency/accuracy numbers)

No vendor publishes price-tag extraction accuracy or per-image latency. Build a small holdout set of 30–50 real tag/menu photos (mix of $, kr, €, ¥, ₹, comma decimals). Run Gemini Flash-Lite, Haiku 4.5 and Tesseract.js on it, and record exact-match amount, currency-symbol accuracy and p50/p95 latency. This mirrors the existing holdout gate pattern used for forecasting.

## Sources

- Anthropic, Vision (token formula, limits, cost example): https://platform.claude.com/docs/en/build-with-claude/vision
- Google, Gemini API pricing: https://ai.google.dev/gemini-api/docs/pricing
- Google, Gemini image understanding (258 tokens/tile, `media_resolution`): https://ai.google.dev/gemini-api/docs/image-understanding
- OpenAI, pricing: https://developers.openai.com/api/docs/pricing
- OpenAI, Images & vision (tile/patch token rules, gpt-4o-mini 2833/5667): https://developers.openai.com/api/docs/guides/images-vision
- Google, ML Kit Text Recognition v2: https://developers.google.com/ml-kit/vision/text-recognition/v2
- Tesseract.js: https://github.com/naptha/tesseract.js
- Repo: `backend/app/agent/providers.py`
