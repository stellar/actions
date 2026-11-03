services = {
  "account-viewer" = {
    name         = "Account Viewer"
    github_repos = ["stellar/account-viewer-v2"]
    owning_team  = "wallet-eng"
    urls         = ["https://accountviewer.stellar.org"]
  }

  "hubspot-(crm)" = {
    name         = "Hubspot (crm)"
    github_repos = []
    owning_team  = "marketing"
  }

  "freighter" = {
    name         = "Freighter"
    github_repos = ["stellar/freighter", "stellar/freighter-backend"]
    owning_team  = "wallet-eng"
    playbook     = "https://example.invalid/playbooks/freighter"
  }

  "orphan-tool" = {
    name         = "Orphan Tool"
    github_repos = ["stellar/orphan-tool"]
  }
}
