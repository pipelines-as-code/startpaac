# startpaac

Set up [Pipelines-as-Code](https://pipelinesascode.com) on a local Kind cluster for development.

[![ShellCheck](https://github.com/chmouel/startpaac/actions/workflows/shellcheck.yml/badge.svg)](https://github.com/chmouel/startpaac/actions/workflows/shellcheck.yml)

startpaac is for local development only.

## Prerequisites

Required: docker, kind, helm, kubectl, jq, minica, and yq (or python3 with PyYAML).

Optional:

- [ko](https://ko.build/): needed to build PAC from source (`-p`, `-a`, `-c`).
- [gum](https://github.com/charmbracelet/gum): nicer interactive menus. Without it, startpaac falls back to plain Bash prompts.
- [pass](https://www.passwordstore.org/): store the GitHub App credentials outside a plaintext file.

On macOS, install [coreutils](https://formulae.brew.sh/formula/coreutils) and [gnu-sed](https://formulae.brew.sh/formula/gnu-sed) from Homebrew.

## Quick start

Create the config file:

```shell
mkdir -p $HOME/.config/startpaac
cat <<EOF > $HOME/.config/startpaac/config
TARGET_HOST=local
PAC_DIR=~/go/src/github.com/tektoncd/pipelines-as-code
PAC_E2E_CONFIG=~/.local/share/startpaac/e2e-config.yaml
EOF
```

GitHub App credentials do not go in that file. They live in a separate YAML file
(the [PAC E2E config](https://github.com/tektoncd/pipelines-as-code/tree/main/test#yaml-configuration-file))
that `PAC_E2E_CONFIG` points to, as a path or a `pass:<entry>` reference.

If an interactive run finds no credentials, startpaac offers to create a GitHub
App: it asks whether the App belongs to you or an organization, gets a webhook
relay URL from [hook.pipelinesascode.com](https://hook.pipelinesascode.com)
(development only, no security guarantees), saves the credentials to the
`PAC_E2E_CONFIG` file, and offers to run [gosmee](https://github.com/chmouel/gosmee)
as a user service (systemd on Linux, LaunchAgent on macOS). Install the new App
on the repositories you want to use. To run only this step, use
`./startpaac --setup-github-app`.

To reuse an existing App, put its values in the YAML file instead:

```yaml
common:
  webhook_secret: "..."

github:
  application_id: "123456"
  private_key: |
    -----BEGIN RSA PRIVATE KEY-----
    ...
  smee_url: "https://hook.pipelinesascode.com/..."
```

Then run the installer:

```shell
./startpaac
```

## What gets installed

Core: Kind cluster, Envoy Gateway, Docker registry, Tekton Pipelines.

Optional, chosen in the menu: PAC (built from local source with ko), Tekton
Dashboard, Triggers and Chains, Forgejo, PostgreSQL, and a second GitHub
controller. Kueue is off by default; select it in the menu or run
`--install-kueue`.

## Common commands

```shell
./startpaac                  # interactive install, or saved preferences
./startpaac -a               # recreate Kind and install everything non-interactively
./startpaac -p               # rebuild and redeploy PAC from source
./startpaac -c controller    # redeploy one component: controller, watcher, or webhook
./startpaac --menu           # force the component menu
./startpaac --stop-kind      # delete the cluster
./startpaac --configure-pac-target $KUBECONFIG $TARGET_NAMESPACE $E2E_CONFIG_YAML
                             # configure PAC on an existing cluster (e.g. OpenShift)
```

## Options

Agent workflows:

| Flag | Description |
|------|-------------|
| `--install-skills TARGET` | Link the bundled skill for `agents`, `claude`, or `all` |
| `--up` | Create or reuse a local PAC development cluster |
| `--describe` | Describe supported agent interfaces (needs jq) |
| `--doctor` | Check local setup prerequisites |
| `--status` | Inspect local component readiness |
| `--plan` | Preview a core action without changing anything |
| `--non-interactive` | Disable prompts and implicit service changes |
| `--output text\|json` | Select output format (JSON needs jq) |

Deployment actions:

| Flag | Description |
|------|-------------|
| `-a, --all` | Recreate Kind and install selected components |
| `-A, --all-but-kind` | Install without recreating Kind |
| `-p, --install-paac` | Build, deploy, and configure PAC |
| `-c, --deploy-component NAME` | Deploy `controller`, `watcher`, or `webhook` |
| `-k, --kind` | Recreate Kind |
| `--redeploy-kind` | Recreate Kind |
| `--stop-kind` | Delete Kind and its kubeconfig |
| `--install-gateway` | Install Envoy Gateway |
| `--install-registry` | Install the registry |
| `-t, --install-tekton` | Install Tekton Pipelines |
| `--install-triggers` | Install Tekton Triggers |
| `--install-chains` | Install Tekton Chains |
| `--install-dashboard` | Install Tekton Dashboard |
| `-g, --install-forgejo` | Install Forgejo and sample repositories |
| `--setup-forgejo-sample` | Create sample Forgejo repositories |
| `--install-postgresql` | Install PostgreSQL |
| `--install-kueue` | Install Kueue to queue PipelineRuns one at a time |
| `--all-to-tekton` | Recreate Kind and install through Tekton |
| `-F, --all-but-forge` | Install without Kind or Forgejo |
| `-H, --all-github-second-no-forgejo` | Recreate with a second GitHub controller |
| `-S, --github-second-ctrl` | Deploy the second GitHub controller |
| `--configure-pac` | Configure PAC |
| `--configure-pac-target KUBECONFIG NAMESPACE E2E_CONFIG` | Configure PAC on an existing cluster |
| `--debug-image` | Deploy PAC with the debug image |
| `-s, --sync-kubeconfig` | Sync kubeconfig from the remote target |
| `-G, --start-user-gosmee` | Start the user webhook forwarder |
| `--setup-github-app` | Create a GitHub App interactively |
| `--show-config` | Show configuration |

Other options:

| Flag | Description |
|------|-------------|
| `--e2e-config FILE` | Read PAC secrets and settings from an E2E YAML config |
| `--e2e-config-override FILE` | Overlay a YAML config on `PAC_E2E_CONFIG` (file or `pass:<entry>`) |
| `-O, --scale-down NAME` | Scale down a component after deployment |
| `-i, --menu, --interactive` | Force the component menu |
| `-R, --reset-preferences` | Remove saved component preferences |
| `--ci` | Legacy non-interactive installation mode |
| `-h, --help` | Show help |

## Configuration

startpaac reads `~/.config/startpaac/config` and takes GitHub App values from
the E2E YAML file, or from `--e2e-config`. To swap a few values only, use
`--e2e-config-override`. See [docs/configuration.md](docs/configuration.md)
for every variable, remote VM setup, hooks, and more.

## Working with an agent

Put the executable on your PATH, then link the bundled skill for your agent:

```sh
startpaac --install-skills all   # agents, claude, or all
startpaac --up --plan --output json
```

See [docs/agents.md](docs/agents.md) for installation and the JSON interface.

How the pieces fit together is in [docs/architecture.md](docs/architecture.md);
zsh completion ships as [misc/_startpaac](misc/_startpaac).

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
