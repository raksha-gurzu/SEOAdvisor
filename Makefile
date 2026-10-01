.PHONY: dev test

dev:  ## start the backend and the web app; open http://localhost:4280
	@scripts/dev.sh

test:  ## unit tests
	@.venv/bin/python -m pytest -q
