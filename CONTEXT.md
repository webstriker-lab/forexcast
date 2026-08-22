# ForexCast

A forex rate tracking and prediction app: ingests real exchange rates, forecasts future rates per currency pair, and turns those forecasts into a plain "should I convert now or wait" signal — originally aimed at travelers deciding when to exchange money for a trip, not traders.

## Language

**Demonstrated edge**:
A forecast candidate's out-of-sample track record actually beating the naive baseline in backtesting, for a specific (currency, horizon) pair. Nothing is trusted to drive a shown recommendation without this — the standard applies uniformly to every forecasting approach the app uses or considers, present or future.
_Avoid_: Accuracy (too vague on its own — always ask "accuracy against what baseline, measured how")

**Naive baseline**:
The persistence forecast: "assume the rate doesn't change." The standard benchmark in FX forecasting (Meese & Rogoff, 1983) and the bar every other candidate model must clear, per pair and horizon, to be used instead of it.
_Avoid_: Random walk model (correct term in the literature, but naive baseline is this project's chosen name)

**Model-selected forecast**:
The forecast actually shown for a given (currency, horizon): whichever candidate model demonstrated the lower backtested error for that specific pair, not a fixed model applied uniformly across all currencies.

**no_signal**:
A recommendation state meaning the reference horizon's model-selected forecast is the naive baseline itself, so there is no directional signal to act on. Distinct from `volatile` (which reflects low confidence in a forecast that does exist) and from `wait`/`act_now` (which both imply a real directional signal was found).
