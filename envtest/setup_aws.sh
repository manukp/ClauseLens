#!/usr/bin/env bash
#
# setup_aws.sh
# Provisions the AWS resources the contract-analyzer PoC needs in us-east-1:
#   - one private S3 bucket for uploads
#   - detects the Bedrock Claude model/inference-profile id to use
#   - verifies Bedrock model access (cannot enable it for you; will instruct)
#   - writes resolved values into config.env
#
# Idempotent: safe to run multiple times.
#
# Usage:
#   chmod +x setup_aws.sh
#   ./setup_aws.sh
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config.env"
[ -f "$CONFIG_FILE" ] && source "$CONFIG_FILE"

AWS_REGION="${AWS_REGION:-us-east-1}"
EMBED_MODEL_ID="${EMBED_MODEL_ID:-amazon.titan-embed-text-v2:0}"
PROFILE_ARG=""
[ -n "${AWS_PROFILE:-}" ] && PROFILE_ARG="--profile ${AWS_PROFILE}"

# ---- pretty output -----------------------------------------------------------
if [ -t 1 ]; then GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YEL=$'\033[0;33m'; BLU=$'\033[0;34m'; NC=$'\033[0m'
else GREEN=""; RED=""; YEL=""; BLU=""; NC=""; fi
ok()   { echo "  ${GREEN}OK${NC}    $1"; }
err()  { echo "  ${RED}ERR${NC}   $1"; }
warn() { echo "  ${YEL}WARN${NC}  $1"; }
info() { echo "        $1"; }
hdr()  { echo; echo "${BLU}== $1 ==${NC}"; }
aws_cmd() { aws $PROFILE_ARG --region "$AWS_REGION" "$@"; }

# ---- 0. prerequisites + identity --------------------------------------------
hdr "0. Prerequisites"
command -v aws >/dev/null 2>&1 || { err "AWS CLI not found. Install AWS CLI v2 first."; exit 1; }
ok "AWS CLI present: $(aws --version 2>&1)"

ACCOUNT_ID="$(aws_cmd sts get-caller-identity --query 'Account' --output text 2>/tmp/awserr)"
if [ -z "$ACCOUNT_ID" ] || [ "$ACCOUNT_ID" = "None" ]; then
  err "Could not authenticate. $(cat /tmp/awserr)"
  info "Fix credentials (aws configure / AWS_PROFILE), then re-run."
  exit 1
fi
ok "Account: ${ACCOUNT_ID}   Region: ${AWS_REGION}"

# ---- 1. S3 bucket ------------------------------------------------------------
hdr "1. S3 bucket"
if [ -z "${S3_BUCKET:-}" ]; then
  S3_BUCKET="contract-analyzer-poc-${ACCOUNT_ID}"
  info "No bucket configured; using generated name: ${S3_BUCKET}"
fi

if aws_cmd s3api head-bucket --bucket "$S3_BUCKET" >/dev/null 2>/tmp/awserr; then
  ok "Bucket already exists and is accessible: ${S3_BUCKET}"
else
  info "Creating bucket ${S3_BUCKET} ..."
  # us-east-1 must NOT receive a LocationConstraint; other regions must.
  if [ "$AWS_REGION" = "us-east-1" ]; then
    CREATE_OUT="$(aws_cmd s3api create-bucket --bucket "$S3_BUCKET" 2>&1)"
  else
    CREATE_OUT="$(aws_cmd s3api create-bucket --bucket "$S3_BUCKET" \
      --create-bucket-configuration "LocationConstraint=${AWS_REGION}" 2>&1)"
  fi
  if [ $? -eq 0 ]; then
    ok "Bucket created: ${S3_BUCKET}"
  else
    case "$CREATE_OUT" in
      *BucketAlreadyOwnedByYou*) ok "Bucket already owned by you: ${S3_BUCKET}" ;;
      *BucketAlreadyExists*)
        err "Bucket name '${S3_BUCKET}' is taken globally by another account."
        info "Set a unique S3_BUCKET in config.env and re-run." ; exit 1 ;;
      *) err "Bucket creation failed: ${CREATE_OUT}" ; exit 1 ;;
    esac
  fi
