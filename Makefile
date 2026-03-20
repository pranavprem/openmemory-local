SHELL := /bin/bash
.DEFAULT_GOAL := help

-include .env
export

.PHONY: help
help: ## Show available commands
	@echo "Memory Service — Makefile targets"
	@echo "================================="
	@echo ""
	@echo "  Mac mini (run locally):"
	@grep -E '^(export|switch|cleanup|verify-nas|up|down|status|help):' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "    \033[36mmake %-14s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  NAS (run on the NAS):"
	@grep -E '^(setup|logs):' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "    \033[36mmake %-14s\033[0m %s\n", $$1, $$2}'

# ── Mac mini targets ──────────────────────

.PHONY: export
export: ## Export local Qdrant + SCP snapshot to NAS
	@bash scripts/export.sh

.PHONY: switch
switch: ## Switch Mac to use NAS Qdrant (no cleanup)
	@bash scripts/switch.sh

.PHONY: cleanup
cleanup: ## Remove local Qdrant (run after NAS is confirmed working)
	@bash scripts/cleanup.sh

.PHONY: verify-nas
verify-nas: ## Verify NAS Qdrant from Mac
	@curl -s --connect-timeout 3 http://$(NAS_IP):$(QDRANT_PORT)/collections/memories | \
		python3 -c "import sys,json; d=json.load(sys.stdin); print(f'✅ NAS Qdrant: {d[\"result\"][\"points_count\"]} memories')" \
		2>/dev/null || echo "❌ Can't reach NAS Qdrant at $(NAS_IP):$(QDRANT_PORT)"

.PHONY: up
up: ## Start local Qdrant
ifeq ($(MEMORY_MODE),openmemory)
	docker compose --profile openmemory up -d
else
	docker compose up -d qdrant
endif

.PHONY: down
down: ## Stop local services
	docker compose down

.PHONY: status
status: ## Show running services
	@docker compose ps

# ── NAS targets ───────────────────────────

.PHONY: setup
setup: ## Deploy Qdrant + import snapshot (run ON the NAS)
	@bash scripts/nas-setup.sh

.PHONY: logs
logs: ## Tail Qdrant logs
	@docker compose logs -f --tail=50 qdrant
