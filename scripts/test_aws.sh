#!/usr/bin/env bash
#
# test_aws.sh
# Read-only connectivity check for the contract-analyzer PoC.
# Reads config.env (written by setup_aws.sh) and verifies:
#   - credentials (STS)
#   - S3 access + object put/get/delete round-trip on the configured bucket
#   - Bedrock chat invocation (Converse)
#   - Bedrock embeddings invocation (Titan)
#
# The only mutation is a tiny test object that is deleted again at the end.
#
# Usage:
#   chmod +x test_aws.sh
#   ./test_aws.sh
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# config.env lives at the repo root (where the app reads it); fall back to the
# script dir for older layouts.
if [ -f "${REPO_ROOT}/config.env" ]; then
  CONFIG_FILE="${REPO_ROOT}/config.env"
elif [ -f "${SCRIPT_DIR}/config.env" ]; then
  CONFIG_FILE="${SCRIPT_DIR}/config.env"
else
  echo "config.env not found at repo root. Copy config.env.example to config.env first."; exit 1
fi
source "$CONFIG_FILE"

AWS_REGION="${AWS_REGION:-us-east-1}"
EMBED_MODEL_ID="${EMBED_MODEL_ID:-amazon.titan-embed-text-v2:0}"
PROFILE_ARG=""
[ -n "${AWS_PROFILE:-}" ] && PROFILE_ARG="--profile ${AWS_PROFILE}"

# ---- pretty output -----------------------------------------------------------
if [ -t 1 ]; then GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YEL=$'\033[0;33m'; BLU=$'\033[0;34m'; NC=$'\033[0m'
else GREEN=""; RED=""; YEL=""; BLU=""; NC=""; fi
PASS=0; FAIL=0; WARN=0
pass() { echo "  ${GREEN}PASS${NC}  $1"; PASS=$((PASS+1)); }
fail() { echo "  ${RED}FAIL${NC}  $1"; FAIL=$((FAIL+1)); }
warn() { echo "  ${YEL}WARN${NC}  $1"; WARN=$((WARN+1)); }
info() { echo "        $1"; }
hdr()  { echo; echo "${BLU}== $1 ==${NC}"; }
aws_cmd() { aws $PROFILE_ARG --region "$AWS_REGION" "$@"; }

echo "Region: ${AWS_REGION}   Bucket: ${S3_BUCKET:-<unset>}   Chat model: ${CHAT_MODEL_ID:-<unset>}"

# ---- 1. credentials ----------------------------------------------------------
hdr "1. Credentials (STS)"
IDENT="$(aws_cmd sts get-caller-identity --query 'Arn' --output text 2>/tmp/awserr)"
if [ -n "$IDENT" ] && [ "$IDENT" != "None" ]; then pass "Authenticated as: ${IDENT}"
else fail "Auth failed. $(cat /tmp/awserr)"; fi

# ---- 2. S3 round-trip --------------------------------------------------------
hdr "2. S3 round-trip"
if [ -z "${S3_BUCKET:-}" ]; then
  fail "S3_BUCKET not set in config.env. Run ./setup_aws.sh."
else
  KEY="connectivity-check/$(date +%s)-$$.txt"
  TMPF="$(mktemp)"; echo "connectivity check" > "$TMPF"
  if aws_cmd s3 cp "$TMPF" "s3://${S3_BUCKET}/${KEY}" >/dev/null 2>/tmp/awserr; then
    pass "PutObject OK"
    aws_cmd s3 cp "s3://${S3_BUCKET}/${KEY}" "${TMPF}.back" >/dev/null 2>/tmp/awserr \
      && pass "GetObject OK" || fail "GetObject failed. $(cat /tmp/awserr)"
    aws_cmd s3 rm "s3://${S3_BUCKET}/${KEY}" >/dev/null 2>/tmp/awserr \
      && pass "DeleteObject OK (cleaned up)" \
      || warn "Could not delete test object: s3://${S3_BUCKET}/${KEY}"
  else
    fail "PutObject failed on '${S3_BUCKET}'. $(cat /tmp/awserr)"
  fi
  rm -f "$TMPF" "${TMPF}.back"
fi

# ---- 3. Bedrock chat ---------------------------------------------------------
hdr "3. Bedrock chat (Converse)"
if [ -z "${CHAT_MODEL_ID:-}" ]; then
  fail "CHAT_MODEL_ID not set. Run ./setup_aws.sh (and enable model access)."
else
  REPLY="$(aws_cmd bedrock-runtime converse --model-id "$CHAT_MODEL_ID" \
      --messages '[{"role":"user","content":[{"text":"Reply with exactly: OK"}]}]' \
      --inference-config '{"maxTokens":10,"temperature":0}' \
      --query 'output.message.content[0].text' --output text 2>/tmp/awserr)"
  if [ -n "$REPLY" ]; then
    pass "Converse OK ('${CHAT_MODEL_ID}') -> $(echo "$REPLY" | tr -d '\n')"
  else
    fail "Converse failed. $(cat /tmp/awserr)"
    case "$(cat /tmp/awserr)" in
      *AccessDenied*|*"don't have access"*|*"not authorized"*)
        info "-> Enable model access: Bedrock console > Model access (region ${AWS_REGION})." ;;
      *inference\ profile*|*"on-demand throughput isn"*)
        info "-> Use an inference profile id (e.g. us.anthropic.claude-...) in config.env." ;;
    esac
  fi
fi

# ---- 4. Bedrock embeddings ---------------------------------------------------
hdr "4. Bedrock embeddings"
EOUT="$(mktemp)"
if aws_cmd bedrock-runtime invoke-model --model-id "$EMBED_MODEL_ID" \
     --body '{"inputText":"connectivity check"}' \
     --cli-binary-format raw-in-base64-out \
     --content-type application/json --accept application/json \
     "$EOUT" >/dev/null 2>/tmp/awserr; then
  if command -v python3 >/dev/null 2>&1; then
    DIM="$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1])).get("embedding",[])))' "$EOUT" 2>/dev/null)"
    [ -n "$DIM" ] && [ "$DIM" -gt 0 ] 2>/dev/null \
      && pass "InvokeModel OK ('${EMBED_MODEL_ID}') -> embedding dim ${DIM}" \
      || warn "Returned, but no embedding vector found."
  else
    pass "InvokeModel OK ('${EMBED_MODEL_ID}')"
  fi
else
  fail "Embeddings failed. $(cat /tmp/awserr)"
  info "-> If AccessDenied: enable Titan Embeddings in Bedrock console > Model access."
fi
rm -f "$EOUT"

# ---- summary -----------------------------------------------------------------
hdr "Summary"
echo "  ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}, ${YEL}${WARN} warning(s)${NC}"
echo
if [ "$FAIL" -eq 0 ]; then
  echo "  ${GREEN}All critical checks passed.${NC} Live Bedrock + S3 are safe for the demo."
  exit 0
else
  echo "  ${RED}Some checks failed.${NC} See hints above; most fixes are model access + IAM perms."
  exit 1
fi
