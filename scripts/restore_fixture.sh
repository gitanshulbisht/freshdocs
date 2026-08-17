#!/usr/bin/env bash
# Restore the fixture site to its original (unbroken) state.
set -euo pipefail
cd "$(dirname "$0")/fixture-site"

for f in *.html; do
  sed -i '' \
    -e 's/class="content-v2"/class="content"/g' \
    -e 's/class="page-heading"/class="title"/g' \
    -e 's/class="article-body"/class="body-text"/g' \
    -e 's/class="subhead"/class="section-heading"/g' \
    -e 's/class="code-v2"/class="code-block"/g' \
    -e 's/<h2/<h1/g' -e 's#</h2>#</h1>#g' \
    "$f"
done
echo "fixture site restored"
