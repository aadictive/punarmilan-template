# Operator guide: hosting chapters in one AWS account

For whoever owns the AWS account and onboards other chapters. Each chapter gets its **own
isolated site** (own CloudFormation stack, DynamoDB table, S3 bucket, CloudFront distribution,
Lambda functions, Stripe account, Gmail sender). What they share is only your AWS account.

## How isolation works

Every resource is named from the stack name, and the stack name is the chapter's `chapter_id`
(`somaiya-chicago-RegisterFunction-AbC123`, `somaiya-chicago-TicketsTable-...`). The per-chapter
IAM user's policy only allows actions on resources whose names start with `<chapter_id>-`, on the
stack `<chapter_id>`, and on that chapter's prefix in the shared artifact bucket
(`docs/iam-deploy-policy.template.json`). Stacks carry the tags `app=punarmilan` and
`chapter=<chapter_id>`, so cost reports can be split per chapter (activate the `chapter` tag under
Billing -> Cost allocation tags).

## One-time account setup

1. **Pick a region** (default `us-east-1`) and use it for every chapter.
2. **Create one artifact bucket** for SAM uploads (any private bucket, e.g.
   `punarmilan-deploy-artifacts-<account-id>`). It's shared; each chapter can only write under its own
   `<chapter_id>/` prefix.
3. Have AWS admin credentials configured locally (`aws sts get-caller-identity` works).

## Onboarding a chapter (about 10 minutes of your time)

1. Agree the chapter's **`chapter_id`** (3-20 chars, lowercase letters/numbers/hyphens). **Rule:** no
   chapter id may be another id followed by a hyphen. `chi` and `chi-west` would overlap because the
   policy matches by name prefix (`chi-*`). The script below refuses overlapping ids.
2. Create their deploy login:
   ```bash
   scripts/admin/create-chapter-deployer.sh <chapter_id> <artifact-bucket>
   # add --dry-run first to see the exact policy that would be created
   ```
   It creates IAM policy + user `<chapter_id>-deployer` and one access key, printed once.
3. Give the chapter lead, **privately** (a password manager's secure-share link; not chat/email):
   `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, the `ARTIFACT_BUCKET` name, and the region if it isn't
   `us-east-1`. They follow the README from Step 1.
4. Watch their **first deploy** (Actions tab, or ask them to share the log). See "First-deploy shakedown".
5. After it succeeds, they add the Stripe webhook (README Step 7) - the webhook URL is in the run summary.

The chapter's own passwords (admin password, check-in key, Gmail app password, Stripe keys) never
reach you: they paste them straight into their repository's GitHub Secrets.

## First-deploy shakedown (do this once, before the first real chapter)

The permission policy is written from the resource types the template creates and has been checked with
IAM Access Analyzer (`aws accessanalyzer validate-policy`), but CloudFormation's exact permission needs
are only proven by a real run. Do a dress rehearsal with a throwaway chapter:

1. Create a scratch repo from the template, `chapter_id: zz-test`, run `create-chapter-deployer.sh zz-test <bucket>`.
2. Set the secrets, run **Deploy site**. If it fails with `AccessDenied`/`is not authorized to perform:
   <action> on resource: <arn>`, that message names the exact missing permission. Add it to
   `docs/iam-deploy-policy.template.json` **scoped to the resource pattern in the message**, re-create the
   policy (`aws iam create-policy-version --set-as-default`), and re-run. CloudTrail (Event history,
   filter "Error code: AccessDenied") shows the same.
3. Check the full flow from README Step 8 on the throwaway site.
4. Clean up: empty the site bucket first (`aws s3 rm s3://<site-bucket> --recursive`), then
   `aws cloudformation delete-stack --stack-name zz-test`. The **DynamoDB table is retained on purpose**, so delete
   it by hand if it was only a test. Then remove the throwaway IAM user and policy.

If a first deploy fails part-way, the stack can sit in `ROLLBACK_COMPLETE`, which must be deleted
(`aws cloudformation delete-stack`) before that chapter deploys again. Only you (or the deployer key,
which is allowed to delete its own stack) can do that.

## What this permission model does and doesn't protect against

Be clear-eyed about it:

- **Protects:** the chapter's keys cannot read or change another chapter's stack, Lambda functions, table
  or bucket, and cannot touch anything outside those name patterns. A leaked key's blast radius is that
  one chapter's site.
- **Does not fully protect (residual risk):**
  - *CloudFront* has no resource-level permissions for creating distributions or Origin Access Controls,
    so those actions are allowed on `*`. Updating/deleting/invalidating a **distribution** is restricted to
    ones tagged `chapter=<chapter_id>`; OAC changes are not restricted.
  - *IAM privilege escalation:* the deployer can create roles named `<chapter_id>-*` and attach/put policies on
    them. A malicious holder of the key could give such a role broad rights and then use a Lambda function
    running as it. The keys should therefore be treated as sensitive, and only trusted people should hold them.
    **Hardening (recommended before opening this to many chapters):** add an IAM *permissions boundary* policy
    that allows only what the functions need (DynamoDB on their table, CloudWatch Logs), require it on
    `iam:CreateRole` with an `iam:PermissionsBoundary` condition, and set `PermissionsBoundary` on the
    template's functions.
  - Anyone who can push to a chapter's `main` branch can read that chapter's secrets via the workflow.
- Each chapter's Stripe/Gmail credentials are stored only as encrypted GitHub Secrets and as Lambda
  environment variables in **your** account (NoEcho CloudFormation parameters). As account owner you can
  technically read Lambda environment variables - say so plainly to chapters, or have chapters use their own
  AWS accounts if that isn't acceptable.

## Alternative: a chapter deploys into its own AWS account

Nothing here is tied to your account. A chapter can fork the template, create an IAM user with rights to
CloudFormation/Lambda/IAM roles/DynamoDB/S3/CloudFront in their own account, and add its keys as the same
two GitHub Secrets. `ARTIFACT_BUCKET` may be omitted (SAM then creates its own).

## Offboarding a chapter

1. `aws cloudformation delete-stack --stack-name <chapter_id>` (empty the site bucket first).
2. Export/delete the retained DynamoDB table when the chapter no longer needs the data:
   `aws dynamodb delete-table --table-name <table>` (find it with `aws dynamodb list-tables`).
3. `aws iam delete-access-key`, detach + delete the policy, delete user `<chapter_id>-deployer`.
4. Remove the chapter's prefix from the artifact bucket.

## Rotating a chapter's AWS key

`aws iam create-access-key --user-name <chapter_id>-deployer`, give the new pair to the chapter lead to
update in GitHub Secrets, then `aws iam delete-access-key` for the old one.

## Updating everyone to a new template version

Chapters own their copy. To share fixes, tell them what changed and have them copy the changed files
(everything except `chapter.config.yaml`, `content/`, `assets/` is code) - or make the template repository
public/organisation-visible and have chapters pull from it with GitHub's "Sync fork" if they created a fork
instead of using "Use this template".
