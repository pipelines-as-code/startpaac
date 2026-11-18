# Local setup and prerequisite failures

Use this reference for a first setup or when a check fails. Fix prerequisites
relevant to the requested action. Readiness checks can identify changes for the
user to make. Carry out setup changes when the request covers them and hand
interactive steps to the user when they require a browser or their credentials.

## CLI and dependencies

- If `startpaac` is missing or the executable lacks the agent interface, check
  for a trusted checkout in the workspace or at the path the user supplied.
  Use its executable directly if it has the sibling `lib/` directory and
  supports the requested action. For installation or updates, use the
  [agent guide](https://github.com/pipelines-as-code/startpaac/blob/main/docs/agents.md#install-the-executable-and-skill).
  Preserve existing symlinks and local changes. The skill directory alone
  does not include the executable.
- If `jq` or another required tool is missing, identify the OS and available
  package manager before suggesting an installation command. Use the
  [project prerequisites](https://github.com/pipelines-as-code/startpaac/blob/main/README.md#prerequisites)
  and upstream instructions for platform-specific requirements. Gum is
  optional. Pass is needed when using the password store.

## Full setup

Run `startpaac --doctor --output json`. Inspect `data.checks`, `errors`, and
`warnings` even when it exits nonzero. A missing Kind cluster is expected for
a first install. A passing doctor still needs a passing `--up --plan` before
execution.

Check Docker access with `docker info --format '{{.ServerVersion}}'`.
Distinguish a missing client, an unreachable daemon, and denied access. For a
source build, check `GOTOOLCHAIN=local go version` outside the PAC module and
compare it with the selected checkout's `go.mod` directives. The check keeps
Go from downloading a toolchain. Explain when ko needs a newer Go toolchain.

The PAC checkout must contain `go.mod` and
`config/{400-controller,500-watcher,600-webhook}.yaml`. If the intended
checkout is unavailable, use the [PAC repository](https://github.com/tektoncd/pipelines-as-code)
and a destination that preserves the user's existing worktrees. Choose the
checkout with the user if the request and workspace do not resolve it.

For a new config, the essential local settings are:

```sh
TARGET_HOST=local
PAC_DIR=/absolute/path/to/pipelines-as-code
PAC_SECRET_FOLDER=/absolute/path/to/app-secrets
```

For an existing config, identify the smallest relevant edit. Use
`PAC_PASS_SECRET_FOLDER` for a password-store entry. If both backends are
configured and the intended backend differs from the one startpaac selects,
use `PAC_SECRET_STORAGE=folder` or `PAC_SECRET_STORAGE=pass` to select it.

## Cluster and kubeconfig

| Result | Recovery |
| --- | --- |
| `cluster_missing` | For inspection, report that Kind is absent. For a redeploy, creation is a separate full-stack operation. |
| `cluster_unavailable` | Check Docker daemon access and the intended Docker context. Check before switching contexts because the name `kind` can exist on multiple Docker daemons. |
| `cluster_compatible` failed | Use a compatible local cluster. `-a`, `--kind`, and `--redeploy-kind` recreate Kind, so they require a request that covers replacement. |
| `kubeconfig_path` or `kubeconfig_mismatch` | Use a single dedicated kubeconfig that identifies the intended local Kind cluster. Preserve the shared or mismatched file. The local default is `~/.kube/config.local`. |
| `kubeconfig_exists` | Kind is absent and setup cannot use the selected path. Select an unused dedicated path. |
| `kubeconfig_missing` | If Kind already exists and the task covers provisioning its kubeconfig, export `kind` to the selected unused dedicated path. Full setup can also export it. For a redeploy, exporting the kubeconfig avoids running a full install just to restore access. |

Use `kind export kubeconfig --name kind --kubeconfig /absolute/unused/path` only
for the intended Docker daemon. If selecting a new path through `KUBECONFIG`,
check the plan's `target.kubeconfig` because shell config can override it.
If the Docker target is unclear, check `docker context show` and any
`DOCKER_HOST` or `DOCKER_CONTEXT` override before running a mutation. The CLI
target reports `local` and `kind`, which alone do not identify a Docker daemon.

## GitHub App credentials and delivery

Full setup and `-p` need `github-application-id`, `github-private-key`,
`webhook.secret`, and `smee`. Use the doctor or the action's plan to check
availability. A failure can mean missing entries or a locked password store.
Ask the user to unlock pass in their terminal. Keep keys, secrets, and relay
URLs out of tool output and chat.

If a new App is needed, have the user choose the account or organization and run
`startpaac --setup-github-app` in an interactive terminal. They must install the
App on the intended repositories. Starting a persistent forwarding service is
separate from the JSON workflow. Follow the
[configuration guide](https://github.com/pipelines-as-code/startpaac/blob/main/docs/configuration.md#automatic-github-app-creation)
for App creation and forwarding. After a fix, rerun the relevant check or plan
and continue any deployment the user already requested.
