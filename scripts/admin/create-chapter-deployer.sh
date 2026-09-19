#!/usr/bin/env bash
# =============================================================================
# create-chapter-deployer.sh   (for the person who OWNS the AWS account)
#
# Creates the narrowly-scoped AWS login a chapter's GitHub Action uses to deploy
# that chapter's site - and nothing else. Run it once per chapter, with your
# own AWS admin credentials, BEFORE the chapter's first deploy.
#
#   scripts/admin/create-chapter-deployer.sh <chapter_id> <artifact_bucket> [--dry-run]
#
#   chapter_id       the same chapter_id that is in their chapter.config.yaml
#   artifact_bucket  an S3 bucket in your account that SAM may upload code to
#                    (create one bucket once, reuse it for every chapter)
#   --dry-run        only print the policy that would be created
#
# What it creates: an IAM policy "<chapter_id>-deployer", an IAM user
# "<chapter_id>-deployer" with that policy, and ONE access key, printed once at
# the end. Hand those two values to the chapter lead to paste into their repo's
# GitHub Secrets as AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.
# See docs/OPERATOR-GUIDE.md for the full onboarding checklist.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/../.."

CHAPTER="${1:-}"; BUCKET="${2:-}"; MODE="${3:-}"
[ -n "$CHAPTER" ] && [ -n "$BUCKET" ] || { sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }
[[ "$CHAPTER" =~ ^[a-z][a-z0-9-]{1,18}[a-z0-9]$ ]] || { echo "chapter_id must be 3-20 chars: lowercase letters, numbers, hyphens." >&2; exit 1; }

REGION="${AWS_REGION:-us-east-1}"
if [ "$MODE" = "--dry-run" ]; then ACCOUNT="000000000000"; else ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"; fi

POLICY_JSON="$(sed -e "s/__CHAPTER_ID__/$CHAPTER/g" -e "s/__ACCOUNT_ID__/$ACCOUNT/g" -e "s/__REGION__/$REGION/g" -e "s/__ARTIFACT_BUCKET__/$BUCKET/g" docs/iam-deploy-policy.template.json)"
echo "$POLICY_JSON" | python3 -m json.tool >/dev/null || { echo "Rendered policy is not valid JSON" >&2; exit 1; }

if [ "$MODE" = "--dry-run" ]; then echo "$POLICY_JSON" | python3 -m json.tool; exit 0; fi

# Overlap check: chapter ids scope permissions by name prefix ("<id>-*"), so one
# id that starts with another id plus a hyphen would overlap its resources.
for other in $(aws iam list-users --query "Users[?ends_with(UserName, '-deployer')].UserName" --output text); do
  o="${other%-deployer}"
  if [ "$o" != "$CHAPTER" ] && { [[ "$CHAPTER" == "$o-"* ]] || [[ "$o" == "$CHAPTER-"* ]]; }; then
    echo "chapter_id '$CHAPTER' overlaps with existing chapter '$o' (one is a hyphenated prefix of the other). Pick a different id." >&2; exit 1
  fi
done

POLICY_ARN="arn:aws:iam::$ACCOUNT:policy/$CHAPTER-deployer"
aws iam create-policy --policy-name "$CHAPTER-deployer" --policy-document "$POLICY_JSON" --tags Key=app,Value=punarmilan Key=chapter,Value="$CHAPTER" >/dev/null
aws iam create-user --user-name "$CHAPTER-deployer" --tags Key=app,Value=punarmilan Key=chapter,Value="$CHAPTER" >/dev/null
aws iam attach-user-policy --user-name "$CHAPTER-deployer" --policy-arn "$POLICY_ARN"
KEY_JSON="$(aws iam create-access-key --user-name "$CHAPTER-deployer" --output json)"

cat <<EOF

Created deployer '$CHAPTER-deployer' (policy $POLICY_ARN).

Give the chapter lead these two values PRIVATELY (a password manager's secure
share is ideal - not chat or email). They paste them into their repository:
Settings -> Secrets and variables -> Actions -> New repository secret.

  AWS_ACCESS_KEY_ID      = $(echo "$KEY_JSON" | python3 -c 'import sys,json;print(json.load(sys.stdin)["AccessKey"]["AccessKeyId"])')
  AWS_SECRET_ACCESS_KEY  = $(echo "$KEY_JSON" | python3 -c 'import sys,json;print(json.load(sys.stdin)["AccessKey"]["SecretAccessKey"])')

Also tell them to add a repository VARIABLE (Variables tab, not Secrets):
  ARTIFACT_BUCKET = $BUCKET
  AWS_REGION      = $REGION   (only if it isn't us-east-1)

This is the only time the secret key is shown. To rotate it later, create a new
key with 'aws iam create-access-key' and delete the old one.
EOF
