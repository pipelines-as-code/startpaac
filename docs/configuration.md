# Configuration reference

## Config file

startpaac reads `~/.config/startpaac/config` (override with `STARTPAC_CONFIG_FILE`). It is sourced as shell. Environment variables take precedence over values in the file.

| Variable | Description |
|----------|-------------|
| `PAC_DIR` | Pipelines-as-Code checkout. Auto-detected when you run startpaac from a PAC checkout |
| `PAC_E2E_CONFIG` | E2E YAML with the GitHub App credentials. Defaults to `~/.local/share/startpaac/e2e-config.yaml` |
| `TARGET_HOST` | `local` or the hostname of a remote VM |
| `KO_EXTRA_FLAGS` | Extra ko flags, for example `(--platform linux/arm64 --insecure-registry)`. Forced to `(--insecure-registry)` when `TARGET_HOST=local` |
| `GOSMEE_LOG_LEVEL` | gosmee log level. Default `debug` |
| `GOSMEE_TARGET_TIMEOUT` | Seconds before a delivery to the target times out. Default `5` |
| `GOSMEE_TARGET_RETRIES` | Delivery retries. Default `5` |
| `HOOKS_DIR` | Hooks directory. Default `~/.config/startpaac/hooks` |
| `CACHE_MAX_AGE_DAYS` | Age after which downloaded manifests are fetched again. Default `21` |

Minimal file:

```shell
TARGET_HOST=local
PAC_DIR=~/go/src/github.com/tektoncd/pipelines-as-code
PAC_E2E_CONFIG=~/.local/share/startpaac/e2e-config.yaml
```

## Secrets management

GitHub App credentials come from the YAML format used by the Pipelines-as-Code E2E tests (`test/e2e-config.yaml.example` in the PAC repository). Point to it with `PAC_E2E_CONFIG` (environment or config file) or `--e2e-config`. The value is a file path or a `pass:<entry>` reference, which avoids a plaintext file on disk:

```shell
PAC_E2E_CONFIG=pass:pac/e2e-config ./startpaac --up
./startpaac --e2e-config pass:pac/e2e-config --up
```

Reading the YAML needs `yq` or `python3` with PyYAML. startpaac reads:

- Primary controller: `github.application_id`, `github.private_key`, `common.webhook_secret`, `github.smee_url`.
- Second controller: `github_enterprise.application_id`, `.private_key`, `.webhook_secret`, `.smee_url`, and `.api_url`. The API URL is reduced to a bare hostname for `PAC_GITHUB_SECOND_HOSTNAME` when that is unset.
- Forgejo sample webhook: `common.webhook_secret`, used for `PAC_WEBHOOK_SECRET` when unset.

Explicit environment variables win over YAML values. In `--ci` mode (legacy actions such as `-a`, not `--up`), the second controller is enabled automatically when `github_enterprise` credentials are present and `INSTALL_GITHUB_SECOND_CTRL` is unset.

To replace only some fields, for example to test another GitHub App, overlay a second YAML file (a path or `pass:<entry>`) with `PAC_E2E_CONFIG_OVERRIDE` or `--e2e-config-override`:

```shell
./startpaac --e2e-config-override pass:pac/my-other-app -p
```

Non-empty scalar fields in the overlay win; omitted or empty fields fall back to the base config. Precedence: `--e2e-config-override`, then `PAC_E2E_CONFIG_OVERRIDE`, then the base config.

## Automatic GitHub App creation

When an interactive run finds no usable credentials (file missing or empty), it offers to create the GitHub App. Run the flow directly with:

```shell
./startpaac --setup-github-app
```

Declining the offer writes `PAC_SKIP_GITHUB_APP_PROMPT=true` to your config so later runs do not ask. Remove it, or run `--setup-github-app`, to set up later.

The flow:

1. Asks whether the App belongs to your account or an organization.
2. Gets a webhook relay URL from <https://hook.pipelinesascode.com> (development only, no support or security guarantees).
3. Opens your browser on GitHub's [App Manifest flow](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest). A local Python server (`lib/github_app_create.py`) receives the redirect and exchanges the temporary code for credentials.
4. Writes the credentials to `PAC_E2E_CONFIG` with mode `0600`, and saves that path in your config.
5. Prints the installation URL. Install the App on the repositories you want to use.
6. Offers to run gosmee as a persistent user service.

## Webhook forwarding

