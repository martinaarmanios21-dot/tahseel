#!/usr/bin/env bash
# Rebuild the Tahseel web app (frontend/) and copy the static files into the Python package.
# Reviewers don't need this: the built app is committed in revenue_agent/web/app/.
set -euo pipefail
cd "$(dirname "$0")/../frontend"
npm install --no-audit --no-fund
# npm sometimes skips rolldown's native binary on Apple Silicon; install it explicitly if missing.
if [[ "$(uname -sm)" == "Darwin arm64" ]] && ! node -e "require('@rolldown/binding-darwin-arm64')" 2>/dev/null; then
  npm install --no-save --no-audit --no-fund "@rolldown/binding-darwin-arm64@$(node -p "require('rolldown/package.json').version")"
fi
rm -rf .output
npm run build
rm -rf ../revenue_agent/web/app
cp -R .output/public ../revenue_agent/web/app
echo "built -> revenue_agent/web/app"
