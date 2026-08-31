# OSCILOT - Oscillation-based Forecasting of Occupancy in Parking Lots

The goal of this project is to predict future parking occupancy in Münster using historical parking data. The resulting web application will allow users to check how busy a specific parking facility is expected to be at a given time. As an optional additional feature, users can enter their destination and arrival time, and the system can recommend suitable parking facilities based on predicted availability, cost, and distance.

# Technologies:

Docker, Streamlit, Python, Git, Pandas, Darts, Matplotlib / Seaborn to analyze, FastAPI, NumPy, Scikit-learn, MySql

# Data sub fields:

Time series

# Data used:

https://github.com/codeformuenster/parking-decks-muenster/tree/master/data
respectively https://opendata.stadt-muenster.de/dataset/parkhausbelegungen-im-verlauf-2019-bis-heute/resource/76f1ddcd-54d1-4951-8b82-9bef3dad2fcc
Mabe https://github.com/klaasnicolaas/python-muenster
For optional part scrap parking costs from https://wbi-muenster.de/parken-in-muenster/uebersicht.php
For optional part geocoordinates from https://opendata.stadt-muenster.de/dataset/parkleitsystem-parkhausbelegung-aktuell
Ocelot lookin for parking spaces %D https://upload.wikimedia.org/wikipedia/commons/b/b5/081_Ocelot_in_Encontro_das_%C3%81guas_State_Park_Photo_by_Giles_Laurent.jpg?utm_source=commons.wikimedia.org&utm_campaign=index&utm_content=original

# How to use this:

To use this you have to create ./db/password.txt with a password in it. 
