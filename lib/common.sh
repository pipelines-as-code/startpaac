#!/usr/bin/env bash
# shellcheck disable=SC2059
CERT_DIR=${CERT_DIR:-/tmp/certs}

echo_color() {
  local echo=
  [[ ${1-""} == "-n" ]] && {
    echo="-n"
    shift
  }
  local color=$1
  local text=${2:-}
  case ${color} in
  red)
    echo ${echo} -e "\033[31m${text}\033[0m"
    ;;
  brightred)
    echo ${echo} -e "\033[1;31m${text}\033[0m"
    ;;
  green)
    echo ${echo} -e "\033[32m${text}\033[0m"
    ;;
  brightgreen)
    echo ${echo} -e "\033[1;32m${text}\033[0m"
    ;;
  blue)
    echo ${echo} -e "\033[34m${text}\033[0m"
    ;;
  brightblue)
    echo ${echo} -e "\033[1;34m${text}\033[0m"
    ;;
  brightwhite)
    echo ${echo} -e "\033[1;37m${text}\033[0m"
    ;;
  yellow)
    echo ${echo} -e "\033[33m${text}\033[0m"
    ;;
  brightyellow)
    echo ${echo} -e "\033[1;33m${text}\033[0m"
    ;;
  cyan)
    echo ${echo} -e "\033[36m${text}\033[0m"
    ;;
  bryightcyan)
    echo ${echo} -e "\033[1;36m${text}\033[0m"
    ;;
  purple)
    echo ${echo} -e "\033[35m${text}\033[0m"
    ;;
  brightcyan)
    echo ${echo} -e "\033[1;35m${text}\033[0m"
    ;;
  normal)
    echo ${echo} -e "\033[0m${text}\033[0m"
    ;;
  reset)
    echo ${echo} -e "\033[0m"
    ;;
  esac
}

show_step() {
  text="$1"
  length=$((${#text} + 4))

  # ANSI escape codes for colors
  green='\033[0;32m'
  blue='\033[0;34m'
  reset='\033[0m'

  # Top border
  printf "${green}╔${reset}" && printf "${green}═%.0s${reset}" $(seq 1 $((length - 2))) && printf "${green}╗${reset}\n"

  # Text with borders (using blue color)
  printf "${green}║ ${blue}%s${green} ║${reset}\n" "$text"

  # Bottom border
  printf "${green}╚${reset}" && printf "${green}═%.0s${reset}" $(seq 1 $((length - 2))) && printf "${green}╝${reset}\n"
}

create_tls_secret() {
  local host=$1
  local sec_name=$2
  local namespace=$3
  local key_file=${CERT_DIR}/${host}/key.pem
  local cert_file=${CERT_DIR}/${host}/cert.pem
  generate_certs_minica ${host}
  kubectl delete secret ${sec_name} -n ${namespace} || true
  kubectl create secret tls ${sec_name} --key ${key_file} --cert ${cert_file} -n ${namespace}
}

create_httproute() {
  local namespace=$1
  local component=$2
  local host=$3
  local targetPort=$4
  # TLS termination is handled at the Gateway level via its wildcard cert.

  echo "Creating HTTPRoute on $(echo_color brightgreen "https://${host}") for ${component}:${targetPort} in ${namespace}"
  kubectl apply -f - <<EOF
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: "${component}"
  namespace: "${namespace}"
spec:
  parentRefs:
    - name: eg
      namespace: envoy-gateway-system
      sectionName: https
  hostnames:
    - "${host}"
  rules:
    - backendRefs:
        - name: "${component}"
          port: ${targetPort}
EOF
}

generate_certs_minica() {
  local domain="$1"
  # minica replaces "*" with "_" in the output directory name it creates for a domain
  # (e.g. "*.example.com" -> "_.example.com"), so check existence against that path.
  local dir_name="${domain//\*/_}"
  [[ -e ${CERT_DIR}/${dir_name}/cert.pem ]] && return 0
  mkdir -p ${CERT_DIR}
  if command -v pass >/dev/null 2>&1 && pass ls minica >/dev/null 2>&1; then
    pass show minica/cert >${CERT_DIR}/minica.pem
    pass show minica/key >${CERT_DIR}/minica-key.pem
  fi
  (cd ${CERT_DIR} && minica -domains ${domain})
}

wait_for_resource() {
  local resource_type=$1
  local namespace=$2
  local name=$3
  local display_name="${resource_type} ${name}"

  echo_color -n brightgreen "Waiting for ${display_name} to be ready in ${namespace}: "
  local i=0
  local max_wait=300 # seconds
  local interval=2   # seconds
  local max_retries=$((max_wait / interval))

  while true; do
    if [[ ${i} -ge ${max_retries} ]]; then
      echo_color brightred " FAILED (timeout after ${max_wait}s)"
      return 1
    fi

    local is_ready=0
    case ${resource_type} in
      endpoint|ep)
        local ep
        ep=$(kubectl get ep -n "${namespace}" "${name}" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null || true)
        [[ -n ${ep} ]] && is_ready=1
        ;;
      pod)
        kubectl wait --for=condition=Ready pods \
          -l "${name}" \
          -n "${namespace}" \
          --timeout=0s \
          &>/dev/null && is_ready=1
        ;;
      deployment|deploy)
        local desired ready
        desired=$(kubectl get deployment -n "${namespace}" "${name}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
        ready=$(kubectl get deployment -n "${namespace}" "${name}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        [[ -n ${desired} ]] && [[ -n ${ready} ]] && [[ ${desired} -eq ${ready} ]] && [[ ${ready} -gt 0 ]] && is_ready=1
        ;;
      gateway)
        kubectl wait --for=condition=Accepted gateway/"${name}" -n "${namespace}" --timeout=0s &>/dev/null &&
          kubectl wait --for=condition=Programmed gateway/"${name}" -n "${namespace}" --timeout=0s &>/dev/null &&
          is_ready=1
        ;;
      *)
        echo_color brightred " ERROR: Unknown resource type ${resource_type}"
        return 1
        ;;
    esac

    [[ ${is_ready} -eq 1 ]] && break
    sleep ${interval}
    echo_color -n brightwhite "."
    i=$((i + 1))
  done

  echo_color brightgreen " OK"
  return 0
}

