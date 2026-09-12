# Methodology of OSCILOT

## Data processing - observations

An observation represents the number of available parking spaces at a given 15-minute time point. If multiple measurements are available within a 15-minute interval, we use the most recent measurement. Missing intervals remain missing for the time being.

## Data processing - time

### Cyclical Time Features

Temporal information is incorporated into the model as additional features derived from the timestamp of each observation. The time of day and day of the week are represented using sine and cosine transformations to preserve their cyclical nature. This avoids treating values such as 23:45 and 00:00, or Sunday and Monday, as being far apart despite their temporal proximity.

For the time of day, the timestamp is converted to the number of minutes since midnight before applying the cyclical transformation. This preserves the 15-minute resolution of the parking data. The resulting features are `time_sin` and `time_cos`. The day of the week is represented analogously using `weekday_sin` and `weekday_cos`.

These features allow the model to learn recurring daily and weekly patterns in parking occupancy without requiring the model to infer the cyclical structure from raw hour or weekday numbers. Since all four features are derived deterministically from the timestamp, they can be generated both during model training and dynamically for future prediction times.


## Data processing - weather

### Weather Data Sources

Weather information is incorporated as an additional set of model features rather than being stored as part of the parking database. Weather data can be retrieved dynamically based on the timestamp for which a prediction is requested.

The primary weather data source is the **Open-Meteo Forecast API**, which provides the weather forecasts required for future predictions. Where historical forecast data is available, the **Open-Meteo Historical Forecast API** is preferred for model training and evaluation. This is particularly useful because it provides historical weather forecasts rather than only retrospectively observed weather conditions. Consequently, the model can be trained using weather information that would have been available at the time at which the prediction would actually have been made. This provides a more realistic representation of the information available to the deployed prediction system and reduces the risk of introducing information that would not have been known at prediction time.

However, the Historical Forecast API only provides coverage from approximately 2022 onwards. This prevents its use for the earlier parts of the parking dataset, which extend back to 2019. For historical periods not covered by the Historical Forecast API, **Meteostat** is used as a supplementary source of historical weather observations.

This results in the following hierarchy:

1. **Open-Meteo Historical Forecast API** for historical periods covered by its forecast archive.
2. **Meteostat** for earlier historical periods where historical forecast data is unavailable.
3. **Open-Meteo Forecast API** for future predictions in the deployed application.

The distinction between historical forecasts and historical observations is explicitly taken into account when interpreting the experiments. Historical forecast data is preferred because it more closely reflects the information that would have been available to the model at prediction time. For earlier periods, Meteostat provides the necessary historical weather information, but these observations represent the weather that actually occurred rather than the forecast that would have been available beforehand. Therefore, results involving the earlier data period are interpreted with this limitation in mind.


## Tested Models



## Experiments

Different experiments are constructed to see how good our model performs in this situations.

Experiment 0

2026-03-10 ─────────────────────────────────── 2026-09-02

first train / test split at
Train: 2026-03-10 00:00:00 -> 2026-07-28 19:00:00
Test: 2026-07-28 19:15:00 -> 2026-09-02 00:00:00

| Modell                                       |      MAE |     RMSE |
| ------------------                           | -------: | -------: |
| Last Value                                   |    90.14 |   122.27 |
| Weekly Naive                                 |    84.76 |   121.51 |
| Prophet                                      |    43.97 |    58.82 |
| LSTM + Scaling                               |     4.92 |     7.80 |
| LSTM / NO SCALING                            |   496.34 |   509.13 |
| LSTM + Scaling + Time and                    |          |          |
| Weather covariates                           |     3.99 |     5.58 |
| ARIMA                                        |     3.45 |     5.57 |

From this point, backed by science (-papers) i will try to add weekdays and weather forecast to LSTM + Scaling and see where it brings us.


Experiment A

Only 2026, the current year

Experiment B

Last two years (2024–2026) from the big gap until now

Experiment C

All data (2019–2026)