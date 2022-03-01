MAKE_HELP_LEFT_COLUMN_WIDTH:=14
.PHONY: help build
help: ## This help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-$(MAKE_HELP_LEFT_COLUMN_WIDTH)s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort

format: ## Format all the code using isort and black
	isort feast_postgres/
	black --target-version py37 feast_postgres

lint: ## Run mypy, isort, flake8, and black
	mypy feast_postgres/
	isort feast_postgres/ --check-only
	flake8 feast_postgres/
	black --check feast_postgres

build: ## Build the wheel
	rm -rf dist/*
	python -m build

publish-testpypi: ## Publish to testpipy
	twine upload --repository testpypi dist/*

publish-pypi: ## Publish to pipy
	twine upload --repository pypi dist/*

start-test-db:
	docker-compose up &

stop-test-db:
	docker-compose down

clean_reinstall_pip_packages:
	pip freeze | sed -r 's/^-e.*egg=([^&]*).*/\1/' | xargs pip uninstall -y
	pip install -U pip wheel pip-tools
	cd feast && PYTHON=3.9 make install-python-ci-dependencies
	pip install -e .["dev"]

# Here we have to type out the whole command for the test rather than having
# `cd feast && FULL_REPO_CONFIGS_MODULE=tests.repo_config make test-python-universal`
# The reason is that feast runs the tests in parallel and doing so the update function
# is run in parallel where two threads will try to create the same schema at the same
# time.
#
# https://stackoverflow.com/a/29908840/957738
#   If the schema is being concurrently created in another session but isn't yet committed,
#   then it both exists and does not exist, depending on who you are and how you look.
#   It's not possible for other transactions to "see" the new schema in the system
#   catalogs because it's uncommitted, so it's entry in pg_namespace is not visible to
#   other transactions. So CREATE SCHEMA / CREATE TABLE tries to create it because, as
#   far as it's concerned, the object doesn't exist.
# 
# The test that persist the historical dataframe are skippted
test-python-universal:
	cd feast && FULL_REPO_CONFIGS_MODULE=postgres_tests.repo_config FEAST_USAGE=False IS_TEST=True python -m pytest --integration --universal -k "not test_historical_retrieval_fails_on_validation and not test_historical_retrieval_with_validation and not test_historical_features_persisting and not test_historical_retrieval_fails_on_validation and not test_universal_cli" sdk/python/tests
