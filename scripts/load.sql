INSTALL spatial; LOAD spatial; SET geometry_always_xy = true;
ATTACH 'data/data.duckdb' AS db (STORAGE_VERSION 'v1.0.0'); USE db;

CREATE OR REPLACE TABLE spills AS SELECT *, round(ST_Distance_Sphere(ST_Point(lon, lat), ST_Point(6.8888, 4.5763)) / 1000, 2) AS km FROM read_json_auto('data/spills.json');
CREATE OR REPLACE TABLE pipelines AS
SELECT name, fluid, status, round(ST_Distance(ST_Transform(geom, 'EPSG:4326', 'EPSG:32632', true),
       ST_Transform(ST_Point(6.8888, 4.5763), 'EPSG:4326', 'EPSG:32632', true)) / 1000, 2) AS km
FROM ST_Read('data/pipelines.geojson');
CREATE OR REPLACE TABLE locations AS SELECT * FROM ST_Read('data/locations.geojson');
CREATE OR REPLACE TABLE seeps AS SELECT name, first, ST_X(geom) AS lon, ST_Y(geom) AS lat FROM ST_Read('data/seeps.geojson');
CREATE OR REPLACE TABLE events AS SELECT * FROM read_csv('data/events.csv');
CREATE OR REPLACE TABLE flares AS SELECT *, round(ST_Distance_Sphere(ST_Point(lon, lat), ST_Point(6.8888, 4.5763)) / 1000, 2) AS km FROM 'data/flares.parquet';
CREATE OR REPLACE TABLE detections AS SELECT * FROM 'data/detections.parquet';
CREATE OR REPLACE TABLE infra AS SELECT * EXCLUDE (geom), ST_GeomFromWKB(geom) AS geom, round(ST_Distance_Sphere(ST_Point(lon, lat), ST_Point(6.8888, 4.5763)) / 1000, 2) AS km FROM 'data/infra.parquet';
CREATE OR REPLACE TABLE plumes AS SELECT *, round(ST_Distance_Sphere(ST_Point(lon, lat), ST_Point(6.8888, 4.5763)) / 1000, 2) AS km FROM 'data/plumes.parquet';

CREATE OR REPLACE TABLE wells AS
SELECT well_name AS name, well_status AS status, well_result AS result, well_type AS type,
       (SELECT CASE WHEN d > DATE '2030-01-01' THEN d - INTERVAL 100 YEAR ELSE d END
        FROM (SELECT try_strptime(split_part(completion_date, ' ', 1), '%-m/%-d/%y')::DATE AS d))::DATE AS completed,
       total_depth::DOUBLE AS depth_m, optr_name AS operator, accumulation_accumulation_name AS field,
       current_lc_area_phase_nm AS licence, ST_Y(geom) AS lat, ST_X(geom) AS lon,
       round(ST_Distance_Sphere(geom, ST_Point(6.8888, 4.5763)) / 1000, 2) AS km
FROM ST_Read('data/wells.geojson');

CREATE OR REPLACE TABLE flaring_monthly AS
SELECT f.id AS site, f.km, f.detail, date_trunc('month', d.date) AS month,
       count(*) AS nights, round(sum(d.rh_mw), 1) AS rh_mw
FROM detections d JOIN flares f ON f.id = d.site_id
GROUP BY ALL ORDER BY km, month;
