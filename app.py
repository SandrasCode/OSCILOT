import pandas as pd # type: ignore
#students = pd.Series(['Al', 'Bo', 'Ce'], name = 'students')
#print("Lalala this one tries the CI pardy")
#print(students)
import requests
from io import StringIO
from sqlalchemy import Engine, create_engine

def initDatabase(resetDb: bool = False):
  """
    Initialize the database.

    Args:
      resetDb: Whether to reset the existing database content before
      initializing it. Default is do not reset.
  """
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
    successfulReseted = resetDatabaseContent()
    print(f"Database reset successful: {successfulReseted}")


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
      conn.execute(text("DELETE FROM parkingspaces"))
      conn.execute(text("DELETE FROM lots"))
  except SQLAlchemyError as e:
    print(f"Database reset failed: {e}")
    returnvalue = False
  return returnvalue


def getAllDataFromParkingDecks() -> pd.DataFrame:
  """
    Retrieves historical data from 2019 to the latest available date,
    which is typically about one day behind the current date.

    Returns:
      DataFrame with all informations.
  """
  api_url = "https://api.github.com/repos/codeformuenster/parking-decks-muenster/contents/data"
  # TODO: handle data inside folder data/2019-2023
  response = requests.get(api_url)
  response.raise_for_status()

  files = response.json()
  df = pd.DataFrame()
  for file in files:
    if file["name"].endswith(".csv"):
      csv_response = requests.get(file["download_url"])
      csv_response.raise_for_status()
      dfNew = pd.read_csv(StringIO(csv_response.text))
      #print(file["name"])
      #print(df.head())
      df = pd.concat([df, dfNew], ignore_index=True)
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

def prepareDataForDB(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Dataframe]:
  """
    Args:
      df: DataFrame of the format getAllDataFromParkingDecks returns
      (columns: 'Datum und Uhrzeit', 'PH Coesfelder Kreuz', 'PH Theater', 'PP Hörsterplatz',
      'PH Alter Steinweg', 'Busparkplatz', 'PP Schlossplatz Nord', 'PP Schlossplatz Süd',
      'PH Aegidii', 'PP Georgskommende', 'PH Münster Arkaden', 'PH Karstadt', 'PH Stubengasse',
      'PH Bremer Platz', 'PH Engelenschanze', 'PH Bahnhofstraße', 'PH Cineplex', 'PH Stadthaus 3',
      'PP Hafenmarkt', 'TG Hafenmarkt', 'Halle Münsterland P1')

    Returns:
      tuple of
      First DataFrame: df fitted to parkingspaces in database (min columnnames: "id", "columnName")
      Second DataFrame: df fitted to lots in database
        (min columnnames: "parkingId", "timepoint", "amount")
  """

  #1. ignore rows whose "Datum und Uhrzeit" isnt in a datetime format as there is sometimes
  # "Anzahl Parkplätze gesamt" contained

  #2. build df for parkingspaces

  #3. build df for lots
