.PHONY: test db-up db-down

test:
	pytest -q

db-up:
	docker compose up -d

db-down:
	docker compose down
