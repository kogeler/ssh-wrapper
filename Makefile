# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

SHELL := bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help
.NOTPARALLEL:

PY ?= python3
SUPPORTED_PYTHONS := 3.13 3.14
BIN := bin

DEVELOPMENT_LOCK := requirements-dev.txt
TEST_LOCK := requirements-test.txt
PACKAGE_LOCK := requirements-package.txt
DOCS_LOCK := requirements-docs.txt
LOCKS := $(DEVELOPMENT_LOCK) $(TEST_LOCK) $(PACKAGE_LOCK) $(DOCS_LOCK)
COMPILE := --quiet --strip-extras --allow-unsafe --generate-hashes
LOCK_UPGRADE ?=

VENV_DEV := .venv-dev
VENV_DOCS := .venv-docs
VENV_LOCK := .venv-lock
VENV_PACKAGE := .venv-package
VENV_TEST := .venv-test
PYTHON_DEV := $(VENV_DEV)/$(BIN)/python
PYTHON_DOCS := $(VENV_DOCS)/$(BIN)/python
PYTHON_LOCK := $(VENV_LOCK)/$(BIN)/python
PYTHON_PACKAGE := $(VENV_PACKAGE)/$(BIN)/python
PYTHON_TEST := $(VENV_TEST)/$(BIN)/python
DEPS_DEV_STAMP := $(VENV_DEV)/.deps-installed
DEPS_DOCS_STAMP := $(VENV_DOCS)/.deps-installed
DEPS_LOCK_STAMP := $(VENV_LOCK)/.deps-installed
DEPS_PACKAGE_STAMP := $(VENV_PACKAGE)/.deps-installed
DEPS_TEST_STAMP := $(VENV_TEST)/.deps-installed

ARTIFACTS := .artifacts
DEPENDENCY_SNAPSHOT := $(ARTIFACTS)/dependency-snapshot.json
RELEASE_NOTES := $(ARTIFACTS)/release-notes.md
SOURCE_DATE_EPOCH ?= $(shell git log -1 --format=%ct 2>/dev/null || printf '315532800')
COVERAGE_MIN ?= 80
RUFF_OUTPUT_FORMAT ?=
RUFF_OUTPUT := $(if $(RUFF_OUTPUT_FORMAT),--output-format=$(RUFF_OUTPUT_FORMAT))
PYTHON_SOURCES := ssh_wrapper tests tests_acceptance tools .github/scripts
ACTIONLINT_IMAGE := docker.io/rhysd/actionlint@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667
CONTAINER ?= $(shell command -v podman 2>/dev/null || command -v docker 2>/dev/null)

.PHONY: help check-python check-lock-python venv-dev venv-test venv-package venv-docs venv-lock \
	lock refresh-dependencies freeze-check lock-platform-check \
	dependency-validate dependency-snapshot audit audit-raw outdated \
	format format-check lint typecheck bandit syntax test test-full test-network-block \
	version-check release-notes build checksums package confinement-test \
	smoke-wheel smoke-sdist smoke reproducibility docs-build docs-audit docs-serve \
	validate-actions test-acceptance quality policy check ci clean

help: ## list supported development targets
	@grep -hE '^[a-zA-Z][a-zA-Z0-9_-]*:.*##' $(MAKEFILE_LIST) | \
		awk -F':.*## ' '{printf "  %-24s %s\n", $$1, $$2}'

check-python:
	@command -v $(PY) >/dev/null 2>&1 || { \
		printf 'required command not found: %s\n' '$(PY)' >&2; exit 1; \
	}
	@$(PY) -c 'import sys; sys.exit("CPython 3.13 or 3.14 is required") if sys.implementation.name != "cpython" or sys.version_info[:2] not in {(3, 13), (3, 14)} else None'

check-lock-python: check-python
	@$(PY) -c 'import sys; sys.exit("CPython 3.14 is required to generate locks") if sys.version_info[:2] != (3, 14) else None'

$(DEPS_DEV_STAMP): $(DEVELOPMENT_LOCK) | check-python
	@if [[ -e "$(VENV_DEV)" ]]; then find "$(VENV_DEV)" -depth -delete; fi
	@$(PY) -m venv "$(VENV_DEV)"
	@$(PYTHON_DEV) -m pip install --quiet --require-hashes --only-binary=:all: \
		--requirement $(DEVELOPMENT_LOCK)
	@$(PYTHON_DEV) -m pip check
	@cp -- $(DEVELOPMENT_LOCK) "$(DEPS_DEV_STAMP)"