# Backwards compatibility wrapper
wait_for_it() {
  wait_for_resource endpoint "$1" "$2"
}

# Backwards compatibility wrapper
wait_for_deployment() {
  wait_for_resource deployment "$1" "$2"
}

check_tools() {
  local tools=(
    "kubectl"
    "helm"
    "curl"
    "docker"
    "kind"
    "base64"
    "sed"
    "mktemp"
    "readlink"
    "jq"
  )

  # minica is required for TLS certificate generation
  tools+=("minica")

  # Only require ssh/scp for remote targets
  if [[ ${TARGET_HOST:-local} != "local" ]]; then
    tools+=("ssh" "scp")
  fi

  for tool in "${tools[@]}"; do
    if ! command -v "$tool" &>/dev/null; then
      echo "Error: $tool is not installed or not in PATH."
      return 1
    fi
  done
  if [[ -n ${PAC_PASS_SECRET_FOLDER:-""} ]]; then
    if ! command -v pass &>/dev/null; then
      echo "Error: pass is not installed or not in PATH and you have the PAC_PASS_SECRET_FOLDER variable set."
      echo "Use PAC_SECRET_FOLDER instead if you want a folder instead of pass."
      return 1
    fi
  fi
  return 0
}

# Check for a tool at point-of-use and exit with a clear error if missing
require_tool() {
  local tool=$1
  if ! command -v "${tool}" &>/dev/null; then
    echo "Error: ${tool} is required for this operation but is not installed or not in PATH."
    exit 1
  fi
}

# Wrapper around gum confirm with bash fallback
_confirm() {
  local prompt="${1:-Confirm?}"
  if command -v gum &>/dev/null; then
    gum confirm "${prompt}"
  else
    local answer
    read -r -p "${prompt} [y/N] " answer </dev/tty
    [[ ${answer} =~ ^[Yy]$ ]]
  fi
}

# Wrapper around gum input with bash fallback
# Usage: _input "Prompt" "default value"
_input() {
  local prompt="${1:-Value?}"
  local default="${2:-}"
  if command -v gum &>/dev/null; then
    gum input --prompt "${prompt}: " --value "${default}" </dev/tty
  else
    local answer
    read -r -p "${prompt} [${default}]: " answer </dev/tty
    echo "${answer:-${default}}"
  fi
}

