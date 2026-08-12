# Notes F0026

## Format

```yaml
version: 1
name: mon_projet
db_path: data/main.duckdb
pipeline_path: pipelines
read_only: false
```

## API

- GET /gui/project
- POST /gui/project/save
- POST /gui/project/open

## CLI

renatus-gui mon.renatus.yaml
renatus-gui --project mon.renatus.yaml
