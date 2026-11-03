# Service catalog pages

The publisher can build a page for every service and every team from the
incident.io service catalog in `stellar/terraform`, instead of from a folder of
Markdown. The pages are generated during each run, so changing the catalog is
all it takes.

```yaml
      - uses: stellar/actions/confluence-publish@main
        with:
          service-catalog: service-catalog/services.auto.tfvars
          root-page: "<root page id>"
```

## What it builds

- **Services**: one page per service, titled with its `name`, showing its
  owning team, repositories, links, playbook and catalog ID.
- **Teams**: one page per distinct `owning_team`, titled from the team's ID
  (`wallet-eng` becomes "Wallet Eng (Team)"), listing its services.

## How changes show up

| Change in the catalog | What happens to the pages |
| --- | --- |
| Add a service | Its page appears, and its team's page lists it |
| Rename a service | Same page, new title |
| Move a service to another team | Its page and both team pages update |
| Change a service's ID | Same page, as long as its name doesn't change in the same pull request |
| Remove a service | Its page is trashed, unless pages someone added sit under it |

## Adding to generated pages

Don't edit a generated page: the edit is overwritten the next time it changes.
Add pages under it instead, by hand or by publishing a service's repo there.
The catalog's runs never touch pages they didn't create, and a generated page
with pages under it is kept even if its service is removed.