# Read one PAC secret key from pass or the plain text secret folder.
# Optional second argument forces the storage: "pass", "folder" or "auto".
# Prints nothing when the key is missing or unreadable.
pac_secret_read() {
  local key=$1 storage=${2:-auto}
  if [[ ${storage} == auto ]]; then
    storage=$(pac_secret_storage)
    [[ -n ${storage} ]] || return 0
  fi
  if [[ ${storage} == pass && -n ${PAC_PASS_SECRET_FOLDER:-} ]]; then
    pass show "${PAC_PASS_SECRET_FOLDER}/${key}" 2>/dev/null || true
  elif [[ ${storage} == folder && -n ${PAC_SECRET_FOLDER:-} ]]; then
    cat "${PAC_SECRET_FOLDER}/${key}" 2>/dev/null || true
  fi
  return 0
}

# Resolve the configured secret backend. An explicit preference wins; otherwise
# prefer a complete pass backend and fall back to a complete plain folder.
pac_secret_storage() {
  local preferred=${PAC_SECRET_STORAGE:-}
  if [[ ${preferred} == pass && -n ${PAC_PASS_SECRET_FOLDER:-} ]] && command -v pass &>/dev/null; then
    echo pass
    return 0
  fi
  if [[ ${preferred} == folder && -n ${PAC_SECRET_FOLDER:-} ]]; then
    echo folder
    return 0
  fi
  if [[ -n ${PAC_PASS_SECRET_FOLDER:-} ]] && command -v pass &>/dev/null && pac_secrets_complete pass; then
    echo pass
    return 0
  fi
  if [[ -n ${PAC_SECRET_FOLDER:-} ]] && pac_secrets_complete folder; then
    echo folder
    return 0
  fi
  if [[ -n ${PAC_PASS_SECRET_FOLDER:-} ]] && command -v pass &>/dev/null; then
    echo pass
  elif [[ -n ${PAC_SECRET_FOLDER:-} ]]; then
    echo folder
  fi
}

# Return 0 when all GitHub App credentials are present and non-empty.
# Optional first argument scopes the check to one storage (pass|folder|auto).
pac_secrets_complete() {
  local storage=${1:-auto} key
  if [[ ${storage} == auto ]]; then
    storage=$(pac_secret_storage)
    [[ -n ${storage} ]] || return 1
  fi
  for key in github-application-id github-private-key webhook.secret; do
    [[ -n "$(pac_secret_read "${key}" "${storage}")" ]] || return 1
  done
  return 0
}

xml_escape() {
  sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/"/\&quot;/g' -e "s/'/\&apos;/g"
}

# Print the configured smee/relay URL (empty when unset)
get_smee_url() {
  pac_secret_read smee
}

# Wrapper around gum choose --no-limit with bash fallback
# Usage: echo "items" | _choose_multi [--selected="item1,item2"]
_choose_multi() {
  local preselected=""
  for arg in "$@"; do
    case "${arg}" in
    --selected=*) preselected="${arg#--selected=}" ;;
    esac
  done

  if command -v gum &>/dev/null; then
    if [[ -n ${preselected} ]]; then
      gum choose --no-limit --selected="${preselected}"
    else
      gum choose --no-limit
    fi
    return
  fi

  # Bash fallback: numbered toggle menu
  local -a items=()
  local -a selected=()
  while IFS= read -r line; do
    [[ -z ${line} ]] && continue
    items+=("${line}")
    if [[ ",${preselected}," == *",${line},"* ]]; then
      selected+=(1)
    else
      selected+=(0)
    fi
  done

  local count=${#items[@]}
  [[ ${count} -eq 0 ]] && return

  while true; do
    echo "" >&2
    for i in $(seq 0 $((count - 1))); do
      local marker="[ ]"
      [[ ${selected[$i]} -eq 1 ]] && marker="[x]"
      printf "  %d) %s %s\n" "$((i + 1))" "${marker}" "${items[$i]}" >&2
    done
    echo "" >&2
    local input
    read -r -p "Toggle a number, or press Enter when done: " input </dev/tty
    if [[ -z ${input} || ${input} == "d" ]]; then
      break
    fi
    if [[ ${input} =~ ^[0-9]+$ ]] && ((input >= 1 && input <= count)); then
      local idx=$((input - 1))
      if [[ ${selected[idx]} -eq 0 ]]; then
        selected[idx]=1
      else
        selected[idx]=0
      fi
    else
      echo "Invalid input, enter a number between 1 and ${count}" >&2
    fi
  done

  for i in $(seq 0 $((count - 1))); do
    [[ ${selected[$i]} -eq 1 ]] && echo "${items[$i]}"
  done
}

