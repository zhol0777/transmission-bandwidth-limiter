venv:
	python3 -m venv venv

source:
	source venv/bin/activate

requirements:
	pip install peewee transmission-rpc python-dotenv

lint: ruff pylint mypy

ruff:
	python3 -m ruff check *.py --config tests/ruff.toml

pylint:
	python3 -m pylint *.py

mypy:
	python3 -m mypy *.py --config-file tests/mypy.ini