venv-dev: $(DEPS_DEV_STAMP) ## install the hash-verified quality audience

$(DEPS_TEST_STAMP): $(TEST_LOCK) | check-python
	@if [[ -e "$(VENV_TEST)" ]]; then find "$(VENV_TEST)" -depth -delete; fi
	@$(PY) -m venv "$(VENV_TEST)"
	@$(PYTHON_TEST) -m pip install --quiet --require-hashes --only-binary=:all: \
		--requirement $(TEST_LOCK)
	@$(PYTHON_TEST) -m pip check
	@cp -- $(TEST_LOCK) "$(DEPS_TEST_STAMP)"

venv-test: $(DEPS_TEST_STAMP) ## install the hash-verified test audience

$(DEPS_PACKAGE_STAMP): $(PACKAGE_LOCK) | check-python
	@if [[ -e "$(VENV_PACKAGE)" ]]; then find "$(VENV_PACKAGE)" -depth -delete; fi
	@$(PY) -m venv "$(VENV_PACKAGE)"
	@$(PYTHON_PACKAGE) -m pip install --quiet --require-hashes --only-binary=:all: \
		--requirement $(PACKAGE_LOCK)
	@$(PYTHON_PACKAGE) -m pip check
	@cp -- $(PACKAGE_LOCK) "$(DEPS_PACKAGE_STAMP)"

venv-package: $(DEPS_PACKAGE_STAMP) ## install the hash-verified packaging audience

$(DEPS_DOCS_STAMP): $(DOCS_LOCK) | check-python
	@if [[ -e "$(VENV_DOCS)" ]]; then find "$(VENV_DOCS)" -depth -delete; fi
	@$(PY) -m venv "$(VENV_DOCS)"
	@$(PYTHON_DOCS) -m pip install --quiet --require-hashes --only-binary=:all: \
		--requirement $(DOCS_LOCK)
	@$(PYTHON_DOCS) -m pip check
	@cp -- $(DOCS_LOCK) "$(DEPS_DOCS_STAMP)"

venv-docs: $(DEPS_DOCS_STAMP) ## install the hash-verified documentation audience

$(DEPS_LOCK_STAMP): Makefile pyproject.toml tools/dependency_policy.py $(LOCKS) | check-lock-python
	@if [[ -e "$(VENV_LOCK)" ]]; then find "$(VENV_LOCK)" -depth -delete; fi
	@$(PY) -m venv "$(VENV_LOCK)"
	@mapfile -t bootstrap < <($(PY) tools/dependency_policy.py bootstrap); \
		test "$${#bootstrap[@]}" -gt 0; \
		$(PYTHON_LOCK) -m pip install --quiet --no-deps --only-binary=:all: \
			"$${bootstrap[@]}"
	@$(PYTHON_LOCK) -m pip check
	@cp -- Makefile "$(DEPS_LOCK_STAMP)"

venv-lock: $(DEPS_LOCK_STAMP) ## create the isolated exact resolver environment

lock: venv-lock ## regenerate all four hash locks without upgrading direct pins
	@CUSTOM_COMPILE_COMMAND='make lock' $(PYTHON_LOCK) -m piptools compile \
		$(COMPILE) $(LOCK_UPGRADE) --extra=dev --output-file=$(DEVELOPMENT_LOCK) pyproject.toml
	@CUSTOM_COMPILE_COMMAND='make lock' $(PYTHON_LOCK) -m piptools compile \
		$(COMPILE) $(LOCK_UPGRADE) --extra=test --output-file=$(TEST_LOCK) pyproject.toml
	@CUSTOM_COMPILE_COMMAND='make lock' $(PYTHON_LOCK) -m piptools compile \
		$(COMPILE) $(LOCK_UPGRADE) --extra=package --output-file=$(PACKAGE_LOCK) pyproject.toml
	@CUSTOM_COMPILE_COMMAND='make lock' $(PYTHON_LOCK) -m piptools compile \
		$(COMPILE) $(LOCK_UPGRADE) --extra=docs --output-file=$(DOCS_LOCK) pyproject.toml

refresh-dependencies: ## upgrade transitive graphs after reviewed direct-pin changes
	@$(MAKE) lock LOCK_UPGRADE=--upgrade

