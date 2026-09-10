#!/usr/bin/env bash
# Resolve a pinned scanner image reference. Sourced, not executed.
#
# Usage:
#   source "$(dirname "${BASH_SOURCE[0]}")/scanner_images.sh"
#   image="$(scanner_image ZAP)"
#
# Returns "<tag>@<digest>" so the pull is reproducible while the log still shows
# which tag the digest came from. An explicit <NAME>_IMAGE override wins, so an
# operator testing an upstream fix does not have to edit the pin file.

_scanner_images_env() {
  printf '%s\n' "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scanner-images.env"
}

scanner_image() {
  local name="$1"
  local override_var="${name}_IMAGE"
  local override="${!override_var:-}"
  if [[ -n "$override" ]]; then
    printf '%s\n' "$override"
    return 0
  fi

  local env_file
  env_file="$(_scanner_images_env)"
  if [[ ! -f "$env_file" ]]; then
    echo "scanner-images.env not found at $env_file" >&2
    return 1
  fi
  # shellcheck disable=SC1090
  source "$env_file"

  local tag_var="${name}_IMAGE_TAG" digest_var="${name}_IMAGE_DIGEST"
  local tag="${!tag_var:-}" digest="${!digest_var:-}"
  if [[ -z "$tag" ]]; then
    echo "no pin for ${name} in $env_file" >&2
    return 1
  fi
  if [[ -z "$digest" ]]; then
    # An empty digest is a deliberate, visible escape hatch (a bump in progress),
    # not a silent fallback: say so rather than pulling a moving tag quietly.
    echo "WARNING: ${name} has no pinned digest; using the floating tag ${tag}" >&2
    printf '%s\n' "$tag"
    return 0
  fi
  printf '%s@%s\n' "${tag%%@*}" "$digest"
}