makeGosmee() {
  local deploymentName=$1
  local smeeURL=$2
  local controllerURL=$3
  local namespace=${4:-gosmee}
  cat <<EOF >/tmp/${deploymentName}.yaml
---
apiVersion: v1
kind: Namespace
metadata:
  name: $namespace
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: $deploymentName
  namespace: $namespace
spec:
  replicas: 1
  selector:
    matchLabels:
      app: gosmee
  template:
    metadata:
      labels:
        app: gosmee
    spec:
      containers:
        - image: ghcr.io/chmouel/gosmee:main
          imagePullPolicy: Always
          name: gosmee
          args:
            [
              "client",
              "--output",
              "json",
              "--log-level",
              "${GOSMEE_LOG_LEVEL:-debug}",
              "--target-connection-timeout",
              "${GOSMEE_TARGET_TIMEOUT:-5}",
              "--target-retries",
              "${GOSMEE_TARGET_RETRIES:-5}",
              "--saveDir",
              "/tmp/save",
              "$smeeURL",
              "$controllerURL",
            ]
EOF
  kubectl apply -f /tmp/${deploymentName}.yaml
}

GOSMEE_SERVICE_MARKER="Managed by startpaac"

# Print the manual gosmee client command to run in a terminal
print_gosmee_manual_command() {
  local smeeurl=$1 targeturl=$2
  echo "Run gosmee manually to forward webhooks:"
  echo "  gosmee client --output json --log-level ${GOSMEE_LOG_LEVEL:-debug} --target-connection-timeout ${GOSMEE_TARGET_TIMEOUT:-5} --target-retries ${GOSMEE_TARGET_RETRIES:-5} --saveDir /tmp/replay ${smeeurl} ${targeturl}"
}

# Create/update and start a persistent per-user gosmee forwarder.
# Uses a systemd user unit on Linux and a LaunchAgent on macOS, falling
# back to printing the manual command everywhere else.
# Usage: start_gosmee_forwarder <service-name> <smee-url> <target-url>
start_gosmee_forwarder() {
  local service=${1:-gosmee} smeeurl=${2:-} targeturl=${3:-}
  if [[ -z ${smeeurl} || -z ${targeturl} ]]; then
    echo "Skipping gosmee forwarder: no smee URL or target URL configured"
    return 0
  fi
  case "$(uname -s)" in
  Darwin)
    start_gosmee_launchagent "${service}" "${smeeurl}" "${targeturl}"
    ;;
  Linux)
    if type -p systemctl >/dev/null 2>&1; then
      start_gosmee_systemd "${service}" "${smeeurl}" "${targeturl}"
    else
      print_gosmee_manual_command "${smeeurl}" "${targeturl}"
    fi
    ;;
  *)
    print_gosmee_manual_command "${smeeurl}" "${targeturl}"
    ;;
  esac
}

