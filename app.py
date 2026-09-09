import pandas as pd # type: ignore
#students = pd.Series(['Al', 'Bo', 'Ce'], name = 'students')
#print("Lalala this one tries the CI pardy")
#print(students)
import requests
from io import StringIO
from sqlalchemy import Engine, create_engine, text
from pathlib import Path
import time
from sqlalchemy.exc import OperationalError, SQLAlchemyError
import seaborn as sns
import matplotlib.pyplot as plt
from statsmodels.graphics.tsaplots import plot_acf
import numpy as np
import matplotlib.dates as mdates
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from darts import TimeSeries
from darts.models import ARIMA
from prophet import Prophet
from prophet.diagnostics import cross_validation
from darts.models import RNNModel
from darts.dataprocessing.transformers import Scaler

engine = None

def resetDatabaseContent(engine: Engine) -> bool:
  """
    Delete all content from the database tables.

    This is necessary because, when working with Docker, restarting the
    application and using ``if_exists="append"`` with ``to_sql`` can result
    in duplicated data.

    Returns:
      True if the database content was deleted successfully, otherwise False.
  """
  returnvalue = True
  try:
    with engine.begin() as conn: #i use a transaction for this
      conn.execute(text("DELETE FROM lots"))
      conn.execute(text("DELETE FROM parkingspaces"))
      # <- because of foreign keys i need to delete first lots and only then parkinspaces
  except SQLAlchemyError as e:
    print(f"Database reset failed: {e}")
    returnvalue = False
  return returnvalue


def initDatabase(resetDb: bool = False) -> Engine:
  # TODO: Add boolean to catch if it was successful?
  """
    Initialize the database.

    Args:
      resetDb: Whether to reset the existing database content before
      initializing it. Default is do not reset.

    Returns:
      initialized database engine.
  """
  global engine
  schema = "oscilot"
  host = "db"
  user = "root"
  password = Path("/run/secrets/db-password").read_text().strip()
  port = 3306
  connection_string = f'mysql+pymysql://{user}:{password}@{host}:{port}/{schema}'
  engine = create_engine(connection_string)
# following arose because of docker-timing-problems but in real world szenarios this mitght be a good idea too:
  for attempt in range(30):
      try:
          with engine.connect() as conn:
              print("Database connected!")
              break
      except OperationalError:
          print(f"Database not ready, retry {attempt + 1}/30")
          time.sleep(2)
  else:
      raise Exception("Database connection failed")
  if resetDb:
    successfulReseted = resetDatabaseContent(engine)
    print(f"Database reset successful: {successfulReseted}")
  return engine


def getEngine() -> Engine:
  """
    Return the database engine, initializing it if necessary.

    Returns:
      The initialized SQLAlchemy database engine.
  """
  global engine
  if engine is None:
      engine = initDatabase()
  return engine



def getAllDataFromParkingDecks() -> pd.DataFrame:
  """
    Retrieves historical data from 2019 to the latest available date,
    which is typically about one day behind the current date.
    Also gets data from subdirectories of data.

    Returns:
      DataFrame with all informations.
  """
  api_url = "https://api.github.com/repos/codeformuenster/parking-decks-muenster/contents/data"
  def get_csv_files(url):
    response = requests.get(url)
    response.raise_for_status()
    print("Begin getting files")
    for file in response.json():
      if file["type"] == "file" and file["name"].endswith(".csv"):
        yield file["download_url"]
        #break #this is to only get first file for debug purposes
      elif file["type"] == "dir":
        yield from get_csv_files(file["url"])

  dataframes = []

  for csv_url in get_csv_files(api_url):
    csv_response = requests.get(csv_url)
    csv_response.raise_for_status()
    print(f"Downloading CSV: {csv_url}")
    dataframes.append(
        pd.read_csv(StringIO(csv_response.text))
    )

  if not dataframes:
    return pd.DataFrame()
  print("Concatenate files to dataframe")
  df = pd.concat(dataframes, ignore_index=True, sort=False) #slightly more efficient with collecting data and concatening all at once.
  return df #hopefully this works? this will be a heck of a dataframe maybe later just slice the new stuff?


def saveDataFrameToDB(engine: Engine, df: pd.DataFrame, table_name: str) -> bool:
  """
    Save a DataFrame to a database table.

    The DataFrame must contain the columns required by the target table.
    Columns not provided by the DataFrame are filled by the database using
    their default values.

    Args:
      engine: The SQLAlchemy engine used to connect to the database.
      df: The DataFrame to save.
      table_name: The name of the database table to append the data to.

    Returns:
      True if saving to SQL was successful, False otherwise.
  """
  returnvalue = True
  try:
    df.to_sql(table_name, if_exists='append', con=engine, index=False)
  except Exception as e:
    returnvalue = False
    print(f"Failed to save DataFrame to '{table_name}': {e}")
  return returnvalue


def getLotsOfParkinspaceNo(engine: Engine, no: int) -> pd.DataFrame:
    query = text("""
        SELECT *
        FROM lots
        WHERE parkingId = :no
        ORDER BY timepoint
    """)

    return pd.read_sql(query, con=engine, params={"no": no})

def getParkingspaces(engine: Engine) -> pd.DataFrame:
  return pd.read_sql("parkingspaces", con=engine)

def getLots(engine: Engine) -> pd.DataFrame:
  return pd.read_sql("SELECT * FROM lots ORDER BY parkingId, timepoint", con=engine)

