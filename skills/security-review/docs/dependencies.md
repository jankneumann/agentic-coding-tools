# security-review Dependencies

`/security-review` can use both native and containerized scanners.

## Quick Start

Print recommended install commands:

```bash
skills/security-review/scripts/install_deps.sh --components java,docker,dependency-check
```

Execute install commands (where supported):

```bash
skills/security-review/scripts/install_deps.sh --apply --components java,docker,dependency-check
```

## Required by Capability

- Dependency-Check native mode: `java`, `dependency-check`
- Dependency-Check fallback mode: `docker` (no local binary needed)
- ZAP scans: `docker`

## macOS (Homebrew)

```bash
brew install openjdk@17
brew install dependency-check
brew install --cask docker
```

## Ubuntu / Debian

```bash
sudo apt-get update
sudo apt-get install -y openjdk-17-jre docker.io
# dependency-check: prefer Docker fallback or manual release install
```

## Fedora / RHEL (dnf)

```bash
sudo dnf install -y java-17-openjdk docker
# dependency-check: prefer Docker fallback or manual release install
```

## Verify

```bash
skills/security-review/scripts/check_prereqs.sh --json
```

If dependency-check is missing but Docker is available, `/security-review` will use Docker fallback for dependency scanning.
