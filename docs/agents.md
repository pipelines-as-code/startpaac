# Agent workflows

startpaac includes a portable skill for local Pipelines-as-Code development.
Install it once at user level so an agent can discover it from a PAC checkout,
without needing the startpaac repository in its current workspace.

## Install the executable and skill

Keep the startpaac checkout: the executable needs its sibling `lib` directory.
From that checkout, put a symlink on PATH:

```sh
startpaac_repo="$PWD"
mkdir -p "$HOME/.local/bin"
ln -s "$startpaac_repo/startpaac" "$HOME/.local/bin/startpaac"
```

Ensure `~/.local/bin` is on PATH. Install the skill for the agent you use:

```sh
startpaac --install-skills agents  # Codex and other agents that use ~/.agents/skills
startpaac --install-skills claude  # Claude Code
startpaac --install-skills all     # both
```

The command links the skill directory from the current startpaac checkout.
When you update that checkout, the links already point to the updated skill.
If a copy or a link to another checkout is already installed, move it aside
before switching. Skill installation needs no PAC config or cluster tools.

For deployments, install the [prerequisites](../README.md#prerequisites).
In a new agent session, try “set up a PAC dev environment” or “redeploy my
watcher changes.”

## Newcomer readiness checks

Ask “check whether I have everything for local PAC development” or “help me
prepare my first PAC environment.” The skill checks readiness when you ask to
set up, run, investigate, or redeploy local PAC. Ordinary code editing does not
trigger onboarding.

The agent checks startpaac and jq before CLI discovery, then checks the PAC
checkout, configuration, tools, Docker access, Go toolchain, and GitHub App
credentials needed for the requested action. It explains missing requirements
and rechecks them after a fix. Setup changes follow the scope of your request.
Creating a GitHub App or unlocking pass requires your interactive session.

An absent Kind cluster is expected before deployment. Once prerequisites pass,
the agent previews the setup and reports the next command; deployment runs
when you request it. Component-only redeployments use their own plans and
verify the requested rollout. They do not require local GitHub App credentials
or a passing full-stack status check.

## Preview, deploy, inspect

Reuse your configured PAC checkout and existing GitHub App credentials. For a
new configuration, follow the [configuration reference](configuration.md).
Agent commands do not generate a sample configuration or open a browser.

```sh
startpaac --describe --output json
startpaac --doctor --output json
startpaac --up --plan --output json
startpaac --up --non-interactive --output json
startpaac --status --output json

startpaac -c watcher --plan --output json
startpaac -c watcher --non-interactive --output json
startpaac -p --non-interactive --output json

# Explicit deletion
startpaac --stop-kind --plan --output json
startpaac --stop-kind --non-interactive --output json
```

`--up` installs Kind, Envoy Gateway, the registry, Tekton Pipelines, PAC, and
Dashboard. It ignores saved component preferences and leaves other installed
components alone. It reuses a compatible `kind` cluster or creates one when
absent. An incompatible cluster produces an error; it is never deleted as a
fallback. Registry installation can restart containerd on a reused cluster.
`--up` leaves existing webhook forwarders alone in both output modes.

Agent commands use the Docker Kind provider. Select a Docker context with a
local Unix socket. TCP and SSH endpoints are rejected, including those set
through `DOCKER_HOST`.

The selected kubeconfig must contain only the local Kind cluster and its
context and user. The default is
`~/.kube/config.local`; `KUBECONFIG` may select another single file. Setup can
export a missing kubeconfig, but does not overwrite one pointing elsewhere.
If Kind is absent and the selected kubeconfig already exists, choose an unused
path or inspect and remove the stale file yourself before setup.

Agent commands resolve relative paths for the kubeconfig, hooks, PAC checkout,
and file-based credentials before switching to the PAC checkout.
`--plan` lists the source checkout, target, ordered steps, configured executable
hooks, and destructive effects. It also reports prerequisite failures without
performing deployment operations. Hooks are trusted user code and can have
additional effects when execution is authorized.

`--doctor` collects setup checks, including tools, checkout, credentials, and
cluster compatibility. Component-only redeployment and teardown have smaller
prerequisite sets; their plans check those requirements. `--status` reports the
core development components, registry endpoint, and observed forwarding state.
It returns a failure when required components are missing, stale, or unavailable.
A component-only deployment can succeed even if a full-environment status check
reports other missing components.

## Machine interface

`--output json` supports `--describe`, `--doctor`, `--status`, `--up`,
`--install-paac` / `-p`, `--deploy-component` / `-c`, and `--stop-kind`.
`--plan` applies to the four deployment/teardown actions. Other combinations
fail before configuration or deployment. Arguments and modifiers are processed
before an action runs; one action is allowed per invocation.

stdout contains one JSON object. Progress goes to stderr. The envelope contains:

- `schema_version`: `1`.
- `ok`: whether the requested action or inspection succeeded.
- `action`: the canonical action name, without `--`.
- `target`: host, cluster name, and kubeconfig path.
- `data`: action-specific capability descriptions, checks, plan, or readiness.
- `errors`: objects with `code`, `message`, and `next_step`.
- `warnings`: messages about incomplete setup or effects worth reviewing.

Exit codes are `0` for success, `1` for failed checks/operations, and `2` for
invalid arguments. Help needs only Bash; agent interfaces require jq. Discovery
and argument validation do not load user configuration. Other inspections load
the existing trusted shell configuration, but do not generate configuration,
execute hooks, export kubeconfigs, or change cluster resources.

`--non-interactive` supports the core workflows. `--up` and JSON execution
also enable it.
It disables prompts, browser launches, and implicit changes to webhook-forwarding
services. Password-store access uses batch mode; unavailable credentials are
reported rather than triggering pinentry. Output excludes credential values and
relay tokens. Credential updates read all values before applying the secret;
failed reads leave the existing secret intact.

## GitHub delivery and advanced workflows

Setup requires reusable GitHub App credentials and a relay URL. If necessary,
run `--setup-github-app` separately in an interactive terminal. To configure or
start a persistent webhook forwarder, run `--start-user-gosmee` separately.
Noninteractive deployment leaves existing user services unchanged.

`--status` reports `forwarder: running` only when it observes a running user
service; otherwise the state is `unverified`, since a foreground forwarder may
be in use. `webhook_delivery` remains `unverified`: component readiness and a
running forwarder do not establish end-to-end delivery. Verify an actual event
before claiming GitHub integration works.

Legacy flags, including `--ci`, keep their existing workflows. In particular,
`-a`, `--kind`, and `--redeploy-kind` recreate Kind. Remote hosts, existing
clusters, optional services, and second GitHub controllers remain outside the
first local agent interface; see the [configuration reference](configuration.md).
