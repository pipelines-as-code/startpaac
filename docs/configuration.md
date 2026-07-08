# Configuration reference

## Config file

Located at `~/.config/startpaac/config` (override with `STARTPAC_CONFIG_FILE` env var).

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
