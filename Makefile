.PHONY: test format lint

test:
	pytest -q

db-up:
	docker compose up -d

db-down:
	docker compose down