GitHub cannot reach a local Kind cluster, so a [gosmee](https://github.com/chmouel/gosmee) client forwards the relay URL to the PAC controller. startpaac offers to manage it as:

- Linux: the systemd user unit `~/.config/systemd/user/startpaac-gosmee.service`.
- macOS: the LaunchAgent `~/Library/LaunchAgents/com.startpaac.gosmee.plist`, logging to `~/Library/Logs/startpaac-gosmee.log`. It needs a logged-in GUI session.

startpaac only updates files containing the `Managed by startpaac` marker. A unit or plist of your own is left alone, and a legacy `gosmee.service` unit is only restarted. If you decline, or the platform is unsupported, startpaac prints the `gosmee client` command to run by hand. `--start-user-gosmee` starts the forwarder on its own.

gosmee runs with JSON output, debug logging, and retries on delivery failures, controlled by `GOSMEE_LOG_LEVEL`, `GOSMEE_TARGET_TIMEOUT`, and `GOSMEE_TARGET_RETRIES`. Records carry delivery and stream identifiers, so failures can be searched with `jq`. gosmee saves payloads for replay in `/tmp/replay` (user service) or `/tmp/save` (in-cluster pod).

## Remote VM setup

Skip this when `TARGET_HOST=local`. For a remote host, point a wildcard DNS record such as `*.lan.mydomain.com` at it ([nextdns.io](https://nextdns.io) can do this for local networks) and set:

```shell
TARGET_HOST=vm.lan
DOMAIN_NAME=lan.mydomain.com
PAC=paac.${DOMAIN_NAME}
REGISTRY=registry.${DOMAIN_NAME}
FORGE_HOST=gitea.${DOMAIN_NAME}
DASHBOARD=dashboard.${DOMAIN_NAME}
TARGET_BIND_IP=192.168.1.5   # comma-separated for multiple IPs
```

startpaac needs SSH access to the host. `-s, --sync-kubeconfig` fetches its kubeconfig.

## Second GitHub controller

Add `github_enterprise` credentials to the E2E YAML and use `--github-second-ctrl`. `PAC_GITHUB_SECOND_HOSTNAME` is derived from `github_enterprise.api_url`, or set it to a bare hostname such as `ghe.example.com`. startpaac adds the hostname to the controller's trusted provider list so repository webhooks authenticate before a GitHub App request has arrived.

## Kueue

Kueue is off by default. Select it in the component menu (shown on the first run and with `--menu`), or install it on a cluster that already has Tekton Pipelines:

```shell
./startpaac --install-kueue
```

This installs cert-manager v1.19.2, Kueue v0.16.6, and [tekton-kueue](https://github.com/tektoncd/tekton-kueue) v0.4.3, then creates a `startpaac-pipelines` ClusterQueue that admits one PipelineRun at a time. New PipelineRuns start as `PipelineRunPending` and run in order.

Only namespaces in `KUEUE_NAMESPACES` (space separated, default `default`) are queued. startpaac labels them `startpaac.dev/kueue=enabled` and creates a `pipelines-queue` LocalQueue in each. Other namespaces, including those PAC E2E tests create, are left alone. After editing the list, run `--install-kueue` again. Dropped namespaces run their PipelineRuns immediately.

```shell
KUEUE_NAMESPACES="default sample"
```

## PostgreSQL

Edit the connection settings in `lib/postgresql/values.yaml`:

```yaml
global:
  postgresql:
    auth:
      username: "myuser"
      password: "mypassword"
      database: "mydatabase"
```

The default credentials are weak and meant for local development.

## Preferences

Component selections are saved to `~/.config/startpaac/preferences.json` when you choose to save them, and reused on later runs. `--menu` forces the menu; `--reset-preferences` clears the file.

## Existing cluster

To configure PAC on a cluster where it is already installed (for example through the OpenShift operator):

```shell
./startpaac --configure-pac-target $KUBECONFIG $TARGET_NAMESPACE $E2E_CONFIG_YAML
```

The arguments are the cluster kubeconfig, the namespace where PAC runs (such as `openshift-pipelines`), and the path to a PAC E2E YAML config.

## Hooks

Hooks are executables that run before or after a step. Put them in `~/.config/startpaac/hooks/` (or `HOOKS_DIR`) and name them `pre-<point>` or `post-<point>`, for example `pre-install-tekton` or `post-configure-pac`.

Hook points: `all`, `stop-kind`, `sync-kubeconfig`, `install-gateway`, `install-registry`, `install-tekton`, `install-triggers`, `install-chains`, `install-dashboard`, `install-kueue`, `install-pac`, `configure-pac`, `configure-pac-custom-certs`, `patch-pac-service-nodeport`, `install-forgejo`, `setup-forgejo-sample`, `install-postgresql`, `install-custom-objects`, `install-github-second-ctrl`.

Hooks run in the full install flows and in the matching direct commands such as `--install-tekton`, `--install-paac`, `--install-forgejo`, and `--configure-pac`. A hook is one executable file or a directory of executables run in sorted order:

```text
~/.config/startpaac/hooks/post-install-tekton            # single file
~/.config/startpaac/hooks/post-install-tekton/01-extras  # directory
```

Hooks inherit the environment. startpaac also exports its scalar config values (`KUBECONFIG`, `TARGET_HOST`, `PAC_DIR`, and others) and sets `STARTPAC_HOOK_NAME` to the current hook (`STARTPAAC_HOOK_NAME` is an alias). A non-zero exit aborts the run.

```bash
mkdir -p ~/.config/startpaac/hooks
cat > ~/.config/startpaac/hooks/post-install-tekton <<'EOF'
#!/bin/bash
kubectl apply -f ~/my-extra-resources/
EOF
chmod +x ~/.config/startpaac/hooks/post-install-tekton
```