def prepareDataForDB(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
  """
    Args:
      df: DataFrame of the format getAllDataFromParkingDecks returns
      (columns per example: 'Datum und Uhrzeit', 'PH Coesfelder Kreuz', 'PH Theater', 'PP Hörsterplatz',
      'PH Alter Steinweg', 'Busparkplatz', 'PP Schlossplatz Nord', 'PP Schlossplatz Süd',
      'PH Aegidii', 'PP Georgskommende', 'PH Münster Arkaden', 'PH Karstadt', 'PH Stubengasse',
      'PH Bremer Platz', 'PH Engelenschanze', 'PH Bahnhofstraße', 'PH Cineplex', 'PH Stadthaus 3',
      'PP Hafenmarkt', 'TG Hafenmarkt', 'Halle Münsterland P1')
      In general, 'Datum und Uhrzeit' and then the names of the parking decks

    Returns:
      tuple of
      First DataFrame: df fitted to parkingspaces in database (min columnnames: "id", "columnName")
      Second DataFrame: df fitted to lots in database
        (min columnnames: "parkingId", "timepoint", "amount")
  """

  #1. ignore rows whose "Datum und Uhrzeit" isnt in a datetime format as there is sometimes
  # "Anzahl Parkplätze gesamt" contained
  df = df[pd.to_datetime(df["Datum und Uhrzeit"], errors="coerce").notna()] #filter to filter out rows without correct datetime (happens somteimes)
  #2. build df for parkingspaces
    #generate IDs since existing DB data may exist in db.
  psdf = getParkingspaces(getEngine())
  if psdf.empty:
    lastid = 0 #ids will begin at 1
  else:
    lastid = psdf["id"].max() # better than last row because independend of order of data in db
  nextid = lastid + 1
  parkingdecks = df.columns.drop(['Datum und Uhrzeit'])
  returnedPdDf = pd.DataFrame()
  returnedPdDf['columnName'] = parkingdecks
  returnedPdDf['id'] = range(nextid, nextid+len(returnedPdDf)) #as the last value is exclusive

  #3. build df for lots
  #list of dfs with "Datum und Uhrzeit" and the values of one Parking Lot
  lots = []
  mapping = returnedPdDf.set_index("columnName")["id"]
  workingDf = df.rename(columns= mapping) #rename parkingspaces names to parkingspaces ids
  returnedLotDf = workingDf.melt(id_vars="Datum und Uhrzeit", var_name="parkingId", value_name="amount")
  returnedLotDf = returnedLotDf.rename(columns={"Datum und Uhrzeit": "timepoint"})
  # If a parkingdeck doesnt exist in a certain point of time it will be represented here as amount = NaN
  returnedLotDf = returnedLotDf.dropna(subset=["amount"])
  returnedLotDf = returnedLotDf.drop_duplicates() #needed... :shrug:
  print("Which values are in my columns?")
  amount_numeric = pd.to_numeric(
    returnedLotDf["amount"],
    errors="coerce"
  )
  print(returnedLotDf.loc[amount_numeric.isna(), "amount"].value_counts(dropna=False))
  print("---------------------")
  #pd.set_option("display.max_rows", None)
  #keiDf = returnedLotDf[returnedLotDf["amount"] == "kei"].groupby("parkingId").first()
  #print(keiDf)
  #amount has still "kei", "bes" and "ges" last two are "geschlossen", "besetzt" "kei" is "keine Angabe" so no information
  print("---------------------")
  print("how long is my dataframe?")
  print(len(returnedLotDf))
  # I save the status for better prediction
  returnedLotDf['status'] = 'frei'
  # replace bes with 0 because bes is besetzt so 'full'.
  returnedLotDf.loc[returnedLotDf['amount'] == 'bes', 'status'] = 'bes'
  returnedLotDf.loc[returnedLotDf['amount'] == 'bes', 'amount'] = 0
  # ges is geschlossen so closed. This will count as 0 parking lots with the status ges
  returnedLotDf.loc[returnedLotDf['amount'] == 'ges', 'status'] = 'ges'
  returnedLotDf.loc[returnedLotDf['amount'] == 'ges', 'amount'] = 0
  # kei is keine Angabe so no information. I have to drop them.
  returnedLotDf = returnedLotDf.drop(returnedLotDf[returnedLotDf['amount'] == 'kei'].index)
  returnedLotDf = returnedLotDf.drop_duplicates(subset=['parkingId', 'timepoint'])
  return returnedPdDf, returnedLotDf

def resetDatabaseAndImportAllData() -> bool:
  """
    Deletes all database content and fills it up completely from scratch with all data from 2019 - now

    Returns:
      if saving all data was successful it returns True, otherwise False
  """
  returnvalue = False
  engine = initDatabase(resetDb=True)
  print("Database initialized")
  dataFromWebDf = getAllDataFromParkingDecks()
  print("Got data")
  parkingspacesDf, lotsDf = prepareDataForDB(dataFromWebDf)
  print("prepared data")
  parkSucc = saveDataFrameToDB(engine, parkingspacesDf, 'parkingspaces')
  if(parkSucc):
    print("Saving parkingspaces data successful!")
  lotsSucc = saveDataFrameToDB(engine, lotsDf, 'lots')
  if(lotsSucc):
    print("Saving lots data successful!")
  if(parkSucc & lotsSucc):
    returnvalue = True
  return returnvalue

def analyzeDataOfLots(lotsDf: pd.DataFrame):
  """
    Analyzes the lots data and prints images of it in output. It will overwrite old images there.

    Args:
      DataFrame one get from database for lots.
  """
  # analizing oscillations. 14 days:
  lotsDf["timepoint"] = pd.to_datetime(lotsDf["timepoint"])
  sample = lotsDf[(lotsDf["timepoint"] >= "2025-06-01") &
                  (lotsDf["timepoint"] < "2025-06-15")
                ]
  sns.lineplot(
    data=sample,
    x="timepoint",
    y="amount"
  )
  plt.xticks(rotation=45)
  plt.savefig("/app/output/twoWeeks.png")
  plt.close()

  # analizing amount per time:
  lotsDf["time"] = lotsDf["timepoint"].dt.strftime("%H:%M")
  lotsDf["date"] = lotsDf["timepoint"].dt.date
  sample = lotsDf[
    #(lotsDf["parkingId"] == 1) &
    (lotsDf["timepoint"] >= "2025-06-01") &
    (lotsDf["timepoint"] < "2025-06-15")
  ]
  sns.lineplot(
    data=sample,
    x="time",
    y="amount",
    hue="date"
  )
  plt.xticks(rotation=45)
  plt.savefig("/app/output/amountPerTime.png")
  plt.close()

  #workday vs weekend
  #lotsDf["weekday"] = lotsDf["timepoint"].dt.day_name()
  #pattern = (
  #    lotsDf.loc[lotsDf['parkingId'] == 1]
  #    .groupby(["weekday", "time"])
  #    ["amount"]
  #    .mean()
  #    .reset_index()
  #)
  #sns.lineplot(
  #    data=pattern,
  #    x="time",
  #    y="amount",
  #    hue="weekday"
  #)
  #plt.xticks(rotation=45)
  #plt.savefig("/app/output/workdayVsWeekday.png")
  #plt.close()

  # Workday vs. weekend / weekday patterns

  lotsDf["weekday"] = lotsDf["timepoint"].dt.day_name()
  weekday_order = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday"
  ]

  lotsDf["weekday"] = pd.Categorical(
    lotsDf["weekday"],
    categories=weekday_order,
    ordered=True
  )

  # Round timestamps to 30-minute intervals
  lotsDf["time_30min"] = lotsDf["timepoint"].dt.floor("30min")

  # Use one common date so Seaborn gets a real datetime axis
  lotsDf["time"] = pd.to_datetime(
    "2000-01-01 " + lotsDf["time_30min"].dt.strftime("%H:%M:%S")
  )
  pattern = (
    lotsDf #.loc[lotsDf["parkingId"] == 1]
    .groupby(["weekday", "time"], observed=True)["amount"]
    .mean()
    .reset_index()
  )

  sns.lineplot(
    data=pattern,
    x="time",
    y="amount",
    hue="weekday",
    hue_order=weekday_order
  )

  plt.xticks(rotation=45)
  plt.title("Average parking occupancy by weekday")
  plt.xlabel("Time of day")
  plt.ylabel("Average amount")
  # Show only the time on the x-axis

  plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
  plt.tight_layout()
  plt.savefig("/app/output/workdayVsWeekday.png")
  plt.close()



  # autocorrelation
  #df = lotsDf.loc[lotsDf['parkingId'] == 1]
  df = lotsDf
  series = df.set_index("timepoint")["amount"]
  plot_acf(
    series.dropna(),
    lags=7 * 24 * 12
  )
  plt.savefig("/app/output/autocorrelation.png")
  plt.close()

  #which frequencies happen often
  values = lotsDf.loc[:, "amount"].dropna().values
  fft = np.fft.rfft(values)
  power = np.abs(fft)
  freq = np.fft.rfftfreq(
    len(values),
    d=5 * 60
  )
  plt.savefig("/app/output/frequencies.png")
  plt.close()

  #did the system change over years?
  monthly = (
    df.set_index("timepoint")
      .resample("ME")["amount"]
      .mean()
  )
  monthly.plot()
  plt.savefig("/app/output/systemchanged.png")
  plt.close()

  #heatmap
  sample = df[ #as df is for only parkingId==1
      (df["timepoint"] >= "2026-08-17") &
      (df["timepoint"] < "2026-08-31")
  ].copy()
  sample["date"] = sample["timepoint"].dt.date
  sample["time"] = sample["timepoint"].dt.strftime("%H:%M")
  pivot = sample.pivot_table(
    index="date",
    columns="time",
    values="amount",
    aggfunc="mean"
  )
  sns.heatmap(pivot)
  plt.savefig("/app/output/heatmap.png")
  plt.close()

  sns.lineplot(data=lotsDf, x="timepoint", y="amount", hue="parkingId", palette="tab20")
  print("saving graph")
  plt.savefig("/app/output/graph.png")
  plt.close()
  print("saved")