fi

# Lock down public access (security baseline; makes the bucket more private).
if aws_cmd s3api put-public-access-block --bucket "$S3_BUCKET" \
    --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true \
    >/dev/null 2>/tmp/awserr; then
  ok "Public access blocked on bucket."
else
  warn "Could not set public access block: $(cat /tmp/awserr)"
fi

# ---- 2. Bedrock model detection ---------------------------------------------
hdr "2. Bedrock models"
aws_cmd bedrock list-inference-profiles \
  --query 'inferenceProfileSummaries[].inferenceProfileId' --output text >/tmp/ip 2>/dev/null
aws_cmd bedrock list-foundation-models --by-provider Anthropic \
  --query 'modelSummaries[].modelId' --output text >/tmp/fm 2>/dev/null

if [ -z "${CHAT_MODEL_ID:-}" ]; then
  # Prefer a US Claude inference profile, prefer Haiku (cheapest) for the app's
  # high-volume steps; fall back to any Claude profile, then base model ids.
  CHAT_MODEL_ID="$(tr '\t' '\n' < /tmp/ip 2>/dev/null | grep -i 'claude' | grep -i 'haiku' | head -n1)"
  [ -z "$CHAT_MODEL_ID" ] && CHAT_MODEL_ID="$(tr '\t' '\n' < /tmp/ip 2>/dev/null | grep -i 'claude' | head -n1)"
  [ -z "$CHAT_MODEL_ID" ] && CHAT_MODEL_ID="$(tr '\t' '\n' < /tmp/fm 2>/dev/null | grep -i 'haiku' | head -n1)"
  [ -z "$CHAT_MODEL_ID" ] && CHAT_MODEL_ID="$(tr '\t' '\n' < /tmp/fm 2>/dev/null | grep -i 'claude' | head -n1)"
fi

if [ -n "${CHAT_MODEL_ID:-}" ]; then
  ok "Selected chat model id: ${CHAT_MODEL_ID}"
else
  warn "No Claude model id found. You likely need to enable model access (below)."
fi
info "Claude inference profiles found:"
tr '\t' '\n' < /tmp/ip 2>/dev/null | grep -i 'claude' | sed 's/^/          /' || info "          (none)"

# ---- 3. Verify Bedrock access (cannot enable it for you) ---------------------
hdr "3. Bedrock access check"
if [ -n "${CHAT_MODEL_ID:-}" ]; then
  REPLY="$(aws_cmd bedrock-runtime converse --model-id "$CHAT_MODEL_ID" \
      --messages '[{"role":"user","content":[{"text":"Reply with: OK"}]}]' \
      --inference-config '{"maxTokens":10,"temperature":0}' \
      --query 'output.message.content[0].text' --output text 2>/tmp/awserr)"
  if [ $? -eq 0 ] && [ -n "$REPLY" ]; then
    ok "Bedrock chat access confirmed (model replied)."
  else
    warn "Chat model access NOT yet granted."
    info "$(cat /tmp/awserr)"
    info "Enable it once (manual, ~1 min):"
    info "  Console > Amazon Bedrock > Model access > Modify model access"
    info "  Enable the Anthropic Claude models in ${AWS_REGION}, accept terms, save."
    info "  Then re-run this script (or just ./test_aws.sh)."
  fi
else
  warn "Skipping access check (no model id)."
fi

# ---- 4. Write config.env -----------------------------------------------------
hdr "4. Writing config.env"
cat > "$CONFIG_FILE" <<EOF
# config.env  —  generated by setup_aws.sh on $(date)
AWS_REGION=${AWS_REGION}
AWS_PROFILE=${AWS_PROFILE:-}
S3_BUCKET=${S3_BUCKET}
CHAT_MODEL_ID=${CHAT_MODEL_ID:-}
EMBED_MODEL_ID=${EMBED_MODEL_ID}
EOF
ok "Wrote ${CONFIG_FILE}"
echo
echo "${GREEN}Setup complete.${NC} Next: run ./test_aws.sh to verify end-to-end connectivity."
