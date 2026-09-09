# security-review Dependencies

`/security-review` can use both native and containerized scanners.

## Quick Start

Print recommended install commands:

```bash
"<skill-base-dir>/scripts/install_deps.sh" --components java,podman,dependency-check
```

Execute install commands (where supported):

```bash
"<skill-base-dir>/scripts/install_deps.sh" --apply --components java,podman,dependency-check
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
"<skill-base-dir>/scripts/check_prereqs.sh" --json
```

If dependency-check is missing but container runtime access is available, `/security-review` will use container fallback for dependency scanning.

## The NVD database (dependency-check)

dependency-check does not carry vulnerability data in its image. It matches your
dependencies against a local copy of the NVD corpus, and **scans run with
`--noupdate`**, so that copy has to be seeded separately.

### Why seeding is separate from scanning

Updating inline would make every security review depend on NVD being reachable
and on the rate limit at that moment — a transient network fault would surface
as a security result rather than as an outage. It would also turn a one-minute
scan into a multi-GB download. Seeded separately, a scan's verdict is a function
of the tree and the database, both of which hold still.

### One-time setup

1. Request a key (free, instant) at
   <https://nvd.nist.gov/developers/request-an-api-key>. NVD throttles
   unauthenticated bulk downloads hard enough that a first seed is not practical
   without one.
2. Put it in `agent-coordinator/.secrets.yaml` (gitignored) as `NVD_API_KEY`.
   `.secrets.yaml.example` documents the entry. `bao_seed.py` reads every
   string-valued key in that file, so `make bao-seed` also puts it in OpenBao
   with no code change.
3. Export it and seed:

   ```bash
   export NVD_API_KEY="$(python3 -c "import yaml;print(yaml.safe_load(open('agent-coordinator/.secrets.yaml'))['NVD_API_KEY'])")"
   make security-seed-nvd
   ```

   The first run downloads the full corpus and takes a while; later runs are
   incremental.

The key is read from the environment, never from a command-line argument, so it
does not land in the process table or in shell history. Only the seeding run
carries it — scans never receive it.

### Where the database lives

`$DEPENDENCY_CHECK_DATA_DIR`, defaulting to `~/.cache/dependency-check/data`.
Outside the repo on purpose: it is a multi-GB artifact with no business in a
working tree, and it should survive branch switches.

### Freshness

A CVE database is stale within days, and **a scan against stale data reports no
findings whether or not any exist** — indistinguishable from a genuinely clean
scan. So staleness is treated as NOT CHECKED rather than as a pass:

```bash
make security-nvd-status   # exit 0 fresh, 4 absent or stale
```

`DEPENDENCY_CHECK_MAX_DB_AGE_DAYS` (default 7) sets the floor;
`--max-db-age-days 0` disables it, which is an explicit "I know, scan anyway"
rather than something you can drift into. `--nvd-status` exits non-zero when
stale precisely so a scheduled job can gate a refresh on it.

### Is this worth running at all?

Partly overlapping with tooling you may already have. Dependabot and the
`dependency-audit-*` CI jobs read manifests and cover the declared Python and
JS ecosystems. dependency-check answers the same question from the *filesystem*
— it fingerprints vendored jars, bundled binaries and transitive artifacts that
manifest parsing never sees. If nothing in the tree is vendored or bundled, the
manifest scanners are most of the value and this is optional.