def baselineModel(df: pd.DataFrame, predictionTimepoint: pd.Timestamp) -> float:
  """
  Predict the available parking spaces at a given timepoint
  using the last known value.

  Args:
    df: DataFrame with training data
    predictionTimepoint: timestamp of which one would like a prediction

  Returns:
    A float value because of possible interpolation, normally it should be int.

  """
  previousValues = df.loc[df.index < predictionTimepoint, "amount"]
  return previousValues.iloc[-1]

def predictBaselineValues(df: pd.DataFrame, predictionTimepoints: pd.Series) -> pd.DataFrame:
  """
    Predicts the available parking spaces for a series of timepoints.

    df: DataFrame with training data
    prediction: Series with only timestamps in it

    Returns:
      DataFrame with the prediction timepoints as index and the predicted amounts in the 'amount' column.
  """
  returnvalue = pd.DataFrame(index=predictionTimepoints)
  for each in predictionTimepoints:
    res = baselineModel(df, each)
    returnvalue.loc[each, 'amount'] = res
  return returnvalue

def weekdayBaselineModel(df: pd.DataFrame, predictionTimepoint: pd.Timestamp) -> float:
  """
  Predict the available parking spaces at a given timepoint
  using the known value from last week at this time.

  Args:
    df: DataFrame with training data
    predictionTimepoint: timestamp of which one would like a prediction

  Returns:
    A float value because of possible interpolation, normally it should be int.

  """
  previousTimepoint = predictionTimepoint - pd.Timedelta(weeks=1)
  index = df.index.get_indexer(
    [previousTimepoint],
    method="nearest"
  )[0]

  return df.iloc[index]["amount"]

