# ECR Login via OIDC — Composite Action

Reusable GitHub Actions composite action that handles AWS OIDC authentication and ECR login (private and public). Role ARNs are pre-configured — callers can optionally override the AWS region and enable public ECR login.

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
    # uses: stellar/actions/sdf-ecr-login@main  # cross-repo ref
    with:
      aws-region: 'us-east-1'        # optional, defaults to us-east-1
      login-public-ecr: 'true'       # optional, defaults to false

    # Build docker image with registry details
  - name: Build docker image
    env:
      ECR_REGISTRY: ${{ steps.ecr-login.outputs.ecr-registry }}
      IMAGE_TAG: ${{ github.sha }}
      ECR_REPOSITORY: dev/image-name # Format: <namespace>/<image-name>. Use dev, stg, or prd as namespace. The repository dev/image-name must have the tag Repository: <stellar/github-repo-name>, where github-repo-name is the repo running the GitHub Action.
    run: |
      docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .

    # Push image to private AWS ECR registry.
  - name: Push image to Amazon ECR private registry
    env:
      ECR_REGISTRY: ${{ steps.ecr-login.outputs.ecr-registry }}
      IMAGE_TAG: ${{ github.sha }}
    run: |
      docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG

    # Build and push image to public AWS ECR registry: public.ecr.aws/stellar/<image-name>
  - name: Build and push image to Amazon ECR public repository
    env:
      ECR_PUBLIC_REGISTRY: ${{ steps.ecr-login.outputs.ecr-public-registry }}
      REGISTRY_ALIAS: stellar
      REPOSITORY: image-name # The AWS ECR public repository stellar/image-name must have the tag Repository: <stellar/github-repo-name>, where github-repo-name is the repo running the GitHub Action.
      IMAGE_TAG: ${{ github.sha }}
    run: |
      echo "Pushing image to public repo"
      docker build $ECR_PUBLIC_REGISTRY/$REGISTRY_ALIAS/$REPOSITORY:$IMAGE_TAG .
      docker push $ECR_PUBLIC_REGISTRY/$REGISTRY_ALIAS/$REPOSITORY:$IMAGE_TAG

```

## Inputs

| Name | Required | Default | Description |
|------|----------|---------|-------------|
| `aws-region` | no | `us-east-1` | AWS region for ECR |
| `login-public-ecr` | no | `false` | Set to `true` to also log into ECR Public |


## Important security note: 
1. For both private and public AWS ECR repositories, the repository (e.g., dev/image-name or stellar/image-name) must have the tag Repository: <stellar/github-repo-name>, where github-repo-name is the name of the repository executing the GitHub Action. This ensures only authorized workflows can push images.

2. Always include a `permissions` section with `id-token: write` and `contents: read` to enable OIDC authentication. These permissions are required for secure AWS authentication and access to repository contents.