freeze-check: venv-lock ## reject semantic pin or hash drift in every lock
	@temporary="$$(mktemp -d)"; trap 'find "$$temporary" -depth -delete' EXIT; \
		CUSTOM_COMPILE_COMMAND='make lock' $(PYTHON_LOCK) -m piptools compile \
			$(COMPILE) --extra=dev --output-file="$$temporary/$(DEVELOPMENT_LOCK)" pyproject.toml; \
		CUSTOM_COMPILE_COMMAND='make lock' $(PYTHON_LOCK) -m piptools compile \
			$(COMPILE) --extra=test --output-file="$$temporary/$(TEST_LOCK)" pyproject.toml; \
		CUSTOM_COMPILE_COMMAND='make lock' $(PYTHON_LOCK) -m piptools compile \
			$(COMPILE) --extra=package --output-file="$$temporary/$(PACKAGE_LOCK)" pyproject.toml; \
		CUSTOM_COMPILE_COMMAND='make lock' $(PYTHON_LOCK) -m piptools compile \
			$(COMPILE) --extra=docs --output-file="$$temporary/$(DOCS_LOCK)" pyproject.toml; \
		$(PY) tools/dependency_policy.py compare --candidate-root "$$temporary"

lock-platform-check: venv-lock ## prove all locks resolve from supported Linux wheels
	@for python_version in $(SUPPORTED_PYTHONS); do \
		abi="cp$${python_version/./}"; \
		for platform in manylinux2014_x86_64 manylinux2014_aarch64; do \
			for lock in $(LOCKS); do \
				$(PYTHON_LOCK) -m pip install --quiet --dry-run --ignore-installed \
					--require-hashes --only-binary=:all: --platform "$$platform" \
					--implementation cp --python-version "$$python_version" --abi "$$abi" \
					--requirement "$$lock"; \
			done; \
		done; \
	done

dependency-validate: ## validate direct owners, pins, and all generated locks
	@$(PY) tools/dependency_policy.py validate

dependency-snapshot: ## build all GitHub dependency manifests offline
	@mkdir -p "$(ARTIFACTS)"
	@$(PY) .github/scripts/dependency_snapshot.py --output "$(DEPENDENCY_SNAPSHOT)"

audit: venv-dev ## require findings to equal the exact reviewed exception set
	@$(PYTHON_DEV) tools/dependency_audit.py

audit-raw: venv-dev ## print strict raw findings for locks and resolver bootstrap
	@temporary="$$(mktemp)"; trap 'unlink "$$temporary"' EXIT; \
		$(PY) tools/dependency_policy.py bootstrap > "$$temporary"; \
		$(PYTHON_DEV) -m pip_audit --strict --disable-pip --require-hashes \
			$(foreach lock,$(LOCKS),--requirement $(lock)); \
		$(PYTHON_DEV) -m pip_audit --strict --disable-pip --no-deps \
			--requirement "$$temporary"

outdated: venv-dev ## show available quality-tool updates
	@$(PYTHON_DEV) -m pip list --outdated

format: venv-dev ## apply Ruff fixes and formatting
	@$(VENV_DEV)/$(BIN)/ruff check --fix $(PYTHON_SOURCES)
	@$(VENV_DEV)/$(BIN)/ruff format $(PYTHON_SOURCES)

format-check: venv-dev ## check formatting without changing files
	@$(VENV_DEV)/$(BIN)/ruff format --check $(PYTHON_SOURCES)

lint: venv-dev ## run Ruff lint checks
	@$(VENV_DEV)/$(BIN)/ruff check $(RUFF_OUTPUT) $(PYTHON_SOURCES)

typecheck: venv-dev ## run strict mypy over the runtime package
	@$(VENV_DEV)/$(BIN)/mypy

bandit: venv-dev ## scan runtime sources for common security defects
	@$(PYTHON_DEV) -m bandit -q -c pyproject.toml -r ssh_wrapper

syntax: venv-dev ## compile every maintained Python source
	@$(PYTHON_DEV) -m compileall -q $(PYTHON_SOURCES)

test: venv-test ## run the network-guarded test suite
	@$(PYTHON_TEST) tools/run_tests.py -q tests

test-full: venv-test ## run tests with branch coverage and the blocking floor
	@mkdir -p "$(ARTIFACTS)"
	@$(PYTHON_TEST) tools/run_tests.py tests --cov=ssh_wrapper \
		--cov-report=term-missing --cov-report=xml:$(ARTIFACTS)/coverage.xml \
		--cov-fail-under=$(COVERAGE_MIN)
	@$(PYTHON_TEST) -m coverage report --format=markdown > $(ARTIFACTS)/coverage-report.md

