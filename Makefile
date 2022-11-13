.PHONY: reformat lint test typecheck build

reformat:
	poetry run black .
	poetry run isort .

lint:
	poetry run isort --check .
	poetry run black --check .
	poetry run flake8

test:
	poetry run coverage run -m pytest -vv
	poetry run coverage report

typecheck:
	poetry run mypy .

build:
	poetry build
