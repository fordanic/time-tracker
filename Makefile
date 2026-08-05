UV ?= uv
UV_CACHE_DIR ?= $(CURDIR)/.uv-cache
UV_PYTHON_INSTALL_DIR ?= $(CURDIR)/.uv-python
PYINSTALLER_CONFIG_DIR ?= $(CURDIR)/.pyinstaller-cache
export UV_CACHE_DIR
export UV_PYTHON_INSTALL_DIR
export PYINSTALLER_CONFIG_DIR

APP_NAME := time-tracker
ifeq ($(OS),Windows_NT)
VENV_PYTHON := .venv/Scripts/python.exe
else
VENV_PYTHON := .venv/bin/python
endif

.DEFAULT_GOAL := help

.PHONY: help prepare-venv sync run stop-agent format format-check lint typecheck test \
	test-unit test-integration test-e2e check ci build smoke-packaged \
	smoke-notification set-version release-artifact clean clear-database clear-local

help:
	@printf '%s\n' \
		'Time Tracker development targets:' \
		'' \
		'  make help              Show this target list' \
		'  make prepare-venv      Remove an unusable generated virtual environment' \
		'  make sync              Sync the locked development environment' \
		'  make run               Run the Textual app' \
		'  make stop-agent        Stop the background agent' \
		'  make format            Format Python sources' \
		'  make format-check      Check Python source formatting' \
		'  make lint              Run Ruff lint checks' \
		'  make typecheck         Run mypy type checks' \
		'  make test              Run unit, integration, and end-to-end tests' \
		'  make test-unit         Run unit tests' \
		'  make test-integration  Run integration tests' \
		'  make test-e2e          Run end-to-end tests' \
		'  make check             Run formatting, lint, types, and tests' \
		'  make ci                Sync and run the complete CI check set' \
		'  make build             Build a native executable in dist/' \
		'  make smoke-packaged    Test the complete packaged timer lifecycle' \
		'  make smoke-notification Dispatch a native notification from the package' \
		'  make set-version VERSION=X.Y.Z[rcN]' \
		'                         Set the canonical version and refresh uv.lock' \
		'  make release-artifact  Check, build, smoke, archive, and checksum locally' \
		'  make clean             Remove repository build and check artifacts' \
		'  make clear-database CONFIRM=1' \
		'                         Stop the agent and delete the local database' \
		'  make clear-local CONFIRM=1' \
		'                         Stop the agent and delete local app data'

prepare-venv:
	@if [ -d ".venv" ]; then \
		if [ ! -x "$(VENV_PYTHON)" ] || \
			! "$(VENV_PYTHON)" -c 'import encodings' >/dev/null 2>&1; then \
			echo "Removing unusable .venv"; \
			rm -rf .venv; \
		fi; \
	fi

sync: prepare-venv
	$(UV) sync --all-groups --locked

run: sync
	$(UV) run $(APP_NAME)

stop-agent: prepare-venv
	$(UV) run $(APP_NAME) --stop-agent

format: prepare-venv
	$(UV) run ruff format .

format-check: prepare-venv
	$(UV) run ruff format --check .

lint: prepare-venv
	$(UV) run ruff check .

typecheck: prepare-venv
	$(UV) run mypy

test: test-unit test-integration test-e2e

test-unit: prepare-venv
	$(UV) run pytest tests/unit

test-integration: prepare-venv
	$(UV) run pytest tests/integration

test-e2e: prepare-venv
	$(UV) run pytest tests/e2e

check: format-check lint typecheck test

ci: sync check

build: sync
	$(UV) run python scripts/build.py

smoke-packaged: prepare-venv
	$(UV) run python scripts/run_packaged_smoke.py

smoke-notification: prepare-venv
	$(UV) run python scripts/run_notification_smoke.py

set-version: sync
	$(UV) run python scripts/release.py set-version "$(VERSION)"

release-artifact: sync check build smoke-packaged
	$(UV) run python scripts/release.py package

clean:
	rm -rf build dist .mypy_cache .pytest_cache .ruff_cache \
		src/time_tracker.egg-info

clear-database: prepare-venv
	$(UV) run python -m time_tracker.infrastructure.local_files \
		--database-only $(if $(filter 1,$(CONFIRM)),--yes,)

clear-local: prepare-venv
	$(UV) run python -m time_tracker.infrastructure.local_files \
		$(if $(filter 1,$(CONFIRM)),--yes,)
