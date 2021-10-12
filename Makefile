MAKE_HELP_LEFT_COLUMN_WIDTH:=14
.PHONY: help build
help: ## This help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-$(MAKE_HELP_LEFT_COLUMN_WIDTH)s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort

format: ## Format all the code using isort and black
	isort feast_postgres/
	black --target-version py38 feast_postgres

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
