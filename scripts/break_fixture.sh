#!/usr/bin/env bash
# Break the fixture site: change the HTML structure the scraper depends on.
# The AcmeDB fixture site uses semantic tags (<article>, <h1>, <p>, <pre><code>)
# with no CSS classes. This "redesign" swaps those tags so the scraper's
# selectors return empty body_text — the heal demo trigger.
#
# Uses h3 (not h2) for the title so there is no collision with existing <h2>
# section headings during restore.
set -euo pipefail
cd "$(dirname "$0")/../demo/fixture-site"

for f in *.html; do
  sed -i '' \
    -e 's/<article>/<div class="content-v2">/g' \
    -e 's#</article>#</div>#g' \
    -e 's/<h1/<h3 class="page-heading"/g' \
    -e 's#</h1>#</h3>#g' \
    -e 's/<p>/<span class="article-body">/g' \
    -e 's#</p>#</span>#g' \
    "$f"
done
echo "fixture site broken: article->div, h1->h3, p->span"
