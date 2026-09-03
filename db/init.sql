-- Fill here your database initialisation:

-- Per example:
-- ----------------------------------
-- Drop the database if it already exists
-- DROP DATABASE IF EXISTS case_study_gans ;
-- Create the database
-- CREATE DATABASE example;
-- Use the database
-- USE case_study_gans;
-- Create the 'cities' table
-- CREATE TABLE cities (
--    id INT AUTO_INCREMENT, -- Automatically generated ID for each city
--    city VARCHAR(255) NOT NULL, -- Name of the city
--    country VARCHAR(255),
--    longitude DECIMAL(9,6), -- yes ai was helping me to decide
--    latitude DECIMAL(9,6), -- yes ai was helping me to decide
--    PRIMARY KEY (id) 
-- );


CREATE DATABASE oscilot;
-- Use the database
USE oscilot;
-- Create the table
CREATE TABLE parkingspaces (
    id INT, 
    #<- autoincrement is not a good idea here. It will make the preparation of data unneccessarily 
    #much more complicated
    name VARCHAR(255) DEFAULT '',
    columnName VARCHAR(255),
    longitude DECIMAL(9,6) DEFAULT NULL,
    latitude DECIMAL(9,6) DEFAULT NULL,
    PRIMARY KEY(id)
);

CREATE TABLE lots (
	parkingId INT, 
    timepoint DATETIME, 
    amount INT,
    status VARCHAR(255), #i could use a default here but i dont then i can see if there are problems
    PRIMARY KEY (timepoint, parkingId),
    FOREIGN KEY (parkingId) REFERENCES parkingspaces(id)
 );


