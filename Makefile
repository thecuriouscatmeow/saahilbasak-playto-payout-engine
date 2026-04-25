.PHONY: up down seed test stress reconcile logs fmt

up:
	docker compose up -d --build

down:
	docker compose down -v

seed:
	docker compose exec web python manage.py seed

test:
	docker compose exec web pytest

stress:
	docker compose exec web python manage.py stress_concurrency --merchants 3 --workers 10 --duration 5

reconcile:
	docker compose exec web python manage.py reconcile

logs:
	docker compose logs -f web worker beat

fmt:
	docker compose exec web ruff format .
