# SupplementPacket local commands (B1). Services run directly: Docker is not used here.
SHELL := /bin/bash
PY := .venv/bin/python
OWNER := $(shell whoami)
TEST_ENV := MIGRATION_DATABASE_URL=postgresql+psycopg://$(OWNER)@localhost:5432/supplementpacket_test
DEV_ENV := MIGRATION_DATABASE_URL=postgresql+psycopg://$(OWNER)@localhost:5432/supplementpacket_dev
CHECK_DIRS := apps packages scripts tests tools

.PHONY: venv env migrate seed dev stop test test-unit lint typecheck boundaries heads parity check

venv:
	/opt/homebrew/bin/python3.12 -m venv .venv
	.venv/bin/pip install -q -r tools/requirements.txt
	$(PY) tools/write_pth.py

env:
	@test -f .env || $(PY) tools/write_env.py

migrate: env
	psql -X -q -v ON_ERROR_STOP=1 -h localhost -d supplementpacket_dev -f scripts/db_bootstrap.sql
	$(DEV_ENV) .venv/bin/alembic -c packages/db/alembic.ini upgrade head

seed: migrate
	$(DEV_ENV) $(PY) scripts/seed_synthetic.py

dev: seed
	$(PY) scripts/dev.py

stop:
	$(PY) scripts/dev.py stop

test:
	scripts/reset_db.sh supplementpacket_test
	$(TEST_ENV) .venv/bin/pytest -c tools/pytest.ini --rootdir .

test-unit:
	.venv/bin/pytest -c tools/pytest.ini --rootdir . tests/unit

lint:
	.venv/bin/ruff check --config tools/ruff.toml $(CHECK_DIRS)
	.venv/bin/ruff format --config tools/ruff.toml --check $(CHECK_DIRS)

typecheck:
	.venv/bin/mypy --config-file tools/mypy.ini apps/api/src apps/worker/src packages/core/src packages/db/src packages/files/src packages/parsers/src packages/obs/src scripts tools

boundaries:
	$(PY) scripts/check_boundaries.py

heads:
	$(PY) scripts/check_migration_heads.py

parity:
	$(TEST_ENV) $(PY) scripts/orm_parity.py

check: lint typecheck boundaries heads test parity
