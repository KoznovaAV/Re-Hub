.PHONY: up smoke smoke-recovery down qa

up:
	docker compose up --build -d --wait

smoke:
	docker compose exec -T frontend node --input-type=module - < scripts/smoke.mjs

qa:
	docker compose exec -T parser-service python - < scripts/qa/run_qa.py

smoke-recovery:
	docker compose stop parser-service
	@status=0; \
		docker compose exec -T -e SMOKE_PYTHON_DOWN=1 frontend node --input-type=module - < scripts/smoke.mjs || status=$$?; \
		docker compose up -d --wait parser-service || exit $$?; \
		exit $$status
	$(MAKE) smoke

down:
	docker compose down
