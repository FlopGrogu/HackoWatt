# Slide – Prediction model (layout C: model left, proof right)

## Assets (slides/assets/, transparent PNG, 2× resolution)
Use the `_dark` files on a dark slide background, the `_light` files on a light one.

| File | Place on a 16:9 slide |
|---|---|
| `model_diagram_*.png` | left half, below the title (≈ 47 % of the slide width) |
| `timeline_22sep_*.png` | right half, top |
| `result_*.png` | right half, bottom |

Google Slides: *Insert → Image → Upload from computer*. Re-render after changes: `sh slides/render_assets.sh`
(source: `slides/assets/source.html`).

## Text on the slide

**Title:** Forecasting *why* energy is used – not just how much

**Subtitle:** An LLM reads her calendar → the forecast knows when she's home

**Footer (small):** Simulated household in Warsaw · weather: Open-Meteo · LLM: Gemini 3.5 Flash-Lite, prompt without personal knowledge – only the address and habits learned from data

## Speaker notes (~40 s)

Energy use in this flat mostly depends on one question: is Aleksandra home?
Instead of only extrapolating the past, an LLM reads her calendar day by day and returns an away score from 0 to 100,
plus how many people are home. Together with her phone position and her habits, that drives four simple,
explainable models: physics for the heat pump, rules for washing machine and dishwasher, averages for the rest.

Here on the 22nd: nobody told the model about the airport – it inferred from "Paul lands 19:40" that she picks him up.

On two test weeks this halves the daily forecast error, and presence is right 98 % of the time instead of 63 %.

## If asked (backup answers)

- **Data:** the household is simulated (minute by minute, real Open-Meteo weather); the weather in the test period was
  the same forecast file the simulation used, so weather error is not included.
- **Biggest remaining error:** trips where she remembered holiday mode – the forecast assumes her usual behaviour
  (she forgets 7 of 10 times). That gap is exactly what the away-mode reminder targets.
- **Why an LLM:** fixed rules break on free text ("Paul's flight" means Paul leaves, not her); the LLM handled it
  without any hint in the prompt.
- **Cost:** one LLM call per calendar day, cached; re-run only when that day changes.