def predictWeekdayBaselineValues(df: pd.DataFrame, predictionTimepoints: pd.Series) -> pd.DataFrame:
  """
    Predicts the available parking spaces for a series of timepoints with the amount from a week afar.

    df: DataFrame with training data
    prediction: Series with only timestamps in it

    Returns:
      DataFrame with the prediction timepoints as index and the predicted amounts in the 'amount' column.
  """
  returnvalue = pd.DataFrame(index=predictionTimepoints)
  for each in predictionTimepoints:
    res = weekdayBaselineModel(df, each)
    returnvalue.loc[each, 'amount'] = res
  return returnvalue

def baselineModelEvaluation(trainDf: pd.DataFrame, testDf: pd.DataFrame):
  """
    Tests the baseline model and prints out results. Model looks at 15 minutes prior to estimate.
    Args:
      trainDf: df to train with, at least it has to have column 'amount' and timepoint as index.
      testDf: df to test with, at least it has to have column 'amount' and timepoint as index.
  """
  print("________________")
  print("BASELINE MODEL")
  print("________________")
  predictedValues = predictBaselineValues(trainDf, testDf.index.to_series())
  #<- gives me a df with index Timepoints and amount column

  # Test only those where we have values:
  evaluationDf = pd.concat(
    [
        testDf["amount"].rename("actual"),
        predictedValues["amount"].rename("prediction")
    ],
    axis=1
  ).dropna()

  mae = mean_absolute_error(
    evaluationDf["actual"],
    evaluationDf["prediction"]
  )
  # for parkingId 1: ca. 90 lots

  rmse = root_mean_squared_error(
    evaluationDf["actual"],
    evaluationDf["prediction"]
  )
  # for parkingId 1: 122 lots, rmse > mae, meaning: there are some bigger errors.

  print("Shape")
  print(evaluationDf.shape)
  # 3326 × 15 min ≈ 34,9 days. Hole test set is from 28.07. to 02.09., so about 35 days. :check:
  print(f"Mae: {mae}")
  print(f"Rmse: {rmse}")

def weeklyBaselineModelEvaluation(trainDf: pd.DataFrame, testDf: pd.DataFrame):
  """
    Tests the weekly baseline model and prints out results. Model looks at the same time a week ago.
    Args:
      trainDf: df to train with, at least it has to have column 'amount' and timepoint as index.
      testDf: df to test with, at least it has to have column 'amount' and timepoint as index.
  """
  print("________________")
  print("WEEKLY BASELINE MODEL")
  print("________________")
  predictedValues = predictWeekdayBaselineValues(trainDf, testDf.index.to_series())
  #<- gives me a df with index Timepoints and amount column

  # Test only those where we have values:
  evaluationDf = pd.concat(
    [
        testDf["amount"].rename("actual"),
        predictedValues["amount"].rename("prediction")
    ],
    axis=1
  ).dropna()

  mae = mean_absolute_error(
    evaluationDf["actual"],
    evaluationDf["prediction"]
  )


  rmse = root_mean_squared_error(
    evaluationDf["actual"],
    evaluationDf["prediction"]
  )
  # weekly is in rmse and mae slightly better than baseline

  print("Shape")
  print(evaluationDf.shape)
  # 3326 × 15 min ≈ 34,9 days. Hole test set is from 28.07. to 02.09., so about 35 days. :check:
  print(f"Mae: {mae}")
  print(f"Rmse: {rmse}")

