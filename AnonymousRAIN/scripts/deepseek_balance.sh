#!/usr/bin/env bash
set -euo pipefail

DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"

usage() {
  cat <<'EOF'
:
  DEEPSEEK_API_KEY=... ./scripts/deepseek_balance.sh

:
  DEEPSEEK_API_ROOT   DeepSeek API ( https://api.deepseek.com)
  DEEPSEEK_BASE_URL    DEEPSEEK_API_ROOT, /v1/chat/completions 
                      ( run.sh  DEEPSEEK_BASE_URL ,)

:
   GET /user/balance,( jq /)
EOF
}

# Chat  DEEPSEEK_BASE_URL  /v1/chat/completions; API 
_normalize_deepseek_api_root() {
  local raw="${1:-https://api.deepseek.com}"
  raw="${raw%/}"
  case "$raw" in
    */v1/chat/completions) raw="${raw%/v1/chat/completions}" ;;
    */chat/completions) raw="${raw%/chat/completions}" ;;
  esac
  printf '%s' "${raw:-https://api.deepseek.com}"
}

if [[ -n "${DEEPSEEK_API_ROOT:-}" ]]; then
  _api_root="$(_normalize_deepseek_api_root "$DEEPSEEK_API_ROOT")"
else
  _api_root="$(_normalize_deepseek_api_root "${DEEPSEEK_BASE_URL:-https://api.deepseek.com}")"
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ -z "$DEEPSEEK_API_KEY" ]]; then
  echo ":  DEEPSEEK_API_KEY" >&2
  echo ": DEEPSEEK_API_KEY=... ./scripts/deepseek_balance.sh" >&2
  exit 2
fi

url="${_api_root}/user/balance"

set +e
resp_with_code="$(
  curl -sS \
    -H "Authorization: Bearer ${DEEPSEEK_API_KEY}" \
    -H "Accept: application/json" \
    -w $'\n__HTTP_STATUS__:%{http_code}\n' \
    "$url" 2>&1
)"
curl_exit_code=$?
set -e

if [[ $curl_exit_code -ne 0 ]]; then
  echo ": GET $url" >&2
  echo "curl : $curl_exit_code" >&2
  echo "$resp_with_code" >&2
  exit 3
fi

http_status="$(printf '%s' "$resp_with_code" | awk -F: '/^__HTTP_STATUS__:/ {print $2; exit}')"
resp="$(printf '%s' "$resp_with_code" | sed '/^__HTTP_STATUS__:/d')"

if [[ -z "${http_status:-}" || "$http_status" -lt 200 || "$http_status" -ge 300 ]]; then
  echo ": GET $url" >&2
  echo "HTTP : ${http_status:-unknown}" >&2
  if [[ -n "$resp" ]]; then
    echo ":" >&2
    echo "$resp" >&2
  fi
  exit 3
fi

printf ': %s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')"

if command -v jq >/dev/null 2>&1; then
  echo "$resp" | jq -r '
    def fmt_money($x): if $x == null then "null" else ($x|tostring) end;
    if (.balance_infos? | type) == "array" then
      "is_available: " + ((.is_available // "unknown")|tostring) + "\n"
      + (
        .balance_infos
        | map(
            "- currency=" + (.currency|tostring)
            + " total=" + fmt_money(.total_balance)
            + " granted=" + fmt_money(.granted_balance)
            + " topped_up=" + fmt_money(.topped_up_balance)
          )
        | join("\n")
      )
    else
      .
    end
  '
else
  echo "$resp"
fi