test-network-block: venv-test ## prove the unit-test network guard is active
	@$(PYTHON_TEST) tools/run_tests.py --probe

version-check: ## verify dynamic version ownership and changelog agreement
	@$(PY) tools/version.py check $(VERSION_ARGS)

release-notes: ## generate the exact current-version GitHub release body
	@mkdir -p "$(ARTIFACTS)"
	@$(PY) tools/version.py notes --repository kogeler/ssh-wrapper \
		--output "$(RELEASE_NOTES)"

build: venv-package ## build one deterministic wheel and normalized sdist
	@$(PY) tools/build_distributions.py --python $(PYTHON_PACKAGE) \
		--output dist --epoch "$(SOURCE_DATE_EPOCH)"

checksums: ## write the exact release SHA-256 inventory
	@$(PY) tools/checksums.py --directory dist

confinement-test: ## verify complete wheel and sdist contents
	@$(PY) tools/verify_distribution.py dist --epoch "$(SOURCE_DATE_EPOCH)"

package: build confinement-test checksums ## build and verify release distributions

smoke-wheel: venv-package venv-dev ## clean-install and type-check the built wheel
	@$(PY) tools/smoke_distribution.py --kind wheel --dist-dir dist \
		--python $(PY) --mypy $(VENV_DEV)/$(BIN)/mypy

smoke-sdist: venv-package venv-dev ## offline-build, clean-install, and type-check the sdist
	@$(PY) tools/smoke_distribution.py --kind sdist --dist-dir dist \
		--python $(PY) --build-python $(PYTHON_PACKAGE) \
		--mypy $(VENV_DEV)/$(BIN)/mypy

smoke: package smoke-wheel smoke-sdist ## exercise both release distributions

reproducibility: venv-package ## compare equivalent clean-tree builds byte-for-byte
	@$(PY) tools/verify_reproducible.py --python $(PYTHON_PACKAGE) \
		--epoch "$(SOURCE_DATE_EPOCH)"

docs-build: venv-docs ## build the documentation site with strict checks
	@$(VENV_DOCS)/$(BIN)/mkdocs build --strict

docs-audit: docs-build ## audit generated routes, links, anchors, and canonical URLs
	@$(PY) tools/audit_docs_site.py --site-dir site \
		--site-url https://kogeler.github.io/ssh-wrapper/

docs-serve: venv-docs ## serve documentation locally with live reload
	@$(VENV_DOCS)/$(BIN)/mkdocs serve

validate-actions: ## lint workflows in an immutable networkless container
	@test -n "$(CONTAINER)" || { printf '%s\n' 'Podman or Docker is required' >&2; exit 1; }
	@$(CONTAINER) run --rm --network=none --read-only --cap-drop=all \
		--security-opt=no-new-privileges --volume "$(CURDIR):/repo:ro,z" \
		--workdir /repo $(ACTIONLINT_IMAGE) -config-file .github/actionlint.yaml

test-acceptance: venv-test ## run hermetic real-OpenSSH acceptance on Linux
	@$(PYTHON_TEST) -m pytest -q -m acceptance tests_acceptance

quality: format-check lint typecheck bandit syntax version-check dependency-validate ## run static source and ownership gates

policy: freeze-check lock-platform-check dependency-snapshot validate-actions ## run lock, snapshot, and workflow policy gates

check: quality test test-network-block ## run source-quality and unit-test gates

ci: quality test-full test-network-block policy docs-audit audit smoke reproducibility ## run each complete Linux gate exactly once

clean: ## remove only project-owned generated state
	@for path in .venv "$(VENV_DEV)" "$(VENV_TEST)" "$(VENV_PACKAGE)" \
		"$(VENV_DOCS)" "$(VENV_LOCK)" .pytest_cache .ruff_cache .mypy_cache \
		.artifacts build dist site coverage.xml .coverage htmlcov ssh_wrapper.egg-info; do \
		if [[ -d "$$path" ]]; then find "$$path" -depth -delete; \
		elif [[ -e "$$path" ]]; then unlink "$$path"; fi; \
	done
	@find ssh_wrapper tests tests_acceptance tools .github/scripts docs/site -type f \
		-path '*/__pycache__/*' -delete 2>/dev/null || true
	@find ssh_wrapper tests tests_acceptance tools .github/scripts docs/site -depth -type d \
		-name __pycache__ -empty -delete 2>/dev/null || true