def arimaModelEvaluation(trainDf: pd.DataFrame, testDf: pd.DataFrame):
  print("________________")
  print("ARIMA MODEL")
  print("________________")


  print("NaN training:", trainDf["amount"].isna().sum())
  print("NaN test:", testDf["amount"].isna().sum())

  validTrain = trainDf.dropna(subset=["amount"]).copy()
  validTrain = validTrain.reset_index()
  validTrain["diff"] = validTrain["timepoint"].diff()

  print(
      validTrain.loc[
          validTrain["diff"] > pd.Timedelta("15min"),
          ["timepoint", "diff"]
      ]
  )
  # in my experimentation data i have holes:
  #server-1  |                timepoint            diff
  #server-1  | 1832 2026-03-29 03:00:00 0 days 01:15:00
  #server-1  | 3384 2026-04-14 07:45:00 0 days 01:00:00
  #server-1  | 4631 2026-04-27 09:00:00 0 days 01:45:00
  #server-1  | 4635 2026-04-27 11:00:00 0 days 01:15:00
  #server-1  | 4770 2026-04-28 23:00:00 0 days 02:30:00

  #<- those are a problem for arima, so i only use data from 29.04.26 onwards.
  trainDf = trainDf.loc[trainDf.index >= pd.Timestamp("2026-04-29")]
  #<- this works, because i first changed timepoint to_datetime and then made an index out of it
  #so it is a datetimeindex! (yes this exists...)

  print("NaN training:", trainDf["amount"].isna().sum())
  print(
      "Train:",
      trainDf.min(),
      "->",
      trainDf.max()
  )

  print("Where are those")
  tmp = trainDf.reset_index()
  print(tmp.loc[tmp["amount"].isna(), ["timepoint", "amount"]])

  print("I'm going off the rails on a \033[90mcrazy\033[0m valid train")
  validTrain = trainDf.reset_index().dropna(subset=["amount"]).copy()
  validTrain["diff"] = validTrain["timepoint"].diff()

  print(
      validTrain.loc[
          validTrain["diff"] > pd.Timedelta("15min"),
          ["timepoint", "diff"]
      ]
  )

  trainSeries = TimeSeries.from_dataframe(
      trainDf.reset_index(),
      time_col="timepoint",
      value_cols="amount"
  )

  testSeries = TimeSeries.from_dataframe(
      testDf.reset_index(),
      time_col="timepoint",
      value_cols="amount"
  )

  model = ARIMA(p=1, d=1, q=1)
  model.fit(trainSeries)
  prediction = model.predict(n=1)
  print("predict...")
  print(prediction)

  #Beware of the 10 minute waiting game:
  #Now: Rolling / One step ahead forecast
  print("Rolling forecast incoming... (might need a few minutes) or like 10")
  fullSeries = trainSeries.concatenate(testSeries)
  forecast = model.historical_forecasts(
    series=fullSeries,
    start=testSeries.start_time(), #prediction starts at timepoint of testdata
    forecast_horizon=1, # only one step in the future for the moment = 15m
    stride=1, # only one step at each time.
    retrain=False, #dont retrain on every step. it is pre trained it is not needed.
    last_points_only=True # get only last point, because of forecast_horizon 1 it is the case anyway
  )

  print(forecast)

  forecastDf = forecast.to_dataframe()
  print(forecastDf.head(10))

  evaluationDf = pd.concat(
      [
          testDf["amount"].rename("actual"),
          forecastDf["amount"].rename("prediction")
      ],
      axis=1
  )

  print(evaluationDf.head(10))
  print(evaluationDf.shape)

  evaluationDf=evaluationDf.dropna()

  mae = mean_absolute_error(
    evaluationDf["actual"],
    evaluationDf["prediction"]
  )


  rmse = root_mean_squared_error(
    evaluationDf["actual"],
    evaluationDf["prediction"]
  )

  #Mae: 3.452384824555465
  #Rmse: 5.570498681417147
  #<- an incredible lot better than baselinemodels!

  print("Shape")
  print(evaluationDf.shape)
  # 3326 × 15 min ≈ 34,9 days. Hole test set is from 28.07. to 02.09., so about 35 days. :check:
  print(f"Mae: {mae}")
  print(f"Rmse: {rmse}")

def prophetModelEvaluation(trainDf: pd.DataFrame, testDfProphet: pd.DataFrame):
  prophetDf = pd.concat([
    trainDf.reset_index()[["timepoint", "amount"]],
    testDfProphet.reset_index()[["timepoint", "amount"]]
  ]).rename(
      columns={
          "timepoint": "ds",
          "amount": "y"
      }
  ).dropna()


  model = Prophet()
  # This looks like data leakage but isnt, because i use cutoffs
  model.fit(prophetDf)

  cutoffs = [
      timestamp - pd.Timedelta(minutes=15)
      for timestamp in testDfProphet.index
      if pd.notna(testDfProphet.loc[timestamp, "amount"])
  ]

  #beware, following needs half an hour!
  print("Rolling forecast incoming, needs about half an hour with a week of data")
  forecast = cross_validation(
      model,
      horizon="15 minutes",
      cutoffs=cutoffs,
      #parallel="processes" # i cannot just make it paralell as is,
      # i would have to fit my app.py to it (time is tight)
  )

  forecast = forecast.loc[
      forecast["ds"] == forecast["cutoff"] + pd.Timedelta(minutes=15)
  ].copy()

  mae = mean_absolute_error(
      forecast["y"],
      forecast["yhat"]
  )

  rmse = root_mean_squared_error(
      forecast["y"],
      forecast["yhat"]
  )

  print(f"mae: {mae}, rmse: {rmse}")
  #  mae: 43.966595656221706, rmse: 58.81863581832422
  # dissapointing

