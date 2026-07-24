# startpaac

Set up [Pipelines-as-Code](https://pipelinesascode.com) on a local Kind cluster for development.

[![ShellCheck](https://github.com/chmouel/startpaac/actions/workflows/shellcheck.yml/badge.svg)](https://github.com/chmouel/startpaac/actions/workflows/shellcheck.yml)

## Quick start

This is meant for local development only.

Create a config file:

```shell
mkdir -p $HOME/.config/startpaac
cat <<EOF > $HOME/.config/startpaac/config
TARGET_HOST=local
PAC_DIR=~/go/src/github.com/tektoncd/pipelines-as-code
PAC_SECRET_FOLDER=~/secrets
EOF
```

A GitHub App is created automatically: when `startpaac` runs interactively
and finds no credentials, it opens your browser on GitHub's App Manifest flow
(personal account or organization), generates a webhook relay URL on
[hook.pipelinesascode.com](https://hook.pipelinesascode.com) (development only,
no security guarantees), stores the credentials (in `pass` if configured,
otherwise in `~/.local/share/startpaac/secrets`), and offers to run
[gosmee](https://github.com/chmouel/gosmee) as a user service (systemd on
Linux, LaunchAgent on macOS) to forward webhooks to your local cluster.

After creating the app, install it on the repositories you want to use with PAC.

If you already have a GitHub App, it is better to reuse it instead of creating a
new one every time. Store your existing credentials and skip the automatic setup:

```shell
mkdir -p ~/secrets
for i in github-application-id github-private-key smee webhook.secret; do
  ${EDITOR:-vi} ~/secrets/$i
done
```

Run the interactive installer:

```shell
./startpaac
```

You can also create a GitHub App directly without running the full installer:

```shell
./startpaac --setup-github-app
```

## What gets installed

**Core** (always):
Kind cluster, Envoy Gateway, Docker registry, Tekton Pipelines

**Optional** (selected via menu):
PAC (built from local source with ko), Tekton Dashboard, Tekton Triggers, Tekton Chains, Forgejo, PostgreSQL, GitHub second controller

## Common usage

```shell
./startpaac              # interactive install (or uses saved preferences)
./startpaac -a           # install everything non-interactively
./startpaac -p           # redeploy PAC from source
./startpaac -c controller  # redeploy a single component (controller/watcher/webhook)
./startpaac --menu       # force the interactive menu
./startpaac --stop-kind  # tear down the cluster
```

Configure PAC on an existing cluster (e.g. OpenShift):

```shell
./startpaac --configure-pac-target $KUBECONFIG $TARGET_NAMESPACE $SECRET_FOLDER
```

## Options

| Flag | Description |
|------|-------------|
| `-a, --all` | Install everything |
| `-A, --all-but-kind` | Install everything but Kind |
| `-i, --menu, --interactive` | Force interactive component selection |
| `-R, --reset-preferences` | Reset saved component preferences |
| `-k, --kind` | (Re)install Kind |
| `-g, --install-forge` | Install Forgejo |
| `-c, --deploy-component` | Deploy a component (controller, watcher, webhook) |
| `-p, --install-paac` | Deploy and configure PAC |
| `-s, --sync-kubeconfig` | Sync kubeconfig from remote host |
| `-G, --start-user-gosmee` | Start gosmee locally |
| `-S, --github-second-ctrl` | Deploy second GitHub controller |
| `--setup-github-app` | Create a GitHub App (manifest flow) and store its credentials |
| `--install-gateway` | Install Envoy Gateway |
| `--install-dashboard` | Install Tekton Dashboard |
| `--install-tekton` | Install Tekton |
| `--install-triggers` | Install Tekton Triggers |
| `--install-chains` | Install Tekton Chains |
| `--redeploy-kind` | Redeploy Kind |
| `--scale-down` | Scale down a component |
| `--stop-kind` | Stop Kind |
| `--debug-image` | Use debug image for PAC controller |
| `--show-config` | Show PAC configuration |
| `--apply-non-root` | Apply non-root config to PAC controller |
| `-h, --help` | Show help |

## Configuration

Minimal config in `~/.config/startpaac/config`:

```shell
TARGET_HOST=local
PAC_DIR=~/path/to/pipelines-as-code
PAC_SECRET_FOLDER=~/secrets
```

See [docs/configuration.md](docs/configuration.md) for the full reference (remote VM setup, secrets management, hooks, PostgreSQL, preferences).

## Prerequisites

docker, kind, helm, kubectl, jq, minica

Optional:

- [ko](https://ko.build/) - only needed when deploying PAC from source (`-p`, `-a`, `-c` flags)
- [gum](https://github.com/charmbracelet/gum) - enhances interactive menus (falls back to plain bash prompts)
- [pass](https://www.passwordstore.org/) - for secrets management

macOS users: install [coreutils](https://formulae.brew.sh/formula/coreutils) and [gnu-sed](https://formulae.brew.sh/formula/gnu-sed) from Homebrew.

## More

- [Configuration reference](docs/configuration.md)
- [Architecture](docs/architecture.md)
- [ZSH completion](misc/_startpaac)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
