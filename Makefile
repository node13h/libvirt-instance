.PHONY: clean develop reformat lint test typecheck all-tests build

clean:
	rm -rf dist/

develop:
	poetry install

reformat:
	poetry run black .
	poetry run isort .

lint:
	poetry run isort --check .
	poetry run black --check .
	poetry run flake8 --extend-ignore=E501

test:
	poetry run coverage run -m pytest -vv
	poetry run coverage report

typecheck:
	poetry run mypy .

all-tests: lint typecheck test

build:
	poetry build