def rnnModelEvaluation(trainDf: pd.DataFrame, testDf: pd.DataFrame):

  print("________________")
  print("RNN MODEL")
  print("________________")

  trainSeries = TimeSeries.from_dataframe(
      trainDf.reset_index(),
      time_col="timepoint",
      value_cols="amount"
  )

  testSeries = TimeSeries.from_dataframe(
      testDf.reset_index(),
      time_col="timepoint",
      value_cols="amount"
  )

  model = RNNModel(
      model="LSTM",
      input_chunk_length=96,
      output_chunk_length=1,
      training_length=96,
      n_rnn_layers=1,
      hidden_dim=25,
      n_epochs=10,
      random_state=42
  )

  scaler = Scaler()
  trainSeriesScaled = scaler.fit_transform(trainSeries)

  model.fit(trainSeriesScaled)

  print("Rolling forecast incoming...")

  fullSeriesScaled = scaler.transform(
      trainSeries.concatenate(testSeries)
  )

  forecast = model.historical_forecasts(
      series=fullSeriesScaled,
      start=testSeries.start_time(),
      forecast_horizon=1,
      stride=1,
      retrain=False,
      last_points_only=True
  )

  forecast = scaler.inverse_transform(forecast)
  forecastDf = forecast.to_dataframe()

  evaluationDf = pd.concat(
      [
          testDf["amount"].rename("actual"),
          forecastDf["amount"].rename("prediction")
      ],
      axis=1
  ).dropna()

  mae = mean_absolute_error(
      evaluationDf["actual"],
      evaluationDf["prediction"]
  )

  rmse = root_mean_squared_error(
      evaluationDf["actual"],
      evaluationDf["prediction"]
  )

  print("MAE:", mae)
  print("RMSE:", rmse)
  # Without scaling:
  #MAE: 496.3480563820411
  #RMSE: 509.1358656406034
  # With scaling:
  # MAE 4.92, RMSE:  7.80


  print(forecastDf.head(20))
  print(forecastDf.describe())
  print("Actual mean:", evaluationDf["actual"].mean())
  print("Prediction mean:", evaluationDf["prediction"].mean())
  print("Actual min/max:", evaluationDf["actual"].min(), evaluationDf["actual"].max())
  print("Prediction min/max:", evaluationDf["prediction"].min(), evaluationDf["prediction"].max())
  #<- that block told me, that the nn calculated the same value for each forecast without scaling.


def addTimeFeatures(df: pd.DataFrame) -> pd.DataFrame:
  """
    Adds sin and cos of time and weekday. Both features are represented cyclical for better
    learing abilities for the model

    Args:
      df: input dataframe, contains the data that exist until now. At least timepoint as index.
      Position is assumed Münster for now.

    Returns:
      dataframe with all features that came in from args and additionally features time_sin,
      time_cos, weekday_sin and weekday_cos.
  """
  minutes = (
  #  df["timepoint"].dt.hour * 60
  #  + df["timepoint"].dt.minute
    df.index.hour * 60
    + df.index.minute
  )

  df["time_sin"] = np.sin(
      2 * np.pi * minutes / (24 * 60)
  )

  df["time_cos"] = np.cos(
      2 * np.pi * minutes / (24 * 60)
  )

  df["weekday_sin"] = np.sin(
    2 * np.pi * df.index.dayofweek / 7
  )

  df["weekday_cos"] = np.cos(
      2 * np.pi * df.index.dayofweek / 7
  )
  return df

