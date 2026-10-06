# GX-10 coordinator operator targets. Sequencing only: every step lives in a
# script or a systemd unit. Run on the GX-10 host as root:
#
#   sudo make -C /opt/agentic-coding-tools/deploy/gx10 <target>
#
# Never pulls. A pull that changes bind-mounted files without recreating the
# containers is a silent outage, so `git pull` stays an explicit operator step.
#
# The analyzer's runtime must be up: this project joins its networks, reads
# secrets rendered from its OpenBao, and exports traces to its Langfuse.

SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

ROOT ?= /opt/agentic-coding-tools
PROJECT ?= aca-gx10-coord
IMAGE ?= ghcr.io/jankneumann/agent-coordinator
IMAGES_ENV ?= /etc/aca/gx10-images.env
UNIT_DIR ?= /etc/systemd/system
STOP_TIMEOUT ?= 15
SINCE ?= 30 minutes ago
SHA := $(shell git -C $(ROOT) rev-parse --short HEAD 2>/dev/null)

HERE := $(ROOT)/deploy/gx10
UNITS := $(wildcard $(HERE)/systemd/*.service)
COORD_UNITS := aca-gx10-coordinator-secrets aca-gx10-coordinator

.PHONY: help require-root install ownership preflight image start stop status logs

help: ## List targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  %-16s %s\n", $$1, $$2}'

require-root:
	@[[ $$EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }

install: require-root ## Install the units, then reload systemd
	install -m 0644 $(UNITS) $(UNIT_DIR)/
	systemctl daemon-reload
	systemctl enable $(addsuffix .service,$(COORD_UNITS))

ownership: require-root ## Create data directories owned by their container users
	# 999:999 is the ParadeDB image user; 10001:10001 is the coordinator image's
	# appuser, pinned in the Dockerfile so this number is knowable at all.
	install -d -o 999 -g 999 -m 0700 /srv/aca/coordinator-postgres
	install -d -o 10001 -g 10001 -m 0700 /srv/aca/coordinator-workdir
	$(MAKE) preflight

preflight: require-root ## Fail closed unless every bind mount is owned correctly
	$(HERE)/check_persistence_ownership.sh

image: require-root ## Build coord-<sha> from the checked-out commit, push, print the pin line
	@[[ -z "$$(git -C $(ROOT) status --porcelain)" ]] || { echo "worktree is dirty; the image must match commit $(SHA)" >&2; exit 1; }
	cd $(ROOT) && podman build -f agent-coordinator/Dockerfile -t $(IMAGE):coord-$(SHA) .
	podman push $(IMAGE):coord-$(SHA)
	@digest="$$(skopeo inspect --format '{{.Digest}}' docker://$(IMAGE):coord-$(SHA))"; \
	  echo; echo "pin this in $(IMAGES_ENV), then restart:"; \
	  echo "GX10_COORD_IMAGE=$(IMAGE):coord-$(SHA)@$$digest"

start: require-root install ## Render secrets and start the coordinator
	systemctl restart aca-gx10-coordinator-secrets.service
	systemctl start aca-gx10-coordinator.service
	$(MAKE) status

stop: require-root ## Stop the coordinator; its ExecStop removes the containers
	systemctl stop aca-gx10-coordinator.service

status: ## Unit states and containers on one screen
	@for unit in $(COORD_UNITS); do printf '%-40s ' "$$unit"; systemctl show "$$unit.service" -p ActiveState,SubState,Result --value | paste -sd' '; done
	@podman ps -a --filter label=io.podman.compose.project=$(PROJECT) --format 'table {{.Names}}\t{{.Status}}'

logs: ## Failures across the coordinator units since $(SINCE)
	@journalctl --since "$(SINCE)" --no-pager -o short -u 'aca-gx10-coordinator*' \
	  | grep -iE 'fatal|error|denied|mismatch|did not become healthy|Failed|Traceback' \
	  | tail -40 || true
