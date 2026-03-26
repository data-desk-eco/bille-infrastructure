.PHONY: build preview etl data clean kill

build:
	@echo "{\"date\": \"$$(gh api /repos/:owner/:repo/commits?per_page=1 --jq '.[0].commit.committer.date' 2>/dev/null || git log -1 --format=%cI)\"}" > data/last_updated.json
	yarn build

preview:
	yarn preview

etl: data/pipelines.geojson data/spills.json

data/pipelines.geojson:
	uv run scripts/fetch_pipelines.py

data/spills.json:
	./scripts/fetch_spills.sh

data: data/spills.json data/data.duckdb

data/data.duckdb: data/spills.json data/pipelines.geojson data/locations.geojson
	duckdb $@ < scripts/load.sql

clean:
	rm -rf docs/.observable/dist data/data.duckdb

kill:
	-pkill -f "notebooks preview" 2>/dev/null || true
