An observation represents the number of available parking spaces at a given 15-minute time point. If multiple measurements are available within a 15-minute interval, we use the most recent measurement. Missing intervals remain missing for the time being.

Experiment 0

2026-03-10 ─────────────────────────────────── 2026-09-02

first train / test split at
Train: 2026-03-10 00:00:00 -> 2026-07-28 19:00:00
Test: 2026-07-28 19:15:00 -> 2026-09-02 00:00:00

| Modell             |      MAE |     RMSE |
| ------------------ | -------: | -------: |
| Last Value         |    90.14 |   122.27 |
| Weekly Naive       |    84.76 |   121.51 |
| Prophet            |    43.97 |    58.82 |
| LSTM + Scaling     |     4.92 |     7.80 |
| LSTM / NO SCALING  |   496.34 |   509.13 |
| ARIMA              |     3.45 |     5.57 |

From this point, backed by science (-papers) i will try to add weekdays and weather forecast to LSTM + Scaling and see where it brings us.


Experiment A

Only 2026, the current year

Experiment B

Last two years (2024–2026) from the big gap until now

Experiment C

All data (2019–2026)