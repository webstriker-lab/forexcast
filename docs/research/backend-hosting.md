# Free non-sleeping backend hosting for the ForexCast API

Research for [#7](https://github.com/webstriker-lab/forexcast/issues/7). Sources were checked on 2026-09-11. Only first-party docs and pricing pages are cited.

## Context

- The backend is FastAPI on uvicorn, deployed from `render.yaml` as a Render `plan: free` web service with `healthCheckPath: /health`.
- Dependencies include `statsmodels` and `scipy` (`backend/requirements.txt`). That makes imports heavy, so the instance needs roughly 512 MB of RAM and a cold boot is slow.
- Data lives in Supabase, which is hosted separately. Ingest, predict and recommend jobs run as GitHub Actions cron (`.github/workflows/*.yml`), not on the web host. The host only has to serve HTTP.

## Comparison

| Host | Free offer | Sleeps? | Cold start | Card required | Fit |
|---|---|---|---|---|---|
| **Render free** (current) | 750 instance-hours per workspace per month. When they run out, free services are suspended until next month. | Yes, after 15 minutes with no inbound traffic | About 1 minute | No | A single service needs at most 744 hours in a 31-day month, so a keep-alive ping keeps it up all month within the free hours. |
| **Koyeb free instance** | 1 per organization: 512 MB RAM, 0.1 vCPU, 2 GB SSD. Frankfurt or Washington, D.C. only. | Yes, scales to zero after 1 hour idle | Not documented | Yes, per the pricing FAQ ("to prevent fraud and abuse"), with a $29 pre-auth hold. Their blog says the card is only asked for when automatic human verification fails. | 0.1 vCPU is tight for statsmodels and scipy. It also still sleeps. |
| **Fly.io** | No free tier. The trial is 2 machine-hours or 7 days, whichever comes first. | Machines auto-stop | n/a | Yes. "All organizations ... require a credit card on file." | Not free. The smallest shared-cpu-1x costs about $2–3.3 per month. |
| **Railway** | $5 one-time trial credit for 30 days, then a Free plan with $1 of credit per month. Up to 1 GB RAM, shared vCPU. | No sleep by default, but $1 per month does not cover an always-on service | n/a | No for the trial | Runs out of credit. Not viable for 24/7 at zero cost. |
| **Google Cloud Run** | 2M requests, 180,000 vCPU-seconds and 360,000 GiB-seconds per month, plus 1 GB of egress from North America | Yes, scales to zero with request-based billing. An always-warm `min-instances` setting is billed per instance. | Seconds, but a heavy Python import adds to it | Yes. "A Google Cloud billing account is required to access the Google Cloud Free Tier." | Good fit if you accept cold starts and a card on file. Always-on means paying. |
| **Hugging Face Spaces** | CPU Basic hardware (2 vCPU, 16 GB) is free, but Docker and Gradio Spaces now **require a paid plan (PRO) to create**. Only Static Spaces are free. | Yes. Free hardware "will go to sleep" if unused. | Rebuild or restart | PRO subscription | Not free for a FastAPI Docker app. |

## Keep-alive ping and the terms of service

- Render's free-tier doc describes the 15-minute spin-down and a 750-hour monthly cap. It does **not** prohibit pinging. The only suspension condition it states is for a free service that "initiates an uncommonly high volume of traffic over the public internet". That covers outbound traffic, not a small number of inbound health checks. I found no anti-keep-alive clause in the Render pages I could fetch. The Terms and AUP pages did not render their text through the fetcher, so that part is unverified.
- **Ping source:** a GitHub Actions `schedule` running every 10–14 minutes against `/health` works, but GitHub runs scheduled workflows on a best-effort basis. Runs can be delayed or dropped at busy times. GitHub also disables scheduled workflows in public repos after 60 days without repository activity ([GitHub docs: events that trigger workflows](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#schedule)). Expect occasional cold starts even with the ping. An external uptime monitor is a more precise alternative.
- Egress for about 4,300 tiny pings per month is negligible against Render's bandwidth allowance.

## Answer

**Stay on Render free and add a keep-alive ping to `/health`.** None of the alternatives is both free and non-sleeping without a card:

- Fly.io has no free tier.
- Railway gives $1 of credit per month.
- Hugging Face needs PRO for Docker Spaces.
- Koyeb and Cloud Run both need a card, and both still scale to zero.

Render's 750 hours cover one always-on service, and pinging is not prohibited in any Render page I could fetch. Keep Supabase and the GitHub Actions cron as they are.

If you ever accept putting a card on file, **Cloud Run** (request-billed, within the free tier) is the strongest upgrade path. Cold starts remain.

## Sources

- Render free tier: https://render.com/docs/free
- Koyeb instances: https://www.koyeb.com/docs/reference/instances
- Koyeb pricing FAQ: https://www.koyeb.com/docs/faqs/pricing
- Fly.io pricing: https://fly.io/docs/about/pricing/
- Fly.io free trial: https://fly.io/docs/about/free-trial/
- Railway free trial: https://docs.railway.com/reference/pricing/free-trial
- Cloud Run pricing: https://cloud.google.com/run/pricing
- Google Cloud Free Tier: https://docs.cloud.google.com/free/docs/free-cloud-features
- Hugging Face Spaces overview: https://huggingface.co/docs/hub/spaces-overview
