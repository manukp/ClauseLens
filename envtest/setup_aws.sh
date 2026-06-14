#!/usr/bin/env bash
#
# setup_aws.sh
# Provisions the AWS resources the contract-analyzer PoC needs in us-east-1:
#   - one private S3 bucket for uploads
#   - detects a WORKING, current-generation Bedrock Claude model (skips Legacy)
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

if aws_cmd s3api put-public-access-block --bucket "$S3_BUCKET" \
    --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true \
    >/dev/null 2>/tmp/awserr; then
  ok "Public access blocked on bucket."
else
  warn "Could not set public access block: $(cat /tmp/awserr)"
fi

# ---- 2. Bedrock model detection (ACTIVE only, current-gen first) ------------
hdr "2. Bedrock models"
aws_cmd bedrock list-inference-profiles \
  --query 'inferenceProfileSummaries[].inferenceProfileId' --output text 2>/dev/null \
  | tr '\t' '\n' | grep -i claude > /tmp/ip_claude || true
aws_cmd bedrock list-foundation-models --by-provider Anthropic \
  --query "modelSummaries[?modelLifecycle.status=='ACTIVE'].modelId" --output text 2>/dev/null \
  | tr '\t' '\n' | grep -i claude > /tmp/fm_active || true

info "Current-gen Claude inference profiles found:"
if [ -s /tmp/ip_claude ]; then
  grep -iv 'claude-3' /tmp/ip_claude | sed 's/^/          /'
else
  info "          (none listed — model access may be off)"
fi

# Build an ordered, de-duplicated candidate list:
#   user-set id (if any) -> current-gen profiles (haiku, sonnet, other)
#   -> active base model ids -> legacy claude-3 profiles (last resort).
{
  [ -n "${CHAT_MODEL_ID:-}" ] && echo "$CHAT_MODEL_ID"
  grep -iv 'claude-3' /tmp/ip_claude 2>/dev/null | grep -i haiku
  grep -iv 'claude-3' /tmp/ip_claude 2>/dev/null | grep -i sonnet
  grep -iv 'claude-3' /tmp/ip_claude 2>/dev/null
  grep -i haiku /tmp/fm_active 2>/dev/null
  grep -i sonnet /tmp/fm_active 2>/dev/null
  cat /tmp/fm_active 2>/dev/null
  grep -i 'claude-3' /tmp/ip_claude 2>/dev/null
} | grep -v '^$' | awk '!seen[$0]++' > /tmp/cand

# ---- 3. Probe access: invoke candidates until one works ---------------------
hdr "3. Bedrock access check"
CHOSEN=""; LASTERR=""; TRIED=0
while IFS= read -r cand; do
  [ -z "$cand" ] && continue
  TRIED=$((TRIED+1))
  [ "$TRIED" -gt 8 ] && break
  REPLY="$(aws_cmd bedrock-runtime converse --model-id "$cand" \
      --messages '[{"role":"user","content":[{"text":"Reply with: OK"}]}]' \
      --inference-config '{"maxTokens":10,"temperature":0}' \
      --query 'output.message.content[0].text' --output text 2>/tmp/awserr)"
  if [ -n "$REPLY" ] && [ "$REPLY" != "None" ]; then
    CHOSEN="$cand"
    ok "Invoked OK: ${cand}  (reply: $(echo "$REPLY" | tr -d '\n'))"
    break
  else
    LASTERR="$(cat /tmp/awserr)"
    info "tried ${cand} -> $(echo "$LASTERR" | tr '\n' ' ' | cut -c1-110)"
  fi
done < /tmp/cand

if [ -n "$CHOSEN" ]; then
  CHAT_MODEL_ID="$CHOSEN"
  ok "Chat model selected: ${CHAT_MODEL_ID}"
else
  warn "No Claude model could be invoked yet."
  [ -n "$LASTERR" ] && info "Last error: $(echo "$LASTERR" | tr '\n' ' ')"
  info "The 3.x models are Legacy; you likely need to enable CURRENT models:"
  info "  Console > Amazon Bedrock > Model access > Modify model access"
  info "  Enable Claude Haiku 4.5 and Claude Sonnet 4.6 in ${AWS_REGION}, accept terms, save."
  info "  Then re-run ./setup_aws.sh."
  info "Known-good current IDs you can also set by hand in config.env:"
  info "  us.anthropic.claude-haiku-4-5-20251001-v1:0   (cheap, high volume)"
  info "  us.anthropic.claude-sonnet-4-6                (reasoning)"
fi

# ---- 4. Write config.env -----------------------------------------------------
hdr "4. Writing config.env"
cat > "$CONFIG_FILE" <<CFG
# config.env  —  generated by setup_aws.sh on $(date)
AWS_REGION=${AWS_REGION}
AWS_PROFILE=${AWS_PROFILE:-}
S3_BUCKET=${S3_BUCKET}
CHAT_MODEL_ID=${CHAT_MODEL_ID:-}
EMBED_MODEL_ID=${EMBED_MODEL_ID}
CFG
ok "Wrote ${CONFIG_FILE}"
echo
if [ -n "$CHOSEN" ]; then
  echo "${GREEN}Setup complete.${NC} Next: run ./test_aws.sh to verify end-to-end connectivity."
else
  echo "${YEL}Setup partly complete.${NC} Enable current Claude models (above), then re-run ./setup_aws.sh."
fi
