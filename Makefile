.PHONY: up smoke smoke-recovery down

up:
	docker compose up --build -d --wait

smoke:
	docker compose exec -T frontend node --input-type=module - < scripts/smoke.mjs

smoke-recovery:
	docker compose stop ai-service
	@status=0; \
		docker compose exec -T -e SMOKE_PYTHON_DOWN=1 frontend node --input-type=module - < scripts/smoke.mjs || status=$$?; \
		docker compose up -d --wait ai-service || exit $$?; \
		exit $$status
	$(MAKE) smoke

down:
	docker compose down
