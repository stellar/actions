import * as core from '@actions/core';
import * as github from '@actions/github';

(async function() {
  try {
    const token = core.getInput('project_token');
    const project_name = core.getInput('project_name');
    const field_name = core.getInput('field_name');
    const context = github.context;

    const octokit = github.getOctokit(token);

    const eventName = context.eventName;
    const url = eventName === 'issues'
      ? context.payload.issue.html_url
      : context.payload.pull_request.html_url;
    console.debug(`url: ${url}`);
    const { resource } = await octokit.graphql<Record<string, any>>(`
      query {
        resource(url: "${url}") {
          ... on ${eventName.startsWith('issue') ? 'Issue' : 'PullRequest'} {
            id
            projectItems(first: 10) {
              nodes {
                id
                project {
                  id
                }
              }
            }
            projectsV2(query: "${project_name}", first: 1) {
              nodes {
                id
                field(name: "${field_name}") {
                  ... on ProjectV2SingleSelectField {
                    id
                    options {
                      id
                      name
                    }
                  }
                }
              }
            }
          }
        }
      }
    `);
    console.debug(`resource: ${JSON.stringify(resource)}`);

    if (!resource) {
      throw new Error(`Issue/PR not found: ${url}`);
    }

    const projects = resource.projectsV2.nodes;
    const projectItems = resource.projectItems.nodes?.filter((item: any) =>
      item.project.id === project.id
    );

    if (projects.length === 0 || projectItems.length === 0) {
      console.log(`Item ${url} is not a member of the project: ${project_name}`);
      return
    }
    if (projects.length > 1 || projectItems.length > 1) {
      console.log(`Item ${url} is a member of multiple projects named: ${project_name}`);
      return
    }

    const project = projects[0];
    const projectItem = projectItems[0];

    if (!project.field?.id) {
      console.log(`${field_name} field not found on this item`);
      return;
    }

    const sprints = project.field.options.filter((a: {name: string}) =>
      a.name.match(/sprint\s+(\d+)/i)
    ).sort((a: {name: string}, b: {name: string}) => {
      let amatch = Number(a.name.match(/sprint\s+(\d+)/i)[1]);
      let bmatch = Number(b.name.match(/sprint\s+(\d+)/i)[1]);
      if (amatch < bmatch) return -1;
      if (amatch > bmatch) return 1;
      return 0;
    }).reverse();
    if (sprints.length === 0) throw new Error("No last sprints found");

    const item_id = projectItem.id;
    const project_id = project.id;
    const field_id = project.field.id;
    const sprint_id = sprints[0].id;

    await octokit.graphql(`
      mutation {
        updateProjectV2ItemFieldValue(input: {
          projectId: "${project_id}",
          itemId: "${item_id}",
          fieldId: "${field_id}",
          value: {
            singleSelectOptionId: "${sprint_id}"
          }
        }) {
          clientMutationId
        }
      }
    `);
  } catch (error) {
		core.setFailed(error.message);
	}
})();
