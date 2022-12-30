# Developing libvirt-instance


## Prerequisites

- Make
- [Poetry](https://python-poetry.org/)


## Virtualenv

Run `make develop` to initialize the Poetry virtualenv with the development
dependencies for the project.


## Formatting the code automatically

Run `make reformat` will use Black and Isort to format the code.


## Testing

Run `make all-tests` to run all the tests.


## Building

Run `make build` to build a source distribution and a wheel in `dist/`.


## Releasing

1. Update the version in `pyproject.toml`.
2. Git tag.
