# startpaac

Set up [Pipelines-as-Code](https://pipelinesascode.com) on a local Kind cluster for development.

[![ShellCheck](https://github.com/chmouel/startpaac/actions/workflows/shellcheck.yml/badge.svg)](https://github.com/chmouel/startpaac/actions/workflows/shellcheck.yml)

## Use with an agent

Install the bundled [startpaac skill](skills/startpaac/SKILL.md) for Codex,
Claude Code, or another skill-capable agent, then ask it to set up a PAC dev
environment or redeploy a controller, watcher, or webhook change.

```sh
./startpaac --install-skills agents  # ~/.agents/skills
./startpaac --install-skills claude  # ~/.claude/skills
./startpaac --install-skills all     # both
```

The skill follows the checkout, so updating startpaac updates the skill too.

```sh
./startpaac --doctor --output json
./startpaac --up --plan --output json
./startpaac --up --non-interactive --output json
./startpaac --status --output json
```

`--up` reuses a compatible local Kind cluster and existing GitHub App credentials.
See [agent installation and CLI interfaces](docs/agents.md).

## Quick start

This is meant for local development only.

Create a config file:

```shell
mkdir -p $HOME/.config/startpaac
cat <<EOF > $HOME/.config/startpaac/config
TARGET_HOST=local
PAC_DIR=~/go/src/github.com/tektoncd/pipelines-as-code
PAC_E2E_CONFIG=~/.local/share/startpaac/e2e-config.yaml
EOF
```

The GitHub App values do not go in that file. They go in a separate YAML file
that [PAC_E2E_CONFIG](https://github.com/tektoncd/pipelines-as-code/tree/main/test#yaml-configuration-file points to, either a path or a `pass:<entry>` reference.
The first run creates an empty one for you.

If startpaac runs interactively and finds no credentials, it creates a GitHub
App for you. It asks whether the App belongs to your account or to an
organization, generates a webhook relay URL on
[hook.pipelinesascode.com](https://hook.pipelinesascode.com) (development only,
no security guarantees), saves the credentials in the `PAC_E2E_CONFIG` file,
then offers to start [gosmee](https://github.com/chmouel/gosmee) as a user
service (systemd on Linux, LaunchAgent on macOS) so webhooks reach your local
cluster.

After creating the app, install it on the repositories you want to use with PAC.

If you already have a GitHub App, reuse it. Put its values in that YAML file
and the automatic setup will leave you alone:

```shell
${EDITOR:-vi} ~/.local/share/startpaac/e2e-config.yaml
```

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

Those names come from the Pipelines-as-Code E2E config. See
[docs/configuration.md](docs/configuration.md#secrets-management) for all of
them.

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
| `-g, --install-forgejo` | Install Forgejo |
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
| `-h, --help` | Show help |

## Configuration

Minimal config in `~/.config/startpaac/config`:

```shell
TARGET_HOST=local
PAC_DIR=~/path/to/pipelines-as-code
PAC_E2E_CONFIG=~/.local/share/startpaac/e2e-config.yaml
```

`PAC_SECRET_FOLDER` no longer exists. startpaac reads the GitHub App values from
the YAML file in `PAC_E2E_CONFIG`, or from whatever you pass to `--e2e-config`.
If you only want to swap a few of them, use `--e2e-config-override`.

See [docs/configuration.md](docs/configuration.md) for the full reference (remote VM setup, secrets management, hooks, PostgreSQL, preferences).

## Prerequisites

docker, kind, helm, kubectl, jq, minica, yq (or python3 with PyYAML)

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
