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
  if(parkSucc & lotSucc):
    returnvalue = True
  return returnvalue


#-----------------------------------
# Call everything!
#-----------------------------------

worked = resetDatabaseAndImportAllData()
message = "Import worked fine" if worked else "Import had a problem"
print(message)
lotsDf = getLots(getEngine())
print("got lots")
sns.lineplot(data=lotsDf, x="timepoint", y="amount", hue="parkingId", palette="tab20")
print("saving graph")
plt.savefig("/app/output/graph.png")
plt.close()
print("saved")