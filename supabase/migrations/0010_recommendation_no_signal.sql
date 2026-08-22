-- Adds 'no_signal' to the recommendations enum: whenever a pair's
-- reference horizon selected the naive/no-change backtest model
-- (app.prediction.backtest._select_model), current_rate exactly equals
-- expected_rate -- there's no basis to call that "act_now" with the same
-- confidence as a real directional forecast, even though the old
-- act_now/wait split's >= comparison would have silently classified it
-- that way (and did, for every all-naive currency, every single day).
alter table public.recommendations
    drop constraint recommendations_recommendation_check;
alter table public.recommendations
    add constraint recommendations_recommendation_check
        check (recommendation in ('act_now', 'wait', 'volatile', 'no_signal'));