start_gosmee_systemd() {
  local service=$1 smeeurl=$2 targeturl=$3
  local legacy_unit="${HOME}/.config/systemd/user/${service}.service"
  local unit_name="startpaac-${service}"
  local unit="${HOME}/.config/systemd/user/${unit_name}.service"
  local gosmee_bin

  # Backwards compatibility: a unit named after the service that we do not
  # manage belongs to the user, only restart it.
  if [[ -e ${legacy_unit} ]] && ! grep -q "${GOSMEE_SERVICE_MARKER}" "${legacy_unit}"; then
    show_step "Restarting user systemd service ${service}"
    systemctl --user restart "${service}" >/dev/null 2>&1 || true
    systemctl --user --no-pager status "${service}" -o cat || true
    return 0
  fi

  gosmee_bin=$(command -v gosmee || true)
  if [[ -z ${gosmee_bin} ]]; then
    echo "gosmee is not installed (see https://github.com/chmouel/gosmee)"
    print_gosmee_manual_command "${smeeurl}" "${targeturl}"
    return 0
  fi

  if [[ ! -e ${unit} ]]; then
    if [[ ${CI_MODE:-false} == "true" ]] || ! _confirm "Create a systemd user service (${unit_name}) to forward webhooks with gosmee?"; then
      print_gosmee_manual_command "${smeeurl}" "${targeturl}"
      return 0
    fi
  fi

  show_step "Configuring systemd user service ${unit_name}"
  mkdir -p "$(dirname "${unit}")"
  local tmpunit
  tmpunit=$(mktemp)
  cat >"${tmpunit}" <<EOF
# ${GOSMEE_SERVICE_MARKER}
[Unit]
Description=Gosmee webhook forwarder for startpaac (${service})
After=network-online.target

[Service]
ExecStart=${gosmee_bin} client --output json --log-level ${GOSMEE_LOG_LEVEL:-debug} --target-connection-timeout ${GOSMEE_TARGET_TIMEOUT:-5} --target-retries ${GOSMEE_TARGET_RETRIES:-5} --saveDir /tmp/replay ${smeeurl} ${targeturl}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
  if [[ -e ${unit} ]] && cmp -s "${tmpunit}" "${unit}"; then
    rm -f "${tmpunit}"
  else
    install -m 600 "${tmpunit}" "${unit}"
    rm -f "${tmpunit}"
    systemctl --user daemon-reload
  fi
  systemctl --user enable "${unit_name}" >/dev/null 2>&1 || true
  systemctl --user restart "${unit_name}"
  systemctl --user --no-pager status "${unit_name}" -o cat || true
}

