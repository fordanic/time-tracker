UV ?= uv
APP_NAME := time-tracker

.DEFAULT_GOAL := help

.PHONY: help sync run stop-agent format format-check lint typecheck test \
	test-unit test-integration test-e2e check ci build clean clear-local

help:
	@printf '%s\n' \
		'Time Tracker development targets:' \
		'' \
		'  make sync              Sync the locked development environment' \
		'  make run               Run the Textual app' \
		'  make stop-agent        Stop the background agent' \
		'  make format            Format Python sources' \
		'  make check             Run formatting, lint, types, and tests' \
		'  make ci                Sync and run the complete CI check set' \
		'  make build             Build a native executable in dist/' \
		'  make clean             Remove repository build and check artifacts' \
		'  make clear-local CONFIRM=1' \
		'                         Stop the agent and delete local app data'

sync:
	$(UV) sync --all-groups --locked

run: sync
	$(UV) run $(APP_NAME)

stop-agent:
	$(UV) run $(APP_NAME) --stop-agent

format:
	$(UV) run ruff format .

format-check:
	$(UV) run ruff format --check .

lint:
	$(UV) run ruff check .

typecheck:
	$(UV) run mypy

test:
	$(UV) run pytest

test-unit:
	$(UV) run pytest tests/unit

test-integration:
	$(UV) run pytest tests/integration

test-e2e:
	$(UV) run pytest tests/e2e

check: format-check lint typecheck test

ci: sync check

build: sync
	$(UV) run pyinstaller --noconfirm --clean --onefile \
		--name $(APP_NAME) --paths src --specpath build \
		--collect-data time_tracker.infrastructure.migrations \
		src/time_tracker/cli.py

clean:
	rm -rf build dist .mypy_cache .pytest_cache .ruff_cache \
		src/time_tracker.egg-info

clear-local:
	$(UV) run python -m time_tracker.infrastructure.local_files \
		$(if $(filter 1,$(CONFIRM)),--yes,)
