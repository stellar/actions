# Security and access

## The publishing account

- Publishing uses a dedicated Confluence service account, not a person. Its
  edits show up as that account.
- Its API token is scoped to pages and attachments, plus setting page
  restrictions. It has no admin, user-management or space-settings rights.
- Its space permissions come from the `confluence-docs-publishers` group.

## Where the token lives

- The token is stored once, in AWS Secrets Manager
  (`confluence/docs-publisher`). No repo, GitHub secret or workflow file holds
  it.
- At publish time, the Action signs in to AWS with GitHub's OIDC token and
  reads the secret for that run only. The token is masked in the logs.
- The AWS role (`github-actions-confluence-publish`) trusts only the default
  branch of the repos on its list. Pull requests, other branches and forks
  are refused by AWS, whatever their workflow says. Adding a repo to the list
  is a reviewed `stellar/terraform` change.
- Pull requests use `check-only`, which needs no credentials at all.

## Restricting who can read docs

To hide a repo's docs from the wider space, put a view restriction on its root
page. View restrictions apply to every page beneath, so everything published
there is covered.

Always include the `confluence-docs-publishers` group in the restriction.
Without it, the publisher can't see or edit those pages, and the next run
fails. Nothing is overwritten or duplicated; adding the group back fixes it.

The source must be restricted too: restricted docs belong in a private repo
whose access matches the page restriction.

## Rotating the token

Atlassian tokens expire after at most a year. To rotate, create a new token
for the service account and update the secret in AWS. No repo changes. An
expired token fails publishing with a 401 error.

## Audit trail

- **Confluence:** every change is a page version by the service account,
  naming the repo and commit.
- **GitHub:** the workflow run shows which commit was published and what
  changed.
- **AWS:** CloudTrail records each read of the secret, and by which repo and
  branch.