def getWeatherData(
  start: pd.Timestamp,
  end: pd.Timestamp,
  latitude: float = 51.961563, # default lat, long of münster.
  longitude: float = 7.628202
) -> pd.DataFrame:
  """
    Gets weather data for a given time period and location.

    Depending on the requested time period, the appropriate weather
    data source is selected:
      - Open-Meteo Forecast API for current and future data
      - Open-Meteo Historical Forecast API for historical forecast data
      - Meteostat for historical periods not covered by the
        Open-Meteo Historical Forecast API (planned)

    If the requested period spans from the past into the future,
    data from the appropriate historical and forecast sources is
    combined.

    Args:
        start: Start of the requested time period.
        end: End of the requested time period.
        latitude: Latitude of the requested location.
        longitude: Longitude of the requested location.

    Returns:
        DataFrame with 'temperature' and 'precipitation' as columns
        and the requested timestamps as index.

    Raises:
        ValueError: If end is earlier than start.
        requests.HTTPError: If a weather API request fails.
  """
  if(start > end):
    raise ValueError("Endtime is prior starttime.")

  def _getForecast(st: pd.Timestamp, en: pd.Timestamp) ->pd.DataFrame:
    """
      Gets data from Open Meteo Weather Forecast API, also current and past values, but cuts it
      to the needed timeperiod, defined by st and en.

      Args:
        st: start time it calls the API for,
        en: end time it calls the API for
      Returns:
        df with columns 'temperature' and 'precipitation' and timepoint as index.
    """
    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "minutely_15": "temperature_2m,precipitation",
        "start_minutely_15": start.strftime("%Y-%m-%dT%H:%M"),
        "end_minutely_15": end.strftime("%Y-%m-%dT%H:%M"),
        #"past_minutely_15": 5,
        #"current": [("temperature_2m",), ("precipitation",)],
        "timezone": "Europe/Berlin"
    }

    response = requests.get(url, params=params)
    print(response.url)
    print(response.text)
    response.raise_for_status()

    data = response.json()

    weatherDf = pd.DataFrame({
        "temperature": data["minutely_15"]["temperature_2m"],
        "precipitation": data["minutely_15"]["precipitation"]
    }, index=pd.to_datetime(data["minutely_15"]["time"]))

    weatherDf.index.name = "timepoint"
    # cut data to timeframe needed:
    weatherDf = weatherDf.loc[st:en]
    return weatherDf

  def _getHistorical(st: pd.Timestamp, en: pd.Timestamp) ->pd.DataFrame:
    """
      Gets historical forecast data from the Open-Meteo Historical Forecast API.

      Args:
          st: start time
          en: end time

      Returns:
          DataFrame with columns 'temperature' and 'precipitation'
          and timepoint as index.
    """

    url = "https://historical-forecast-api.open-meteo.com/v1/forecast"

    params = {
      "latitude": latitude,
      "longitude": longitude,
      "minutely_15": "temperature_2m,precipitation",
      "start_minutely_15": st.strftime("%Y-%m-%dT%H:%M"),
      "end_minutely_15": en.strftime("%Y-%m-%dT%H:%M"),
      "timezone": "Europe/Berlin"
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    data = response.json()

    weatherDf = pd.DataFrame({
      "temperature": data["minutely_15"]["temperature_2m"],
      "precipitation": data["minutely_15"]["precipitation"]
    }, index=pd.to_datetime(data["minutely_15"]["time"]))

    weatherDf.index.name = "timepoint"
    return weatherDf

  # case 1: start is now, and end in future
  # case 2: start is already in the future and end too
  # -> case 1 and 2 are one case, both doable with open meteo forecast
  # case 3: start is in past, end in the future or now
  # -> a) if past is more than an hour i need historical api otherwise b) forecast api with past_minutely_15 = 5 is just fine
  # case 4: start is in the past, end too, but before
  # -> historical api
  # case 5: some time is earlier than some specific to-be-found-out point in 2022 then i need meteostat

  now = pd.Timestamp.now(tz="Europe/Berlin").tz_localize(None)
  oneHourAgo = (now - pd.Timedelta(hours=1)).floor("15min")
  if start >= now:
    # case 1 and 2.
    #print("Case 1 or 2, _getForecast")
    weatherDf = _getForecast(st=start, en=end)
  elif end <= now:
    # case 4:
    # start and end are both in the past
    #print("Case 4, _getHistorical")
    weatherDf = _getHistorical(st=start, en=end)
  else:
    # case 3:
    if start < oneHourAgo:
      # case 3 a).
      #print("Case 3 a, _getForecast and _getHistorical")
      historicalEnd = oneHourAgo
      forecastStart = oneHourAgo + pd.Timedelta(minutes=15)
      pastDf = _getHistorical(st=start, en=historicalEnd)
      futureDf = _getForecast(st=forecastStart, en=end)
      weatherDf = pd.concat([pastDf, futureDf])
    else:
      # case 3 b:
      #print("Case 3 b, _getForecast")
      weatherDf = _getForecast(st=start, en=end)

  #Info: case 5 is postponed for now as it looks that open meteo historical
  #forecast api has all the data needed


  return weatherDf

def addWeatherFeatures(df: pd.DataFrame) -> pd.DataFrame:
  """
    Adds weather data to the df.

    Args:
      df: input dataframe, contains the data that exist until now. At least timepoint as index.
      position is assumed Münster for now.
    Returns:
      dataframe with all columns from df and additional columns temperature and precipitation.
  """
  if df.empty:
    return df.copy() # as it would be a problem if df is empty for iloc.
  df = df.sort_index()
  start = df.index[0]
  end = df.index[-1]
  weatherDf = getWeatherData(start, end)
  returnDf = pd.concat([df, weatherDf], axis=1)
  return returnDf

def enrichData(df: pd.DataFrame) -> pd.DataFrame:
  df = addTimeFeatures(df)
  df = addWeatherFeatures(df)
  return df

def printWeatherTest(name, start, end):
  print(f"\n{'=' * 50}")
  print(name)
  print(f"Requested: {start} -> {end}")
  print("NOW:", pd.Timestamp.now())
  try:
    df = getWeatherData(
      start=start,
      end=end
    )

    print(f"Returned:  {df.index.min()} -> {df.index.max()}")
    print(f"Rows:      {len(df)}")
    print(f"Columns:   {list(df.columns)}")
    print()
    print(df.head())
    print("...")
    print(df.tail())

  except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")


def testWeatherCases():
  now = pd.Timestamp.now(tz="Europe/Berlin").tz_localize(None).floor("15min")
  # 1. Future -> Future
  printWeatherTest(
    "TEST 1: Future",
    now + pd.Timedelta(minutes=30),
    now + pd.Timedelta(hours=2)
  )
  # 2. Past -> Past
  printWeatherTest(
    "TEST 2: Historical",
    now - pd.Timedelta(days=2),
    now - pd.Timedelta(days=2) + pd.Timedelta(hours=2)
  )
  # 3. Past -> Future, more than one hour in the past
  printWeatherTest(
    "TEST 3: Past -> Future",
    now - pd.Timedelta(hours=2),
    now + pd.Timedelta(hours=2)
  )
  # 4. Past -> Future, but past is less than one hour ago
  printWeatherTest(
    "TEST 4: Recent Past -> Future",
    now - pd.Timedelta(minutes=30),
    now + pd.Timedelta(hours=2)
  )
  printWeatherTest(
    "TEST 5: rainy day",
    pd.Timestamp("2026-09-13 13:00"),
    pd.Timestamp("2026-09-13 18:00")
  )
  printWeatherTest(
    "TEST 6: Start of Dataset",
    pd.Timestamp("2019-01-01"),
    pd.Timestamp("2019-01-01 02:00")
  )

#-----------------------------------
# Call everything!
#-----------------------------------

#__________________
#Reset Database and gett all Data
#__________________
#worked = resetDatabaseAndImportAllData()
#message = "Import worked fine" if worked else "Import had a problem"
#print(message)

# It takes a long time to get all the data:
#lotsDf = getLots(getEngine())
#print("got lots")
#so i built this guy:
#__________________
#Get Data from Parkinspace 1
#__________________
lotsDf = getLotsOfParkinspaceNo(getEngine(), 1)
print("got lots from 1")

#__________________
#Analyze data visually
#__________________
#analyzeDataOfLots(lotsDf)

#__________________
#Analyse structure of data
#__________________
#print("Status value count")
#print(lotsDf["status"].value_counts())

#print("0-values separately")
#print(lotsDf[ lotsDf["amount"] == 0 ]["status"].value_counts())

#print("whats with amount - describe")
#print(lotsDf["amount"].describe())

#print("how regular is my data")
#print(lotsDf["timepoint"].sort_values().diff().value_counts())

#__________________
#Look at specific data
#__________________
#current = lotsDf[
#    (lotsDf["timepoint"] >= "2026-03-10") &
#    (lotsDf["status"] != "ges")
#].copy()

#current = current.sort_values("timepoint")

#print(current.head())
#print(current.tail())

#print("Amount:", len(current))
#print("From:", current["timepoint"].min())
#print("To:", current["timepoint"].max())

#print("\nStatus:")
#print(current["status"].value_counts())

#print("\ndistances:")
#print(current["timepoint"].diff().value_counts().head(20))

#__________________
#Change type of timepoint to datetime (comming from database it wasnt yet)
#__________________
#Timepoint is datetime
lotsDf["timepoint"] = pd.to_datetime(lotsDf["timepoint"])

#__________________
#Defined time period for Experiment 0
#__________________
# 0st experiment: #2026-03-10 ─────────────────────────────────── 2026-09-02
timeseriesDf = lotsDf.loc[(lotsDf['timepoint'] >= "2026-03-10") & (lotsDf['timepoint'] <= "2026-09-02")]

#__________________
#Defined time period for Experiment 1
#__________________
#1st experiment: Data of the year 2026
#timeseriesDf = lotsDf.loc[lotsDf['timepoint'] >= "2026-01-01"].copy()

#__________________
#Clean Data / Create proper timeseries data:
#__________________
# 1. remove ges, as it will not be par of our training.
timeseriesDf = timeseriesDf.loc[timeseriesDf['status'] != 'ges']

# (2. everything with status 'bes' = 0 is already the case)

# 3. 15 minute grid. If there is an hole in the data it will not wrongfully filled with resample!
timeseriesDf = (
  timeseriesDf
  .set_index("timepoint")
  .resample("15min")
  .last()
  .sort_index()
)

#__________________
#Analyse how many NaN are created by our resampling
#__________________
#timeseriesDf = timeseriesDf.reset_index()
#print(timeseriesDf.head(20))
#print("amount of NaN")
#print(timeseriesDf.isna().sum())

#print("NaN in amount")
#print(timeseriesDf[timeseriesDf["amount"].isna()])

#__________________
# investigate gaps in data:
#__________________
#testDf = timeseriesDf.dropna(subset=["amount"]).sort_index()

#diffs = testDf.index.to_series().diff()

#print("\nLücken:")
#print(
#    pd.DataFrame({
#        "timepoint": testDf.index,
#        "diff": diffs
#    })
#    .query("diff > '0 days 00:15:00'")
#)
#interpolate
#this point in time, the one 15 before is missing, so 14:15 is missing
#2026-07-09 01:45:00 2026-07-09 01:45:00 0 days 00:30:00

#__________________
# 2026-07-09 01:30 - interpolate missing value:
#__________________
timeseriesDf.loc[
    "2026-07-09 01:30:00", "amount"
] = (
    timeseriesDf.loc["2026-07-09 01:15:00", "amount"]
    + timeseriesDf.loc["2026-07-09 01:45:00", "amount"]
) / 2

#__________________
#Test split
#__________________


timeseriesDf = enrichData(timeseriesDf)
print("timeseries with timestuff and weatherstuff")
print(timeseriesDf)

splitIndex = int(len(timeseriesDf) * 0.8)
trainDf = timeseriesDf.iloc[:splitIndex].copy()
testDf = timeseriesDf.iloc[splitIndex:].copy()

print("Train:", trainDf.index.min(), "->", trainDf.index.max())
print("Test:", testDf.index.min(), "->", testDf.index.max())

#-----------------------------------
# Predict Baseline and see MAE and RMSE
#-----------------------------------
baselineModelEvaluation(trainDf, testDf)

#-----------------------------------
# Predict Weekly Baseline and see MAE and RMSE
#-----------------------------------
weeklyBaselineModelEvaluation(trainDf, testDf)

#-----------------------------------
# Arima Model
#-----------------------------------
#Commented out because it needs about 10 minutes and i am not working with arima for now
#arimaModelEvaluation(trainDf, testDf)

#-----------------------------------
# Prophet Model
#-----------------------------------
#Commented out because it needs half an hour with a week of data and results are not promising
#so i will not use this

# I will not use my whole testset. Because of rolling forecast each forecast needs about
# 2 seconds. Which results in 1,5 hours of running without paralellisation

#testEnd = testDf.index.min() + pd.Timedelta(weeks=1)
#testDfProphet = testDf.loc[testDf.index < testEnd].copy()

#prophetModelEvaluation(trainDf, testDfProphet)

#-----------------------------------
# RNN Model
#-----------------------------------
#Remind you, this is only the evaluation!
#rnnModelEvaluation(trainDf, testDf)

#-----------------------------------
# Test getWeatherData
#-----------------------------------
#testWeatherCases()



print("Ended")
# following needed for development with docker compose watch:
import time
time.sleep(500000)