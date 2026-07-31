#!/usr/bin/env bash
# Install SEO-Agent as a Hermes user plugin via symlink.
# Does NOT modify the hermes-agent repository — only ~/.hermes/plugins/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_SRC="${SCRIPT_DIR}/seo_agent_plugin"
HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
PLUGIN_DST="${HERMES_HOME}/plugins/seo-agent"

if [[ ! -f "${PLUGIN_SRC}/plugin.yaml" ]]; then
  echo "ERROR: plugin not found at ${PLUGIN_SRC}" >&2
  exit 1
fi

mkdir -p "${HERMES_HOME}/plugins"

if [[ -L "${PLUGIN_DST}" ]]; then
  rm -f "${PLUGIN_DST}"
elif [[ -e "${PLUGIN_DST}" ]]; then
  echo "ERROR: ${PLUGIN_DST} exists and is not a symlink. Move it aside first." >&2
  exit 1
fi

ln -s "${PLUGIN_SRC}" "${PLUGIN_DST}"
echo "Linked: ${PLUGIN_DST} -> ${PLUGIN_SRC}"

# Best-effort: ensure plugins.enabled includes seo-agent in ~/.hermes/config.yaml
CONFIG="${HERMES_HOME}/config.yaml"
if [[ -f "${CONFIG}" ]]; then
  if grep -qE '^\s*-\s*seo-agent\s*$' "${CONFIG}"; then
    echo "seo-agent already listed in ${CONFIG}"
  else
    echo ""
    echo "Add this to ${CONFIG} (or run: hermes plugins enable seo-agent):"
    echo ""
    cat "${SCRIPT_DIR}/hermes.config.snippet.yaml"
  fi
else
  echo "No ${CONFIG} found yet. After Hermes setup, run:"
  echo "  hermes plugins enable seo-agent"
  echo "Or merge ${SCRIPT_DIR}/hermes.config.snippet.yaml into your config."
fi

echo ""
echo "Done. Restart Hermes / start a new session so tools load."
echo "Tools: audit_site, optimize_page, generate_report, compare_audits, list_seo_history"
