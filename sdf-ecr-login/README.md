# ECR Login via OIDC — Composite Action

Reusable GitHub Actions composite action that handles AWS OIDC authentication, ECR login (private and public), and automatic ECR repository creation. Callers must provide the OIDC and ECR role ARNs as inputs, and can optionally override the AWS region and enable public ECR login.

This action also installs an `ecr-push` CLI command that replaces `docker push`. It automatically creates the ECR repository (with the correct `Repository` tag) if it doesn't already exist, then pushes the image.

## Usage

```yaml
permissions:
  id-token: write
  contents: read

steps:
  - uses: actions/checkout@v6

    # Authenticate with stellar AWS ECR.
  - name: ECR Login via OIDC
    id: ecr-login
    uses: stellar/actions/sdf-ecr-login@main
    with:
      aws-oidc-role: ${{ secrets.AWS_GITHUB_OIDC_ROLE }}       # required
      aws-ecr-login-role: ${{ secrets.AWS_ECR_LOGIN_ROLE }}     # required
      aws-region: 'us-east-1'        # optional, defaults to us-east-1
      login-public-ecr: 'true'       # optional, defaults to false

    # Build docker image with registry details
  - name: Build docker image
    env:
      ECR_REGISTRY: ${{ steps.ecr-login.outputs.ecr-registry }}
      IMAGE_TAG: ${{ github.sha }}
      ECR_REPOSITORY: dev/image-name # Format: <namespace>/<image-name>. Use dev, stg, or prd as namespace.
    run: |
      docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .

    # Push image to private AWS ECR registry using ecr-push.
    # ecr-push automatically creates the ECR repository if it doesn't exist.
  - name: Push image to Amazon ECR private registry
    env:
      ECR_REGISTRY: ${{ steps.ecr-login.outputs.ecr-registry }}
      IMAGE_TAG: ${{ github.sha }}
      ECR_REPOSITORY: dev/image-name
    run: |
      ecr-push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG

```

## `ecr-push` CLI

The action installs `ecr-push` onto `$GITHUB_PATH`, making it available in all subsequent steps. Use it as a drop-in replacement for `docker push`:

```bash
ecr-push <image:tag>
```

It will:
1. Extract the repository name from the image URI
2. Create the ECR repository if it doesn't exist, tagging it with `Repository: <owner/repo>` (derived from `github.repository`)
3. Push the image via `docker push`

**Note:** `ecr-push` only supports private ECR repositories. Public ECR repositories are managed via Terraform and must be created separately.

## Inputs

| Name | Required | Default | Description |
|------|----------|---------|-------------|
| `aws-oidc-role` | **yes** | — | ARN of the IAM role to assume via OIDC |
| `aws-ecr-login-role` | **yes** | — | ARN of the IAM role to assume for ECR push (role chaining) |
| `aws-region` | no | `us-east-1` | AWS region for ECR |
| `login-public-ecr` | no | `false` | Set to `true` to also log into ECR Public |


## Important security note:
1. ECR repositories created by `ecr-push` are automatically tagged with `Repository: <owner/repo>` (e.g., `stellar/my-service`). The IAM policy ensures only workflows from the matching GitHub repository can push images, as the tag must match the caller's `github.repository`.

2. Always include a `permissions` section with `id-token: write` and `contents: read` to enable OIDC authentication. These permissions are required for secure AWS authentication and access to repository contents.
