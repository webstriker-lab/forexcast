# Research: a distinctive visual design direction (#8)

Question: how to make ForexCast (React+Vite web, later Capacitor Android + iPhone PWA) look distinctive rather than generic AI output: skills, palette, typography, chart styles, chart libraries.

## 1. Claude Code design skills

### UI UX Pro Max
- **What:** MIT-licensed community skill by nextlevelbuilder. A local Python (stdlib only, no network) search + reasoning engine over a design dataset: ~79 UI styles, 192 palettes, 74 font pairings, 25 chart types, 22 stacks, 119 UX guidelines, 192 industry reasoning rules. Given a product description it emits a design system (pattern, style, colours, type, effects, anti-patterns, pre-delivery checklist). Has explicit Banking / Fintech-Crypto / Personal Finance rules; its fintech anti-patterns reject "AI purple/pink gradients". Source: [README](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/main/README.md).
- **Where:** https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
- **Install (Claude Code):**
  - `/plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill` then `/plugin install ui-ux-pro-max@ui-ux-pro-max-skill`
  - or `npx ui-ux-pro-max-cli init --ai claude` (CLI: `npm i -g ui-ux-pro-max-cli; uipro init --ai claude`)
  - Needs Python 3 on PATH.
- **Caveat:** it's a catalogue; used naively it converges on popular presets (glassmorphism etc.). Use it to generate a candidate system, then apply the anti-slop rules below.

### Anthropic `frontend-design` skill (alternative / complement)
Official skill at [anthropics/skills/skills/frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md). Not a dataset; a set of taste rules. Key points: pick type deliberately per brief; avoid cream+terracotta and near-black+acid-green palettes; avoid uniform rounded-grey-shadow SaaS cards and 01/02/03 numbering; one orchestrated motion moment over per-section fade-ins; "spend boldness in one place". Installable via `/plugin marketplace add anthropics/skills`.

Also available in this environment: the built-in `dataviz` skill (chart palette + validator) and `design` canvas skill for mockups before coding.

**Recommendation:** install UI UX Pro Max for a first-pass system (query: "forex remittance assistant, fintech, mobile, trustworthy"), then run the result through `frontend-design` rules and `dataviz` for chart colours. Prototype 2 directions in the `design` canvas before touching `frontend/`.

## 2. Palette & typography directions

Current app: Tailwind defaults (`bg-white rounded-lg shadow`, `rgb(59,130,246)` blue) = the generic look. Two directions (pick one):

**A. "Ledger" (recommended)** — calm, paper-and-ink trust.
- Ground: cool off-white `#F6F7F9` / dark `#0E1116` (true dark, not tinted).
- Ink: `#111827`; one brand accent, deep teal `#0F766E` (dark: `#2DD4BF`).
- Semantic: convert-now `#15803D`, wait `#B45309` (amber, not red: waiting isn't an error), risk `#B91C1C`.
- Type: **IBM Plex Sans** UI + **IBM Plex Mono** or **JetBrains Mono** for rates (tabular figures, `font-variant-numeric: tabular-nums`). Rates as the hero number, large mono.

**B. "Signal"** — bolder, one saturated brand colour (e.g. indigo-blue `#3346FF`) used only on the recommendation/signal element; everything else greyscale. Type: **Inter Tight** / **Geist** + **Geist Mono**.

Rules for either: one accent only; colour carries meaning (direction/confidence), never decoration; no gradients on data; 44px min touch targets; respect `prefers-color-scheme` (PWA + Capacitor status bar).

## 3. Chart styles

| Element | Style |
|---|---|
| **Signal gauge** | Half-circle (180°) arc, 3 segments (wait / neutral / convert) in muted tints, needle or filled arc to the score; big mono label under it ("Convert 62%"). Build as plain SVG (~40 lines), not a chart lib: crisp, tiny, animatable once on load. |
| **Forecast confidence band** | Historical line solid ink; forecast line dashed accent; band = filled area between `lower_bound` and `upper_bound` at ~12% accent opacity; vertical "today" rule; no points except hover crosshair. For multiple intervals (50/80/95) stack decreasing opacity (fan chart). |
| **Citation cards** | Compact list, not SaaS cards: source favicon + domain, headline (2-line clamp), relative time, sentiment pip (colour dot + text label). Tap opens source. Hairline dividers, no shadows. |
| **Chunked-conversion plan** | Horizontal timeline / stacked bar: each chunk a segment sized by amount, labelled date + amount + expected rate; or a step-line of cumulative % converted over time. Plain SVG/flex divs; charts libs are overkill. |

## 4. Chart libraries (mobile web + Capacitor)

Current: `chart.js ^4.4` + `react-chartjs-2 ^5.2` (`frontend/src/components/RateChart.tsx`, line + `Filler` band with separate upper/lower datasets).

| Library | Fit | Notes |
|---|---|---|
| **Chart.js (keep)** | Good | Canvas, touch tooltips work, already installed. Band via `fill: '-1'` between upper/lower datasets; add `chartjs-plugin-annotation` for the "today" line. Cheapest path. |
| **TradingView Lightweight Charts** | Very good for rate history | Canvas, built for financial time series, smooth pinch/drag, Area/Baseline/Line series ([docs](https://tradingview.github.io/lightweight-charts/docs)). **License requires TradingView attribution + link.** No native band series (needs custom series plugin). |
| **visx / plain SVG** | Best for bespoke gauge, plan, fan chart | Full design control, React-native, SSR-free; more code. |
| Recharts | OK | SVG, easy, but generic look and heavier with many points. |

**Recommendation:** keep Chart.js for the main rate+band chart (restyle only: remove Tailwind blue, dashed forecast, band fill, crosshair tooltip, tabular fonts). Hand-roll the signal gauge and chunk plan in SVG. Consider Lightweight Charts only if interactive pan/zoom on history becomes a requirement (accept the attribution).

## Sources
- https://github.com/nextlevelbuilder/ui-ux-pro-max-skill (README)
- https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md
- https://tradingview.github.io/lightweight-charts/docs
- Local: `frontend/package.json`, `frontend/src/components/RateChart.tsx`
