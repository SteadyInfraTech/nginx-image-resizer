#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || -z "$1" ]]; then
  echo "usage: $0 <branch-or-version-ref>" >&2
  exit 2
fi

published_ref=$1
if [[ "$published_ref" == v* ]]; then
  image_tag="${published_ref#v}"
  # docker/metadata-action's {{version}} tag excludes SemVer build metadata.
  image_tag="${image_tag%%+*}"
  if [[ -z "$image_tag" ]]; then
    echo "version ref produced an empty image tag: $published_ref" >&2
    exit 1
  fi
  printf '%s\n' "$image_tag"
else
  printf '%s\n' main
fi
