INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;
CREATE SECRET dd (TYPE s3, PROVIDER config, KEY_ID '', SECRET '', REGION 'WAW3-2', ENDPOINT 's3.WAW3-2.cloudferro.com', URL_STYLE 'path');

COPY (
  SELECT id, lat, lon, detail, first_seen, last_seen, detections, active_days, observations, persistence
  FROM read_parquet('s3://data-desk-archive/eog/flares/data.parquet')
  WHERE lat BETWEEN 4.3 AND 4.9 AND lon BETWEEN 6.5 AND 7.3
) TO 'data/flares.parquet';

COPY (
  SELECT site_id, date, rh_mw, temp_k, satellite
  FROM read_parquet('s3://data-desk-archive/eog/detections/**/data.parquet')
  WHERE cell = '8182fffffffffff' AND lat BETWEEN 4.3 AND 4.9 AND lon BETWEEN 6.5 AND 7.3 AND date >= DATE '2018-01-01'
) TO 'data/detections.parquet';

COPY (
  SELECT provider, id, kind, name, operator, status, detail, lat, lon, ST_AsWKB(geometry) AS geom
  FROM read_parquet('s3://data-desk-archive/*/infrastructure/**/data.parquet', union_by_name = true)
  WHERE lat BETWEEN 4.35 AND 4.85 AND lon BETWEEN 6.6 AND 7.2
    AND kind NOT IN ('storage_tank', 'gasometer', 'licence', 'licence_area', 'licence_owner', 'lng_terminal', 'substation')
) TO 'data/infra.parquet';

COPY (
  SELECT provider, id, date, lat, lon, rate_kg_h, satellite
  FROM read_parquet(['s3://data-desk-archive/carbon-mapper/detections/**/data.parquet', 's3://data-desk-archive/imeo/detections/**/data.parquet',
                     's3://data-desk-archive/sron/detections/**/data.parquet', 's3://data-desk-archive/google/detections/**/data.parquet'], union_by_name = true)
  WHERE kind = 'plume' AND lat BETWEEN 4.0 AND 5.2 AND lon BETWEEN 6.2 AND 7.6
) TO 'data/plumes.parquet';
