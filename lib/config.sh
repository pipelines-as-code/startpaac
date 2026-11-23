# shellcheck shell=bash disable=SC1090
CONFIG_FILE=${STARTPAC_CONFIG_FILE:-$HOME/.config/startpaac/config}
[[ ${CLI_MANAGED:-false} == true ]] || echo "Loading configuration from ${CONFIG_FILE}"

if [[ -e "${CONFIG_FILE}" ]]; then
  source "${CONFIG_FILE}"
elif [[ ${STARTPAAC_CREATE_CONFIG:-true} == true && -z ${PAC_DIR:-} ]]; then
  # Only require config file if PAC_DIR is not already set (e.g., in CI)
  mkdir -p "$(dirname "$CONFIG_FILE")"
  echo "Creating a sample $HOME/.config/startpaac/config file"
  cat <<EOF >"${CONFIG_FILE}"
# PAC_DIR is the path to the pipelines-as-code directory, it will try to detect
# it otherwise
#
# PAC_DIR=~/path/to/pipelines-as-code
#
# PAC_E2E_CONFIG is the path to a Pipelines-as-Code E2E YAML config file,
# or a password-store entry prefixed with pass: (e.g. pass:pac/e2e-config).
# startpaac reads GitHub App secrets, smee URLs, webhook secret, and
# second-controller GHE settings directly from it.
# PAC_E2E_CONFIG=pass:pac/e2e-config
# PAC_E2E_CONFIG=~/.local/share/startpaac/e2e-config.yaml
#
# Hostname of the GitHub Enterprise instance used by the second controller.
# Use only the hostname, without an https:// prefix, path, or port.
# PAC_GITHUB_SECOND_HOSTNAME=ghe.example.com
#
# Set to true to stop interactive runs from offering the guided GitHub App
# setup when credentials are missing (set automatically when you decline).
# PAC_SKIP_GITHUB_APP_PROMPT=true
#
# TARGET_HOST is your vm where kind will be running, you need to have kind working there
# set as local and unset all other variable to have it running on your local VM
# TARGET_HOST=my.vm.lan
#
# KO_EXTRA_FLAGS are the extra flags to pass to ko
#
# KO_EXTRA_FLAGS=() # extra ko flags for example --platform linux/arm64 --insecure-registry
#
# Install custom objects in the kind cluster after the cluster is created
# INSTALL_CUSTOM_OBJECT=~/path/to/dir/
#
# HOOKS_DIR is the directory where hook scripts are loaded from.
# Hooks are executable files named pre-<component> or post-<component>
# (e.g., post-install-tekton) that run automatically at defined points
# in the installation flow. A hook can be a single executable file or
# a directory of executable files (run in sorted order).
# HOOKS_DIR=~/.config/startpaac/hooks
## Hosts (not needed if TARGET_HOST is set to local)
#
# setup a wildcard dns *.lan.mydomain.com to go to your TARGET_HOST vm
# tips: if you don't want to install a dns server you can simply use
# https://nextdns.io to let you create wildcard dns for your local network.
#
# DOMAIN_NAME=lan.mydomain.com
# PAC=paac.\${DOMAIN_NAME}
# REGISTRY=registry.\${DOMAIN_NAME}
# FORGE_HOST=gitea.\${DOMAIN_NAME}
# DASHBOARD=dashboard.\${DASHBOARD}
#
# Example:
#
# TARGET_HOST=civuole.lan
# KO_EXTRA_FLAGS=(--insecure-registry --platform linux/arm64)
# DOMAIN_NAME=vm.lan
# PAC=paac.\${DOMAIN_NAME}
# REGISTRY=registry.\${DOMAIN_NAME}
# FORGE_HOST=gitea.\${DOMAIN_NAME}
# TARGET_BIND_IP=192.168.1.5
# TARGET_BIND_IP=192.168.1.5,10.0.0.5 # Comma-separated for multiple IPs
# DASHBOARD=dashboard.\${DOMAIN_NAME}
# PAC_DIR=\$GOPATH/src/github.com/tektoncd/pac/main
#
# USE_NODEPORT_WEBHOOK: Use NodePort instead of gosmee for local webhooks
# Defaults to true when TARGET_HOST=local
# USE_NODEPORT_WEBHOOK=true
#
# PAC_WEBHOOK_NODEPORT: The NodePort to use for the PAC webhook (default: 30080)
# PAC_WEBHOOK_NODEPORT=30080

# Gosmee delivery diagnostics. These values are passed to every Gosmee client
# started by startpaac, including the in-cluster deployment.
# GOSMEE_LOG_LEVEL=debug
# GOSMEE_TARGET_TIMEOUT=5
# GOSMEE_TARGET_RETRIES=5

# We are defaulting to a local install
PAC_DIR=~/go/src/github.com/tektoncd/pac/main
PAC_E2E_CONFIG=~/.local/share/startpaac/e2e-config.yaml
TARGET_HOST=local
EOF

  if [[ ! -f ~/.local/share/startpaac/e2e-config.yaml ]]; then
    (umask 077 && mkdir -p ~/.local/share/startpaac && cat <<'YAML' >~/.local/share/startpaac/e2e-config.yaml
common:
  webhook_secret: ""

github:
  application_id: ""
  private_key: ""
  smee_url: ""
YAML
    )
  fi

  if [[ ${SETUP_GITHUB_APP_ONLY:-false} == true ]]; then
    source "${CONFIG_FILE}"
  else
    echo "Adjust your PAC_DIR to where pipelines-as-code is checked out"
    echo "You can run './startpaac --setup-github-app' to create a GitHub App and fill ~/.local/share/startpaac/e2e-config.yaml automatically,"
    echo "or edit ~/.local/share/startpaac/e2e-config.yaml (or pass --e2e-config FILE)."
    exit 1
  fi
elif [[ ${CLI_MANAGED:-false} != true ]]; then
  echo "Config file not found, but PAC_DIR is set via environment - proceeding"
fi
