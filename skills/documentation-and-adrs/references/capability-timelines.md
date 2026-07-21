# Capability timeline convention

A project may keep architectural decisions as reverse-chronological capability
timelines under the consumer-project-relative `docs/decisions/` directory.
Each entry records a status (`active` or `superseded`) and links to the
session-log phase that established or reversed the decision.

Representative capability names include:

- `agent-coordinator`
- `configuration`
- `merge-pull-requests`
- `skill-workflow`
- `software-factory-tooling`

Read existing files in the consumer project before choosing the next entry
number. If no timeline fits, create a kebab-case capability file. Generate the
index from `architectural: <capability>` tags using the project's documented
source-contribution command; never assume the installed skill ships the
consumer's decision history or Makefile.
