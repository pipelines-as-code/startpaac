# Agent workflows

startpaac ships a portable skill for local Pipelines-as-Code development. Install it once at user level and an agent can find it from any PAC checkout, without the startpaac repository in its workspace.

## Install the executable and skill

Keep the startpaac checkout: the executable needs its sibling `lib` directory. From that checkout, symlink it onto PATH:

```sh
mkdir -p "$HOME/.local/bin"
ln -s "$PWD/startpaac" "$HOME/.local/bin/startpaac"
```

Make sure `~/.local/bin` is on PATH, then install the skill for your agent:

```sh
startpaac --install-skills agents  # Codex and others that use ~/.agents/skills
startpaac --install-skills claude  # Claude Code
startpaac --install-skills all     # both
```

The command links the skill directory from the current checkout, so updating the checkout updates the skill. If a copy, or a link to another checkout, is already installed, move it aside first. Skill installation needs no PAC config or cluster tools. Deployments need the [prerequisites](../README.md#prerequisites).

In a new agent session, try "set up a PAC dev environment" or "redeploy my watcher changes".

## Readiness checks

The skill checks readiness when you ask to set up, run, investigate, or redeploy local PAC; ordinary code editing does not trigger it. Try "check whether I have everything for local PAC development".

The agent checks startpaac and jq first, then the PAC checkout, configuration, tools, Docker access, Go toolchain, and the GitHub App credentials the requested action needs. It explains what is missing and rechecks after a fix. Creating a GitHub App or unlocking pass needs your interactive session. A missing Kind cluster is expected before deployment. Once prerequisites pass, the agent previews the setup and reports the next command, and deploys when you ask. Component-only redeployments use their own plans, verify the rollout, and need neither local GitHub App credentials nor a passing full-stack status.

## Preview, deploy, inspect

Agent commands reuse your configured PAC checkout and existing GitHub App credentials. They do not generate a sample configuration or open a browser. For a new configuration, see the [configuration reference](configuration.md).

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

`--up` installs Kind, Envoy Gateway, the registry, Tekton Pipelines, PAC, and the Dashboard. It ignores saved component preferences and leaves other installed components alone.

- It reuses a compatible `kind` cluster or creates one. An incompatible cluster is an error and is never deleted as a fallback.
- It reuses installed Envoy Gateway and registry Helm releases. Run `--install-gateway` to upgrade Envoy Gateway.
- Registry installation can restart containerd on a reused cluster.
- It leaves existing webhook forwarders alone in both output modes.

Agent commands use the Docker Kind provider. Select a Docker context with a local Unix socket; TCP and SSH endpoints are rejected, including through `DOCKER_HOST`.

The selected kubeconfig must contain only the local Kind cluster, its context, and its user. The default is `~/.kube/config.local`; `KUBECONFIG` may select another single file. Setup exports a missing kubeconfig but never overwrites one that points elsewhere. If Kind is absent and the kubeconfig already exists, pick an unused path, or inspect and remove the stale file yourself.

Relative paths for the kubeconfig, hooks, PAC checkout, and file-based credentials are resolved before startpaac changes into the PAC checkout.

`--plan` lists the source checkout, target, ordered steps, configured executable hooks, and destructive effects, and reports prerequisite failures without deploying. Hooks are trusted user code and can have further effects when execution is authorized.

`--doctor` checks tools, checkout, credentials, and cluster compatibility. Component-only redeployment and teardown have smaller prerequisite sets, checked by their plans. `--status` reports the core components, the registry endpoint, and the observed forwarding state, and fails when required components are missing, stale, or unavailable. A component-only deployment can succeed while a full status check reports other components missing.

## Machine interface

`--output json` works with `--describe`, `--doctor`, `--status`, `--up`, `--install-paac` / `-p`, `--deploy-component` / `-c`, and `--stop-kind`. `--plan` works with the four deployment and teardown actions. Other combinations fail before configuration or deployment. One action is allowed per invocation.

stdout holds one JSON object; progress goes to stderr. Its fields:

- `schema_version`: `1`.
- `ok`: whether the action or inspection succeeded.
- `action`: canonical action name, without `--`.
- `target`: host, cluster name, and kubeconfig path.
- `data`: action-specific capabilities, checks, plan, or readiness.
- `errors`: objects with `code`, `message`, and `next_step`.
- `warnings`: incomplete setup or effects worth reviewing.

Exit codes: `0` success, `1` failed checks or operations, `2` invalid arguments.

Help needs only Bash; agent interfaces need jq. Discovery and argument validation do not load user configuration. Other inspections load your existing shell configuration, but do not generate configuration, run hooks, export kubeconfigs, or change cluster resources.

`--non-interactive` supports the core workflows, and `--up` and JSON execution enable it. It disables prompts, browser launches, and implicit changes to webhook-forwarding services. Password-store access uses batch mode, so unavailable credentials are reported instead of triggering pinentry. Output excludes credential values and relay tokens. Credential updates read every value before applying the secret, so a failed read leaves the existing secret intact.

## GitHub delivery

Setup needs reusable GitHub App credentials and a relay URL. If they are missing, run `--setup-github-app` in an interactive terminal. To configure or start a persistent forwarder, run `--start-user-gosmee` separately. Non-interactive deployment leaves existing user services unchanged.

`--status` reports `forwarder: running` only when it sees a running user service; otherwise the state is `unverified`, because a foreground forwarder may be in use. `webhook_delivery` is always `unverified`: component readiness and a running forwarder do not prove end-to-end delivery. Verify with a real event before claiming the GitHub integration works.

Legacy flags, including `--ci`, keep their existing workflows; `-a`, `--kind`, and `--redeploy-kind` recreate Kind. Remote hosts, existing clusters, optional services, and second GitHub controllers are outside the local agent interface; see the [configuration reference](configuration.md).
