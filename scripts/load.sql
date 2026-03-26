INSTALL spatial; LOAD spatial;

CREATE OR REPLACE TABLE spills AS
SELECT * FROM read_json_auto('data/spills.json');

CREATE OR REPLACE TABLE pipelines AS
SELECT * FROM ST_Read('data/pipelines.geojson');

CREATE OR REPLACE TABLE locations AS
SELECT * FROM ST_Read('data/locations.geojson');
