.PHONY: build preview etl data clean kill

build: data/last_updated.json
	yarn build

data/last_updated.json:
	@echo "{\"date\": \"$$(gh api /repos/:owner/:repo/commits?per_page=1 --jq '.[0].commit.committer.date' 2>/dev/null || git log -1 --format=%cI)\"}" > $@

preview: kill
	rm -rf docs/.observable
	yarn preview

kill:
	-pkill -f "notebooks preview" 2>/dev/null || true

etl: data/pipelines.geojson data/wells.geojson data/spills.json data/flares.parquet data/s2/scenes.json data/s1/scenes.json
	uv run --with rasterio,numpy,pillow,scipy scripts/composites.py

data/pipelines.geojson:
	uv run scripts/fetch_pipelines.py

data/wells.geojson:
	uv run scripts/fetch_wells.py

data/spills.json:
	./scripts/fetch_spills.sh

data/flares.parquet:
	duckdb < scripts/fetch_archive.sql

data/s2/scenes.json:
	uv run --with rasterio,numpy,requests scripts/s2.py

data/s1/scenes.json:
	uv run --with rasterio,numpy,requests scripts/s1.py

data: data/data.duckdb

data/data.duckdb: scripts/load.sql data/spills.json data/pipelines.geojson data/wells.geojson data/seeps.geojson data/events.csv data/flares.parquet
	rm -f $@ && duckdb < scripts/load.sql

clean:
	rm -rf docs/.observable/dist data/data.duckdb
