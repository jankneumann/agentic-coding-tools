# security-review Dependencies

`/security-review` can use both native and containerized scanners.

## Quick Start

Print recommended install commands:

```bash
skills/security-review/scripts/install_deps.sh --components java,podman,dependency-check
```

Execute install commands (where supported):

```bash
skills/security-review/scripts/install_deps.sh --apply --components java,podman,dependency-check
```

## Required by Capability

- Dependency-Check native mode: `java`, `dependency-check`
- Dependency-Check fallback mode: `podman` (or Docker-compatible runtime)
- ZAP scans: `podman` (or Docker-compatible runtime)

## macOS (Homebrew + Podman Desktop)

```bash
brew install openjdk@17
brew install podman
brew install --cask podman-desktop
brew install dependency-check
podman machine init --now
# Enable Docker CLI compatibility in Podman Desktop settings if needed
```

## Ubuntu / Debian

```bash
sudo apt-get update
sudo apt-get install -y openjdk-17-jre podman podman-docker
# dependency-check: prefer container fallback or manual release install
```

## Fedora / RHEL (dnf)

```bash
sudo dnf install -y java-17-openjdk podman podman-docker
# dependency-check: prefer container fallback or manual release install
```

## Verify

```bash
skills/security-review/scripts/check_prereqs.sh --json
```

If dependency-check is missing but container runtime access is available, `/security-review` will use container fallback for dependency scanning.
