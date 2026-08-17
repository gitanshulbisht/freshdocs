#!/usr/bin/env bash
# Create all Bright Data collectors for FreshDocs.
#
# Run one at a time; generation takes 5-15 minutes each. After each create,
# copy the returned c_* Collector ID into collectors/collectors.json and
# CLAUDE.md (never into git secrets).
#
#   bash scripts/setup_collectors.sh docker     # create just one
#   bash scripts/setup_collectors.sh            # print all create commands

set -euo pipefail
cd "$(dirname "$0")/.."

require_bdata() {
  if ! command -v bdata >/dev/null 2>&1; then
    echo "bdata not installed — run: npx -p @brightdata/cli bdata login" >&2
    exit 1
  fi
}

create() {
  local key="$1" url="$2" prompt="$3"
  echo "=== creating collector for $key ==="
  echo "bdata scraper create '$url' '$prompt'"
  echo
}

DOCKER_URL="https://docs.docker.com/sitemap.xml"
K8S_URL="https://kubernetes.io/en/sitemap.xml"
EKS_URL="https://docs.aws.amazon.com/eks/latest/userguide/sitemap.xml"
ARGO_URL="https://argo-workflows.readthedocs.io/en/release-4.1/sitemap.xml"
LANGCHAIN_URL="https://docs.langchain.com/sitemap.xml"

COMMON="Visit every documentation page listed in the sitemap and extract: page title, canonical URL, main body text (the article content, cleaned of navigation/footer/scripts), and last-updated date if the page shows one. Return one row per page."

if [[ -n "${1:-}" ]]; then
  case "$1" in
    docker) create docker "$DOCKER_URL" "Build a Sitemap scraper using this sitemap: $DOCKER_URL. $COMMON" ;;
    kubernetes) create kubernetes "$K8S_URL" "Build a Sitemap scraper using this sitemap: $K8S_URL. $COMMON" ;;
    aws-eks) create aws-eks "$EKS_URL" "Build a Sitemap scraper using this sitemap: $EKS_URL. $COMMON" ;;
    argo) create argo-workflows "$ARGO_URL" "Build a Sitemap scraper using this sitemap: $ARGO_URL. $COMMON" ;;
    langchain) create langchain "$LANGCHAIN_URL" "Build a Sitemap scraper using this sitemap: $LANGCHAIN_URL. $COMMON" ;;
    *) echo "unknown source: $1 (docker|kubernetes|aws-eks|argo|langchain)" >&2; exit 2 ;;
  esac
else
  create docker "$DOCKER_URL" "Build a Sitemap scraper using this sitemap: $DOCKER_URL. $COMMON"
  create kubernetes "$K8S_URL" "Build a Sitemap scraper using this sitemap: $K8S_URL. $COMMON"
  create aws-eks "$EKS_URL" "Build a Sitemap scraper using this sitemap: $EKS_URL. $COMMON"
  create argo-workflows "$ARGO_URL" "Build a Sitemap scraper using this sitemap: $ARGO_URL. $COMMON"
  create langchain "$LANGCHAIN_URL" "Build a Sitemap scraper using this sitemap: $LANGCHAIN_URL. $COMMON"
fi
