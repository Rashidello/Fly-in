PYTHON ?= python3
MAIN ?= main.py
MAP ?= maps/easy/01_linear_path.txt

MYPY_FLAGS = --warn-return-any --warn-unused-ignores \
	--ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

install:
	uv pip install -r requirements.txt

run:
	$(PYTHON) $(MAIN) $(MAP)

medium:
	$(PYTHON) $(MAIN) maps/medium/01_dead_end_trap.txt

hard:
	$(PYTHON) $(MAIN) maps/hard/01_maze_nightmare.txt

debug:
	$(PYTHON) -m pdb $(MAIN) $(MAP)

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .mypy_cache .pytest_cache

lint:
	flake8 .
	mypy . $(MYPY_FLAGS)

lint-strict:
	flake8 .
	mypy . --strict

.PHONY: lint install hard run clean debug medium lint-strict VE