start_gosmee_launchagent() {
  local service=$1 smeeurl=$2 targeturl=$3
  local label="com.startpaac.${service}"
  local plist="${HOME}/Library/LaunchAgents/${label}.plist"
  local logfile="${HOME}/Library/Logs/startpaac-${service}.log"
  local gosmee_bin escaped_gosmee_bin escaped_label escaped_logfile escaped_smeeurl escaped_targeturl

  if [[ -e ${plist} ]] && ! grep -q "${GOSMEE_SERVICE_MARKER}" "${plist}"; then
    echo "Refusing to overwrite ${plist}: it is not managed by startpaac"
    print_gosmee_manual_command "${smeeurl}" "${targeturl}"
    return 0
  fi

  gosmee_bin=$(command -v gosmee || true)
  if [[ -z ${gosmee_bin} ]]; then
    echo "gosmee is not installed (see https://github.com/chmouel/gosmee)"
    print_gosmee_manual_command "${smeeurl}" "${targeturl}"
    return 0
  fi

  if [[ ! -e ${plist} ]]; then
    if [[ ${CI_MODE:-false} == "true" ]] || ! _confirm "Create a LaunchAgent (${label}) to forward webhooks with gosmee?"; then
      print_gosmee_manual_command "${smeeurl}" "${targeturl}"
      return 0
    fi
  fi

  show_step "Configuring LaunchAgent ${label}"
  mkdir -p "${HOME}/Library/LaunchAgents" "${HOME}/Library/Logs"
  escaped_gosmee_bin=$(printf '%s' "${gosmee_bin}" | xml_escape)
  escaped_label=$(printf '%s' "${label}" | xml_escape)
  escaped_logfile=$(printf '%s' "${logfile}" | xml_escape)
  escaped_smeeurl=$(printf '%s' "${smeeurl}" | xml_escape)
  escaped_targeturl=$(printf '%s' "${targeturl}" | xml_escape)
  local tmpplist
  tmpplist=$(mktemp)
  cat >"${tmpplist}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<!-- ${GOSMEE_SERVICE_MARKER} -->
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${escaped_label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${escaped_gosmee_bin}</string>
    <string>client</string>
    <string>--output</string>
    <string>json</string>
    <string>--log-level</string>
    <string>${GOSMEE_LOG_LEVEL:-debug}</string>
    <string>--target-connection-timeout</string>
    <string>${GOSMEE_TARGET_TIMEOUT:-5}</string>
    <string>--target-retries</string>
    <string>${GOSMEE_TARGET_RETRIES:-5}</string>
    <string>--saveDir</string>
    <string>/tmp/replay</string>
    <string>${escaped_smeeurl}</string>
    <string>${escaped_targeturl}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key>
    <false/>
  </dict>
  <key>StandardOutPath</key>
  <string>${escaped_logfile}</string>
  <key>StandardErrorPath</key>
  <string>${escaped_logfile}</string>
</dict>
</plist>
EOF
  install -m 600 "${tmpplist}" "${plist}"
  rm -f "${tmpplist}"
  local domain
  domain="gui/$(id -u)"
  launchctl bootout "${domain}/${label}" 2>/dev/null || true
  launchctl bootstrap "${domain}" "${plist}" 2>/dev/null ||
    launchctl load -w "${plist}" 2>/dev/null || {
    echo "Could not load the LaunchAgent (no GUI session?)"
    print_gosmee_manual_command "${smeeurl}" "${targeturl}"
    return 0
  }
  launchctl kickstart -k "${domain}/${label}" 2>/dev/null || true
  echo "LaunchAgent ${label} is running, logs in ${logfile}"
}

HOOKS_DIR="${HOOKS_DIR:-${HOME}/.config/startpaac/hooks}"

export_hook_environment() {
    local -a hook_env_vars=(
        CERT_DIR
        CI_MODE
        CONFIG_FILE
        DASHBOARD
        DOMAIN_NAME
        FORCE_INTERACTIVE
        FORGE_HOST
        GOSMEE_LOG_LEVEL
        GOSMEE_TARGET_RETRIES
        GOSMEE_TARGET_TIMEOUT
        HOOKS_DIR
        INSTALL_CUSTOM_OBJECT
        INSTALL_CUSTOM_OBJECT_ENABLED
        INSTALL_FORGE
        INSTALL_GITHUB_SECOND_CTRL
        INSTALL_PAC
        INSTALL_POSTGRESQL
        INSTALL_TEKTON_CHAINS
        INSTALL_TEKTON_DASHBOARD
        INSTALL_TEKTON_TRIGGERS
        KO_DEFAULTBASEIMAGE
        KUBECONFIG
        PAC
        PAC_CONTROLLER_TARGET_NS
        PAC_DEBUG_IMAGE
        PAC_DIR
        PAC_DOMAIN
        PAC_IMAGE_NONROOT
        PAC_PASS_SECOND_FOLDER
        PAC_PASS_SECRET_FOLDER
        PAC_SECOND_SECRET_FOLDER
        PAC_SECRET_FOLDER
        PAC_WEBHOOK_NODEPORT
        PAC_WEBHOOK_SECRET
        PAC_WEB_URL
        PREFERENCES_FILE
        REGISTRY
        SP
        TARGET_BIND_IP
        TARGET_HOST
        TMPFILE
        USE_NODEPORT_WEBHOOK
    )
    local var declaration

    for var in "${hook_env_vars[@]}"; do
        [[ -v ${var} ]] || continue
        declaration=$(declare -p "${var}" 2>/dev/null || true)
        [[ ${declaration} == declare\ -a* || ${declaration} == declare\ -A* ]] && continue
        export "${var?}"
    done
}

run_hook() {
    local hook_name="$1"
    local hook_path="${HOOKS_DIR}/${hook_name}"

    [[ -d "${HOOKS_DIR}" ]] || return 0

    local -a hook_files=()
    if [[ -x "${hook_path}" && -f "${hook_path}" ]]; then
        hook_files=("${hook_path}")
    elif [[ -d "${hook_path}" ]]; then
        while IFS= read -r f; do
            [[ -x "$f" && -f "$f" ]] && hook_files+=("$f")
        done < <(find "${hook_path}" -maxdepth 1 -type f | sort)
    fi

    [[ ${#hook_files[@]} -eq 0 ]] && return 0

    export_hook_environment
    export STARTPAC_HOOK_NAME="${hook_name}"
    export STARTPAAC_HOOK_NAME="${hook_name}"
    for hook_file in "${hook_files[@]}"; do
        local display_name="${hook_name}"
        [[ ${#hook_files[@]} -gt 1 ]] && display_name="${hook_name}/$(basename "${hook_file}")"
        echo_color cyan "Running hook: ${display_name}"
        if ! "${hook_file}"; then
            echo_color red "Hook '${display_name}' failed"
            return 1
        fi
        echo_color green "Hook '${display_name}' completed"
    done
}

run_with_hooks() {
    local hook_name="$1"
    shift
    run_hook "pre-${hook_name}" || return $?
    "$@" || return $?
    run_hook "post-${hook_name}"
}
