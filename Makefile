.PHONY: up smoke down

up:
	docker compose up --build -d --wait

smoke:
	docker compose exec -T frontend node --input-type=module - < scripts/smoke.mjs

down:
	docker compose down
