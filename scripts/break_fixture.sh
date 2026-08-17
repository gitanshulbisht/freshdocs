#!/usr/bin/env bash
# Break the fixture site: rename the classes/headings the scraper depends on.
# Run this, deploy the changes to GitHub Pages, and the fixture collector's
# next run will return rows with empty body_text — the heal demo trigger.
set -euo pipefail
cd "$(dirname "$0")/fixture-site"

for f in *.html; do
  sed -i '' \
    -e 's/class="content"/class="content-v2"/g' \
    -e 's/class="title"/class="page-heading"/g' \
    -e 's/class="body-text"/class="article-body"/g' \
    -e 's/class="section-heading"/class="subhead"/g' \
    -e 's/class="code-block"/class="code-v2"/g' \
    -e 's/<h1/<h2/g' -e 's#</h1>#</h2>#g' \
    "$f"
done
echo "fixture site broken: classes renamed, h1 -> h2"
