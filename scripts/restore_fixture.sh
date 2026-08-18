#!/usr/bin/env bash
# Restore the fixture site to its original (unbroken) state.
set -euo pipefail
cd "$(dirname "$0")/../demo/fixture-site"

for f in *.html; do
  sed -i '' \
    -e 's/<div class="content-v2">/<article>/g' \
    -e 's#</div>#</article>#g' \
    -e 's/<h3 class="page-heading">/<h1>/g' \
    -e 's#</h3>#</h1>#g' \
    -e 's/<span class="article-body">/<p>/g' \
    -e 's#</span>#</p>#g' \
    "$f"
done
echo "fixture site restored"
