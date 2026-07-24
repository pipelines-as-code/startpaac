# Configuration reference

## Config file

Located at `~/.config/startpaac/config` (override with `STARTPAC_CONFIG_FILE` env var).

### Gosmee delivery diagnostics

When startpaac starts Gosmee, it enables structured debug logging and retries
target delivery failures. Override these settings in the configuration file or
environment when needed:

```bash
GOSMEE_LOG_LEVEL=debug
GOSMEE_TARGET_TIMEOUT=5
GOSMEE_TARGET_RETRIES=5
```

The timeout is in seconds. Gosmee writes JSON records containing delivery and
stream identifiers, making failures searchable with `jq` in the pod logs or
the `/tmp/save` replay directory.

```bash
# Path to your pipelines-as-code checkout (auto-detected if unset)
PAC_DIR=~/go/src/github.com/tektoncd/pipelines-as-code

# Secrets via password-store (pass)
# Folder structure: github-application-id, github-private-key, smee, webhook.secret
PAC_PASS_SECRET_FOLDER=github/apps/my-app

# Or secrets as plain text files (same structure as above)
PAC_SECRET_FOLDER=~/path/to/secrets

# Where Kind runs: "local" or a remote hostname
TARGET_HOST=local

# Extra flags for ko
KO_EXTRA_FLAGS=() # e.g. --platform linux/arm64 --insecure-registry

## Remote VM setup (not needed when TARGET_HOST=local)
# Set up a wildcard DNS *.lan.mydomain.com pointing to your TARGET_HOST.
# Tip: https://nextdns.io lets you create wildcard DNS for local networks.
DOMAIN_NAME=lan.mydomain.com
PAC=paac.${DOMAIN_NAME}
REGISTRY=registry.${DOMAIN_NAME}
FORGE_HOST=gitea.${DOMAIN_NAME}
DASHBOARD=dashboard.${DOMAIN_NAME}
TARGET_BIND_IP=192.168.1.5          # comma-separated for multiple IPs
```

## Secrets management

Secrets are the GitHub App credentials needed by PAC. You need four files:

- `github-application-id` -- your GitHub App ID
- `github-private-key` -- the app's private key
- `smee` -- your smee.io or hook.pipelinesascode.com webhook URL
- `webhook.secret` -- the shared webhook secret

### Using pass

Set `PAC_PASS_SECRET_FOLDER` in your config to the pass folder path:

```
github/apps/my-app
├── github-application-id
├── github-private-key
├── smee
└── webhook.secret
```

### Using plain text files

Set `PAC_SECRET_FOLDER` to a directory with the same structure, files in plain text.

If both backends are configured, set `PAC_SECRET_STORAGE` to `pass` or `folder`
to select which one startpaac uses. The guided GitHub App setup saves this
selection automatically.

### Automatic GitHub App creation

If no usable credentials are found (files missing or empty), interactive runs
offer to create the GitHub App for you, or run it explicitly:

```shell
./startpaac --setup-github-app
```

The guided flow:

1. Asks whether to create the app under your personal account or an organization.
2. Generates a webhook relay URL from <https://hook.pipelinesascode.com>
   (development relay only — no support or security guarantees).
3. Opens your browser on GitHub's [App Manifest flow](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest);
   a small local Python server receives the redirect and exchanges the
   temporary code for the app credentials.
4. Stores the credentials in your configured `pass` folder, or as plain files
   in `~/.local/share/startpaac/secrets` (persisted as `PAC_SECRET_FOLDER` in
   your config).
5. Shows the app installation URL — install the app on the repositories you
   want to use with PAC.
6. Offers to run gosmee as a persistent user service to forward webhooks.

### Gosmee webhook forwarding service

GitHub cannot reach a local Kind cluster directly, so a
[gosmee](https://github.com/chmouel/gosmee) client forwards the relay URL to
your PAC controller. startpaac offers to manage it as:

- **Linux**: a systemd user unit `~/.config/systemd/user/startpaac-gosmee.service`
- **macOS**: a LaunchAgent `~/Library/LaunchAgents/com.startpaac.gosmee.plist`
  (logs in `~/Library/Logs/startpaac-gosmee.log`; requires a logged-in GUI session)

Only files containing the `Managed by startpaac` marker are ever updated;
a pre-existing unit or plist of your own is left alone (a legacy
`gosmee.service` systemd unit is simply restarted). If you decline or the
platform is unsupported, the exact `gosmee client` command to run manually is
printed instead.

### Second GitHub controller

Set `PAC_PASS_SECOND_FOLDER` (same structure as above) and use `--github-second-ctrl` / `--second-secret=SECRET`.

## PostgreSQL

Customize the connection in `lib/postgresql/values.yaml`:

```yaml
global:
  postgresql:
    auth:
      username: "myuser"
      password: "mypassword"
      database: "mydatabase"
```

Default credentials are weak and for local dev only.

## Preferences

Component selections are saved to `~/.config/startpaac/preferences.json` when you choose to save them. On subsequent runs, saved preferences are used automatically.

```shell
./startpaac --menu              # force the menu even with saved preferences
./startpaac --reset-preferences # clear saved preferences
```

## Configure PAC on an existing cluster

If you have PAC already installed (e.g. via the OpenShift operator):

```shell
./startpaac --configure-pac-target $KUBECONFIG $TARGET_NAMESPACE $DIRECTORY_OR_PASS_FOLDER
```

- `$KUBECONFIG` -- kubeconfig for the cluster
- `$TARGET_NAMESPACE` -- namespace where PAC is installed (e.g. `openshift-pipelines`)
- `$DIRECTORY_OR_PASS_FOLDER` -- secret folder (plain text dir or pass folder)

## Hooks

Hooks are executable scripts that run at defined points in the installation flow.

### Setup

Place hooks in `~/.config/startpaac/hooks/` (override with `HOOKS_DIR` env var).

### Naming

Files are named `pre-<component>` or `post-<component>`:

```
pre-install-tekton    -- runs before Tekton install
post-configure-pac    -- runs after PAC configuration
```

Available hook points: `all`, `sync-kubeconfig`, `install-gateway`, `install-registry`, `install-tekton`, `install-triggers`, `install-chains`, `install-dashboard`, `install-pac`, `configure-pac`, `configure-pac-custom-certs`, `patch-pac-service-nodeport`, `install-forgejo`, `setup-forgejo-sample`, `install-postgresql`, `install-custom-objects`, `install-github-second-ctrl`.

Hooks run in the full install flows and in matching direct component commands such as `--install-tekton`, `--install-paac`, `--install-forgejo`, and `--configure-pac`.

### Format

A hook can be a single executable file or a directory of executables (run in sorted order):

```
~/.config/startpaac/hooks/post-install-tekton           # single file
~/.config/startpaac/hooks/post-install-tekton/01-extras  # directory of scripts
```

### Environment

Hooks inherit the current environment. startpaac also exports its scalar runtime/config values for hooks (`KUBECONFIG`, `TARGET_HOST`, `PAC_DIR`, etc.). `STARTPAC_HOOK_NAME` is exported with the current hook name; `STARTPAAC_HOOK_NAME` is also available as an alias.

A non-zero exit from any hook aborts the run.

### Example

```bash
mkdir -p ~/.config/startpaac/hooks
cat > ~/.config/startpaac/hooks/post-install-tekton <<'EOF'
#!/bin/bash
echo "Tekton installed -- applying custom resources"
kubectl apply -f ~/my-extra-resources/
EOF
chmod +x ~/.config/startpaac/hooks/post-install-tekton
```
