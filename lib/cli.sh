#!/usr/bin/env bash

CLI_DEPLOYMENTS='[["envoy-gateway-system","envoy-gateway"],["registry","docker-registry"],["tekton-pipelines","tekton-pipelines-controller"],["tekton-pipelines","tekton-pipelines-webhook"],["tekton-pipelines","tekton-dashboard"],["pipelines-as-code","pipelines-as-code-controller"],["pipelines-as-code","pipelines-as-code-watcher"],["pipelines-as-code","pipelines-as-code-webhook"]]'

help() {
  printf '%s\n' 'startpaac [action] [options]' \
    '' 'Agent workflows:' \
    '  --install-skills TARGET      Link the bundled skill for agents, claude, or all' \
    '  --up                         Create or reuse a local PAC development cluster' \
    '  --describe                   Describe supported agent interfaces (requires jq)' \
    '  --doctor                     Check local setup prerequisites' \
    '  --status                     Inspect local component readiness' \
    '  --plan                       Preview a core action without changing anything' \
    '  --non-interactive            Disable prompts and implicit service changes' \
    '  --output text|json           Select output (JSON requires jq)' \
    '' 'Deployment actions:' \
    '  -a, --all                    Recreate Kind and install selected components' \
    '  -A, --all-but-kind           Install without recreating Kind' \
    '  -p, --install-paac           Build, deploy, and configure PAC' \
    '  -c, --deploy-component NAME  Deploy controller, watcher, or webhook' \
    '  -k, --kind                   Recreate Kind' \
    '  --stop-kind                  Delete Kind and its kubeconfig' \
    '  --redeploy-kind              Recreate Kind' \
    '  --install-gateway            Install Envoy Gateway' \
    '  --install-registry           Install registry' \
    '  -t, --install-tekton         Install Tekton Pipelines' \
    '  --install-triggers           Install Tekton Triggers' \
    '  --install-chains             Install Tekton Chains' \
    '  --install-dashboard          Install Tekton Dashboard' \
    '  -g, --install-forgejo        Install Forgejo and sample repositories' \
    '  --install-postgresql         Install PostgreSQL' \
    '  --setup-forgejo-sample       Create sample Forgejo repositories' \
    '  --all-to-tekton              Recreate Kind and install through Tekton' \
    '  -F, --all-but-forge          Install without Kind or Forgejo' \
    '  -H, --all-github-second-no-forgejo  Recreate with a second GitHub controller' \
    '  -S, --github-second-ctrl     Deploy second GitHub controller' \
    '  --configure-pac              Configure PAC' \
    '  --configure-pac-target KUBECONFIG NAMESPACE E2E_CONFIG  Configure existing cluster' \
    '  --debug-image                Deploy PAC with debug image' \
    '  -s, --sync-kubeconfig        Sync kubeconfig from remote target' \
    '  -G, --start-user-gosmee      Start user webhook forwarder' \
    '  --setup-github-app           Interactive GitHub App creation' \
    '  --show-config                Show configuration' \
    '' 'Other options:' \
    '  --e2e-config FILE            Read PAC secrets and settings from an E2E YAML config' \
    '  -O, --scale-down NAME        Scale down a component after deployment' \
    '  -i, --menu, --interactive    Force component menu' \
    '  -R, --reset-preferences      Remove saved component preferences' \
    '  --ci                        Legacy noninteractive installation mode' \
    '  -h, --help                   Show help' \
    '' 'Example: startpaac --up --plan --output json'
}

cli_usage_error() {
  if [[ ${CLI_MANAGED} == true && -v CLI_ERRORS ]]; then
    cli_error invalid_arguments "$1" 'Run startpaac --help.'
    CLI_FAILURE_CODE=2
    exit 2
  fi
  if [[ ${CLI_OUTPUT} == json ]]; then
    if command -v jq >/dev/null 2>&1; then
      jq -n --arg message "$1" '{schema_version:1,ok:false,action:"arguments",target:{},data:{},errors:[{code:"invalid_arguments",message:$message,next_step:"Run startpaac --help."}],warnings:[]}'
    else
      printf '%s\n' '{"schema_version":1,"ok":false,"action":"arguments","target":{},"data":{},"errors":[{"code":"invalid_arguments","message":"Invalid arguments; JSON output requires jq.","next_step":"Install jq and run startpaac --help."}],"warnings":[]}'
    fi
  else
    printf '%s\n' "$1" 'Run startpaac --help.' >&2
  fi
  exit 2
}

cli_parse() {
  CLI_ACTION='' CLI_VALUE='' CLI_PLAN=false CLI_OUTPUT=text CLI_MANAGED=false
  export CLI_LOCAL_TARGET=false
  CLI_NON_INTERACTIVE_OVERRIDE=${NON_INTERACTIVE-}
  CLI_CI_OVERRIDE=${CI_MODE-}
  CLI_MENU_OVERRIDE=${FORCE_INTERACTIVE-}
  CLI_E2E_CONFIG_OVERRIDE=
  export CLI_E2E_CONFIG_EXPLICIT=false
  NON_INTERACTIVE=${NON_INTERACTIVE:-false}
  CI_MODE=${CI_MODE:-false}
  FORCE_INTERACTIVE=${FORCE_INTERACTIVE:-false}
  SETUP_GITHUB_APP_ONLY=false
  scale_down_controller=
  CLI_EXTRA=()
  local arg value short
  local previous=
  for arg in "$@"; do
    if [[ ${arg} == --output=json || (${previous} == --output && ${arg} == json) ]]; then
      CLI_OUTPUT=json
    fi
    previous=${arg}
  done
  while [[ $# -gt 0 ]]; do
    arg=$1
    shift
    if [[ ${arg} == --*=* ]]; then
      value=${arg#*=}
      arg=${arg%%=*}
      case ${arg} in
      --output | --deploy-component | --scale-down | --install-skills | --e2e-config) set -- "${value}" "$@" ;;
      *) cli_usage_error "${arg} does not accept an inline value." ;;
      esac
    elif [[ ${arg} == -?* && ${arg} != --* && ${#arg} -gt 2 ]]; then
      short=${arg:1:1}
      value=${arg:2}
      case ${short} in
      c | O) set -- "${value}" "$@" ;;
      *) set -- "-${value}" "$@" ;;
      esac
      arg=-${short}
    fi
    case ${arg} in
    --output)
      [[ $# -gt 0 && ($1 == json || $1 == text) ]] || cli_usage_error '--output requires text or json.'
      CLI_OUTPUT=$1
      shift
      continue
      ;;
    --plan)
      CLI_PLAN=true
      continue
      ;;
    --non-interactive)
      NON_INTERACTIVE=true
      CLI_NON_INTERACTIVE_OVERRIDE=true
      continue
      ;;
    --ci)
      CI_MODE=true
      CLI_CI_OVERRIDE=true
      continue
      ;;
    -i | --menu | --interactive)
      FORCE_INTERACTIVE=true
      CLI_MENU_OVERRIDE=true
      continue
      ;;
    --e2e-config)
      [[ $# -gt 0 && -n $1 && $1 != -* ]] || cli_usage_error '--e2e-config requires a file path.'
      CLI_E2E_CONFIG_OVERRIDE=$1
      export CLI_E2E_CONFIG_EXPLICIT=true
      shift
      continue
      ;;
    -O | --scale-down)
      [[ $# -gt 0 ]] || cli_usage_error "${arg} requires a component."
      case $1 in controller | watcher | webhook) ;; *) cli_usage_error 'Invalid scale-down component.' ;; esac
      scale_down_controller+=" $1"
      shift
      continue
      ;;
    -h) arg=--help ;;
    -a) arg=--all ;;
    -A) arg=--all-but-kind ;;
    -p) arg=--install-paac ;;
    -c) arg=--deploy-component ;;
    -k) arg=--kind ;;
    -g | --install-forge) arg=--install-forgejo ;;
    -t) arg=--install-tekton ;;
    -s) arg=--sync-kubeconfig ;;
    -S) arg=--github-second-ctrl ;;
    -G) arg=--start-user-gosmee ;;
    -F) arg=--all-but-forge ;;
    -H) arg=--all-github-second-no-forgejo ;;
    -R) arg=--reset-preferences ;;
    --)
      [[ $# -eq 0 ]] || cli_usage_error 'Unexpected positional arguments.'
      break
      ;;
    local)
      CLI_LOCAL_TARGET=true
      continue
      ;;
    esac
    case ${arg} in
    --install-skills)
      case ${1:-} in
      agents | claude | all)
        value=$1
        shift
        ;;
      *) cli_usage_error '--install-skills requires agents, claude, or all.' ;;
      esac
      ;;
    --deploy-component)
      [[ $# -gt 0 && $1 != -* ]] || cli_usage_error "${arg} requires a value."
      value=$1
      shift
      case ${value} in controller | watcher | webhook) ;; *) cli_usage_error 'Invalid deployment component.' ;; esac
      ;;
    --configure-pac-target)
      [[ $# -ge 3 ]] || cli_usage_error '--configure-pac-target requires kubeconfig, namespace, and e2e-config.'
      CLI_EXTRA=("$1" "$2" "$3")
      shift 3
      value=
      ;;
    --help | --up | --describe | --doctor | --status | --all | --all-but-kind | --install-paac | --kind | --install-forgejo | --install-tekton | --sync-kubeconfig | --github-second-ctrl | --start-user-gosmee | --all-but-forge | --all-github-second-no-forgejo | --reset-preferences | --stop-kind | --redeploy-kind | --install-gateway | --install-registry | --install-triggers | --install-chains | --install-dashboard | --install-postgresql | --setup-forgejo-sample | --all-to-tekton | --configure-pac | --debug-image | --setup-github-app | --show-config) value= ;;
    *) cli_usage_error "Unknown argument: ${arg}" ;;
    esac
    [[ -z ${CLI_ACTION} ]] || cli_usage_error 'Choose one action per invocation.'
    CLI_ACTION=${arg}
    CLI_VALUE=${value}
  done
  cli_validate
}

cli_validate() {
  if [[ ${CLI_PLAN} == true || ${CLI_OUTPUT} == json ]]; then
    case ${CLI_ACTION} in
    --up | --install-paac | --deploy-component | --stop-kind) ;;
    --describe | --doctor | --status) [[ ${CLI_PLAN} == false ]] || cli_usage_error '--plan requires a deployment or teardown action.' ;;
    *) cli_usage_error 'JSON and --plan support only core agent actions; see --help.' ;;
    esac
  fi
  if [[ ${NON_INTERACTIVE} == true && -z ${CLI_ACTION} ]]; then
    cli_usage_error '--non-interactive requires an explicit action.'
  fi
  case ${CLI_ACTION} in --up | --describe | --doctor | --status) CLI_MANAGED=true ;; esac
  if [[ ${CLI_PLAN} == true || ${CLI_OUTPUT} == json || ${NON_INTERACTIVE} == true ]]; then
    CLI_MANAGED=true
  fi
  if [[ ${CLI_OUTPUT} == json || ${CLI_ACTION} == --up ]]; then
    NON_INTERACTIVE=true
    CLI_NON_INTERACTIVE_OVERRIDE=true
  fi
  if [[ ${NON_INTERACTIVE} == true ]]; then
    case ${CLI_ACTION} in
    --help | --up | --describe | --doctor | --status | --install-paac | --deploy-component | --stop-kind | --setup-github-app | --install-skills) ;;
    *) cli_usage_error '--non-interactive supports core agent actions; use existing flags and --ci for other workflows.' ;;
    esac
  fi
  if [[ ${FORCE_INTERACTIVE} == true && (${NON_INTERACTIVE} == true || ${CLI_PLAN} == true) ]]; then
    cli_usage_error '--menu cannot be combined with noninteractive execution or --plan.'
  fi
  if [[ ${CLI_ACTION} == --up && -n ${scale_down_controller} ]]; then
    cli_usage_error '--up requires ready PAC components; scale components down in a separate deployment action.'
  fi
  [[ ${CLI_ACTION} != --setup-github-app ]] || SETUP_GITHUB_APP_ONLY=true
  export NON_INTERACTIVE CI_MODE SETUP_GITHUB_APP_ONLY
}

cli_error() {
  CLI_ERRORS=$(jq -c --arg code "$1" --arg message "$2" --arg next "$3" \
    '. + [{code:$code,message:$message,next_step:$next}]' <<<"${CLI_ERRORS}")
}

cli_warning() {
  CLI_WARNINGS=$(jq -c --arg message "$1" '. + [$message]' <<<"${CLI_WARNINGS}")
}

cli_check() {
  local id=$1 ok=$2 message=$3 next=$4
  CLI_CHECKS=$(jq -c --arg id "${id}" --argjson ok "${ok}" --arg message "${message}" \
    '. + [{id:$id,ok:$ok,message:$message}]' <<<"${CLI_CHECKS}")
  [[ ${ok} == true ]] || cli_error "${id}" "${message}" "${next}"
}

cli_result() {
  local code=$1
  if [[ ${code} -ne 0 && ${CLI_ERRORS} == '[]' ]]; then
    cli_error operation_failed "Failed during ${CLI_STEP}." 'Run --doctor and inspect the failed step before retrying.'
  fi
  if [[ ${CLI_OUTPUT} == json ]]; then
    jq -n --arg action "${CLI_ACTION#--}" --argjson ok "$([[ ${code} == 0 ]] && echo true || echo false)" \
      --arg host "${TARGET_HOST:-local}" --arg kubeconfig "${KUBECONFIG:-}" \
      --argjson data "${CLI_DATA}" --argjson errors "${CLI_ERRORS}" --argjson warnings "${CLI_WARNINGS}" \
      '{schema_version:1,ok:$ok,action:$action,target:{host:$host,cluster:"kind",kubeconfig:$kubeconfig},data:$data,errors:$errors,warnings:$warnings}' >&3
  else
    printf '%s: %s\n' "${CLI_ACTION#--}" "$([[ ${code} == 0 ]] && echo OK || echo FAILED)"
    jq -r --arg host "${TARGET_HOST:-local}" --arg kubeconfig "${KUBECONFIG:-}" --argjson plan "${CLI_PLAN}" '
      (.checks[]? | "\(.id): \(.message)"),
      (if $plan and has("steps") then
        "Target: \($host) / kind",
        "Kubeconfig: \($kubeconfig)",
        (select(.pac_dir != "") | "PAC checkout: \(.pac_dir)"),
        (select(.component != "") | "Component: \(.component)"),
        (select(.destructive) | "Deletes the Kind cluster and its kubeconfig."),
        (.hooks[] | "Hook: \(.)"),
        (.scale_down[] | "Scale down: \(.)")
      else empty end),
      (.steps[]? | "  \(.)"),
      (.components[]? | "\(.namespace)/\(.name): \(if .ready then "ready" else "not ready" end)"),
      (if has("registry_ready") then
        "Registry: \(.endpoints.registry) (\(if .registry_ready then "ready" else "unavailable" end))",
        "Webhook forwarder: \(.forwarder)",
        "Webhook delivery: \(.webhook_delivery)"
      else empty end)
    ' <<<"${CLI_DATA}"
    jq -r '.[] | "\(.message) Next: \(.next_step)"' <<<"${CLI_ERRORS}"
    jq -r '.[] | "Warning: \(.)"' <<<"${CLI_WARNINGS}"
    [[ ${CLI_ACTION} != --describe ]] || jq . <<<"${CLI_DATA}"
  fi
}

cli_cleanup() {
  local code=$?
  trap - EXIT
  if ((${#CLI_TEMP_FILES[@]})); then
    rm -f -- "${CLI_TEMP_FILES[@]}" || true
  fi
  if [[ ${CLI_MANAGED} == true ]]; then
    [[ ${code} -eq 0 ]] || code=${CLI_FAILURE_CODE}
    cli_result "${code}"
  fi
  exit "${code}"
}

cli_describe() {
  CLI_DATA='{"actions":[{"flag":"--up","effect":"Create or reuse local Kind; deploy core, PAC, and Dashboard"},{"flag":"--install-paac","effect":"Build, deploy, and configure PAC"},{"flag":"--deploy-component","argument":"controller|watcher|webhook","effect":"Build and deploy one PAC component"},{"flag":"--stop-kind","effect":"Delete Kind and its kubeconfig","destructive":true},{"flag":"--doctor","effect":"Inspect setup prerequisites"},{"flag":"--status","effect":"Inspect component readiness and forwarding state"},{"flag":"--describe","effect":"Describe agent interfaces without loading configuration"}],"options":{"--plan":"Read-only preview of a core action","--non-interactive":"No prompts, browser, or implicit service changes","--output":"text|json","--e2e-config":"Read PAC secrets and settings from an E2E YAML config"},"examples":["startpaac --up --plan --output json","startpaac --up --non-interactive --output json","startpaac -c watcher --non-interactive --output json","startpaac --status --output json"]}'
}

cli_check_docker_target() {
  local endpoint
  if [[ ${KIND_EXPERIMENTAL_PROVIDER:-docker} != docker ]]; then
    cli_error kind_provider 'Agent workflows require the Docker Kind provider.' 'Select the Docker provider and retry.'
    return 1
  fi
  if ! endpoint=$(docker context inspect --format '{{.Endpoints.docker.Host}}' 2>/dev/null); then
    cli_error docker_endpoint_unavailable 'Cannot resolve the active Docker endpoint.' 'Check the Docker context and any endpoint overrides.'
    return 1
  fi
  if [[ ${endpoint} != unix:///?* ]]; then
    cli_error docker_endpoint_nonlocal 'Agent workflows require Docker to use a local Unix socket.' 'Select a local Docker context and check DOCKER_HOST and DOCKER_CONTEXT.'
    return 1
  fi
  export DOCKER_HOST=${endpoint} KIND_EXPERIMENTAL_PROVIDER=docker
  unset DOCKER_CONTEXT
}

cli_preflight() {
  local tool ok tools='kubectl kind docker'
  case ${CLI_ACTION} in
  --doctor | --up) tools+=' helm curl jq minica ko go git ping sed mktemp' ;;
  --install-paac) tools+=' curl minica ko go mktemp' ;;
  --deploy-component) tools+=' curl ko go' ;;
  --status) tools+=' curl' ;;
  --stop-kind) tools='kind docker kubectl' ;;
  *) tools+=' helm curl jq minica' ;;
  esac
  for tool in ${tools}; do
    ok=false
    command -v "${tool}" >/dev/null 2>&1 && ok=true
    cli_check "tool_${tool}" "${ok}" "${tool}: ${ok}" "Install ${tool} and ensure it is on PATH."
  done
  ok=false
  [[ ${TARGET_HOST} != local ]] || ok=true
  cli_check local_target "${ok}" 'Agent workflows require TARGET_HOST=local.' 'Use the existing interactive workflow for remote targets.'
  ok=false
  [[ ${KUBECONFIG} != *:* ]] && ok=true
  cli_check kubeconfig_path "${ok}" 'KUBECONFIG must name one dedicated file.' 'Select a single kubeconfig file instead of a list.'
  case ${CLI_ACTION} in
  --up | --doctor | --install-paac | --deploy-component)
    ok=false
    [[ -f ${PAC_DIR:-}/config/400-controller.yaml && -f ${PAC_DIR:-}/config/500-watcher.yaml && -f ${PAC_DIR:-}/config/600-webhook.yaml && -f ${PAC_DIR:-}/go.mod ]] && ok=true
    cli_check pac_source "${ok}" 'PAC checkout must contain go.mod and its controller, watcher, and webhook manifests.' 'Set PAC_DIR to a Pipelines-as-Code source checkout.'
    ;;
  esac
  case ${CLI_ACTION} in
  --up | --doctor | --install-paac)
    ok=false
    pac_e2e_config_exists "${PAC_E2E_CONFIG:-}" && ok=true
    cli_check e2e_config_file "${ok}" "PAC_E2E_CONFIG exists: ${ok}" "Set PAC_E2E_CONFIG (or pass --e2e-config FILE or pass:<entry>) to a readable E2E YAML config."
    ok=false
    pac_yaml_parser >/dev/null 2>&1 && ok=true
    cli_check tool_yaml_parser "${ok}" "YAML parser (yq or python3+PyYAML): ${ok}" "Install yq (or python3 with PyYAML) to read PAC_E2E_CONFIG."
    ok=false
    pac_secrets_complete && [[ -n $(get_smee_url) ]] && ok=true
    cli_check credentials "${ok}" 'Reusable GitHub App credentials and relay URL are required.' 'Configure PAC_E2E_CONFIG (--e2e-config) with GitHub App credentials and smee_url, or run --setup-github-app separately.'
    ;;
  esac
  CLI_CLUSTER_EXISTS=false
  if [[ ${TARGET_HOST} == local ]] && command -v docker >/dev/null 2>&1 && cli_check_docker_target && command -v kind >/dev/null 2>&1; then
    local clusters bindings
    if clusters=$(kind get clusters 2>/dev/null); then
      while IFS= read -r cluster; do
        [[ ${cluster} != kind ]] || CLI_CLUSTER_EXISTS=true
      done <<<"${clusters}"
      if [[ ${CLI_CLUSTER_EXISTS} == true ]]; then
        bindings=$(docker inspect kind-control-plane --format '{{json .HostConfig.PortBindings}}' 2>/dev/null || echo '{}')
        ok=false
        if jq -e --arg ip "${TARGET_BIND_IP:-127.0.0.1}" '
          any(.["31080/tcp"][]?; .HostPort == "80" and .HostIp == $ip) and
          any(.["31443/tcp"][]?; .HostPort == "443" and .HostIp == $ip) and
          any(.["30080/tcp"][]?; .HostPort == "30080" and .HostIp == $ip)' <<<"${bindings}" >/dev/null; then
          ok=true
        fi
        if [[ ${CLI_ACTION} != --stop-kind ]]; then
          cli_check cluster_compatible "${ok}" 'Existing Kind cluster must expose startpaac ports on the configured bind IP.' 'Use a compatible cluster, or explicitly request recreation with --kind.'
        fi
        cli_check_kubeconfig
      elif [[ ${CLI_ACTION} == --up && -e ${KUBECONFIG} ]]; then
        cli_error kubeconfig_exists 'Kind is absent but the selected kubeconfig already exists.' 'Choose an unused dedicated kubeconfig path; existing configuration will not be overwritten.'
      elif [[ ${CLI_ACTION} != --up && ${CLI_ACTION} != --doctor ]]; then
        cli_error cluster_missing 'The local Kind cluster does not exist.' 'Run --up to create it.'
      fi
    else
      cli_error cluster_unavailable 'Cannot inspect local Kind clusters.' 'Check Docker is running and kind can access it.'
    fi
  fi
  CLI_DATA=$(jq -n --argjson checks "${CLI_CHECKS}" --argjson exists "${CLI_CLUSTER_EXISTS}" \
    '{checks:$checks,cluster_exists:$exists}')
}

cli_check_kubeconfig() {
  if [[ ! -f ${KUBECONFIG} ]]; then
    case ${CLI_ACTION} in --up | --doctor) return 0 ;; esac
    cli_error kubeconfig_missing 'The target kubeconfig does not exist.' 'Run --up to export the local Kind kubeconfig.'
    return 0
  fi
  command -v kubectl >/dev/null 2>&1 || return 0
  local expected actual
  expected=$(kind get kubeconfig --name kind 2>/dev/null | kubectl --kubeconfig=/dev/stdin --context=kind-kind config view --raw --minify -o 'jsonpath={.clusters[0].cluster.server}|{.clusters[0].cluster.certificate-authority-data}' 2>/dev/null || true)
  actual=$(kubectl --context=kind-kind config view --raw --flatten -o json 2>/dev/null | jq -er '
    select((.clusters | length) == 1 and (.contexts | length) == 1 and (.users | length) == 1) |
    select(.contexts[0].name == "kind-kind" and
      .contexts[0].context.cluster == .clusters[0].name and .contexts[0].context.user == .users[0].name) |
    .clusters[0].cluster | .server + "|" + .["certificate-authority-data"]' 2>/dev/null || true)
  if [[ -z ${expected} || ${expected} != "${actual}" ]]; then
    cli_error kubeconfig_mismatch 'KUBECONFIG must contain only the local Kind cluster and its context and user.' 'Select its dedicated kubeconfig; startpaac will not overwrite or delete a shared or different cluster configuration.'
  fi
}

cli_build_plan() {
  local steps hook_steps hooks='[]' step phase path file
  case ${CLI_ACTION} in
  --up)
    if [[ ${CLI_CLUSTER_EXISTS} == true ]]; then step=reuse-kind; else step=create-kind; fi
    steps=$(jq -cn --arg first "${step}" '[$first,"sync-kubeconfig","install-gateway","install-registry","install-tekton","install-dashboard","install-pac","configure-pac","configure-pac-custom-certs","patch-pac-service-nodeport","set-namespace"]')
    ;;
  --install-paac) steps='["install-pac","configure-pac","configure-pac-custom-certs","patch-pac-service-nodeport"]' ;;
  --deploy-component) steps='["install-pac"]' ;;
  --stop-kind) steps='["stop-kind"]' ;;
  esac
  hook_steps=${steps}
  [[ ${CLI_ACTION} != --up ]] || hook_steps=$(jq -c '. + ["all"]' <<<"${steps}")
  while IFS= read -r step; do
    case ${step} in create-kind | reuse-kind | set-namespace) continue ;; esac
    for phase in pre post; do
      path=${HOOKS_DIR}/${phase}-${step}
      if [[ -f ${path} && -x ${path} ]]; then
        hooks=$(jq -c --arg path "${path}" '. + [$path]' <<<"${hooks}")
      elif [[ -d ${path} ]]; then
        while IFS= read -r file; do
          [[ -x ${file} ]] || continue
          hooks=$(jq -c --arg path "${file}" '. + [$path]' <<<"${hooks}")
        done < <(find "${path}" -maxdepth 1 -type f | sort)
      fi
    done
  done < <(jq -r '.[]' <<<"${hook_steps}")
  CLI_DATA=$(jq --argjson steps "${steps}" --argjson hooks "${hooks}" --arg component "${CLI_VALUE}" \
    --arg pac_dir "${PAC_DIR:-}" --argjson destructive "$([[ ${CLI_ACTION} == --stop-kind ]] && echo true || echo false)" \
    --arg scaled "${scale_down_controller}" \
    '. + {steps:$steps,hooks:$hooks,component:$component,pac_dir:$pac_dir,destructive:$destructive,scale_down:($scaled | split(" ") | map(select(length > 0)))}' <<<"${CLI_DATA}")
  if [[ ${CLI_ACTION} == --up ]]; then
    cli_warning 'Registry setup may restart containerd. Webhook forwarders are left unchanged by --up.'
  fi
}

cli_read_status() {
  local deployments components
  if ! deployments=$(kubectl --context=kind-kind --request-timeout=10s get deployments -A -o json 2>/dev/null); then
    cli_error cluster_unreachable 'Cannot query deployments in the target cluster.' 'Check Docker, kubeconfig, and Kubernetes API availability.'
    return 0
  fi
  components=$(jq -c --argjson wanted "${CLI_DEPLOYMENTS}" '
    . as $deployments |
    $wanted |
    map(. as $wanted | ([$deployments.items[] | select(.metadata.namespace == $wanted[0] and .metadata.name == $wanted[1])][0]) as $d |
      ($d.spec.replicas // 1) as $desired | ($d.status.updatedReplicas // 0) as $updated |
      {namespace:$wanted[0],name:$wanted[1],ready:($d != null and $desired > 0 and
        ($d.status.observedGeneration // 0) >= ($d.metadata.generation // 0) and
        $updated >= $desired and ($d.status.replicas // 0) == $updated and
        ($d.status.availableReplicas // 0) >= $updated)})' <<<"${deployments}")
  if ! jq -e 'all(.[]; .ready)' <<<"${components}" >/dev/null; then
    cli_error components_not_ready 'Some development components are missing or not ready.' 'Inspect the component states and Kubernetes events.'
  fi
  local registry_ready=false forwarder=unverified
  curl --connect-timeout 5 --max-time 10 -fkso /dev/null "https://${REGISTRY}/v2/" && registry_ready=true
  if [[ ${registry_ready} != true ]]; then
    cli_error registry_unavailable 'The registry endpoint is unavailable.' 'Check registry readiness, gateway routing, and local DNS.'
  fi
  if command -v systemctl >/dev/null 2>&1; then
    if systemctl --user is-active --quiet startpaac-gosmee 2>/dev/null || systemctl --user is-active --quiet gosmee 2>/dev/null; then
      forwarder=running
    fi
  elif command -v launchctl >/dev/null 2>&1; then
    if launchctl print "gui/$(id -u)/com.startpaac.gosmee" 2>/dev/null | grep -q 'state = running'; then
      forwarder=running
    fi
  fi
  CLI_DATA=$(jq --argjson components "${components}" --argjson registry "${registry_ready}" --arg forwarder "${forwarder}" \
    --arg pac "https://${PAC}" --arg dashboard "https://${DASHBOARD}" --arg registry_url "https://${REGISTRY}" \
    '. + {components:$components,registry_ready:$registry,endpoints:{pac:$pac,dashboard:$dashboard,registry:$registry_url},forwarder:$forwarder,webhook_delivery:"unverified"}' <<<"${CLI_DATA}")
  cli_warning 'Webhook delivery is unverified; a running forwarder alone does not prove end-to-end GitHub delivery. Run --start-user-gosmee separately if forwarding needs setup.'
}

cli_execute_core() {
  TMPFILE=$(mktemp /tmp/.startpaac.XXXXXX)
  CLI_TEMP_FILES+=("${TMPFILE}")
  case ${CLI_ACTION} in
  --up)
    mkdir -p "$(dirname "${KUBECONFIG}")"
    if [[ ${CLI_CLUSTER_EXISTS} != true ]]; then
      install_kind
    elif [[ ! -f ${KUBECONFIG} ]]; then
      kind export kubeconfig --name kind --kubeconfig "${KUBECONFIG}"
    fi
    kubectl config use-context kind-kind
    unset HELM_KUBEAPISERVER HELM_KUBECAFILE HELM_KUBEINSECURE_SKIP_TLS_VERIFY HELM_KUBETLS_SERVER_NAME
    unset HELM_KUBEASGROUPS HELM_KUBEASUSER HELM_KUBETOKEN
    export HELM_KUBECONTEXT=kind-kind
    export INSTALL_PAC=true INSTALL_TEKTON_DASHBOARD=true INSTALL_FORGE=false
    export INSTALL_TEKTON_TRIGGERS=false INSTALL_TEKTON_CHAINS=false INSTALL_POSTGRESQL=false
    export INSTALL_CUSTOM_OBJECT_ENABLED=false INSTALL_GITHUB_SECOND_CTRL=false
    all
    ;;
  --install-paac)
    kubectl config use-context kind-kind
    cd "${PAC_DIR}" || return 1
    run_with_hooks install-pac install_pac
    run_with_hooks configure-pac configure_pac
    run_with_hooks configure-pac-custom-certs configure_pac_custom_certs
    run_with_hooks patch-pac-service-nodeport patch_pac_service_nodeport
    ;;
  --deploy-component)
    kubectl config use-context kind-kind
    cd "${PAC_DIR}" || return 1
    run_with_hooks install-pac install_pac "${CLI_VALUE}"
    ;;
  --stop-kind)
    run_with_hooks stop-kind stop_kind
    return
    ;;
  esac
  local namespace deployment
  while IFS=$'\t' read -r namespace deployment; do
    [[ " ${scale_down_controller} " != *" ${deployment#pipelines-as-code-} "* ]] || continue
    kubectl --request-timeout=10s rollout status "deployment/${deployment}" -n "${namespace}" --timeout=300s
  done < <(jq -r --arg action "${CLI_ACTION}" --arg component "${CLI_VALUE}" \
    '.[] | select($action == "--up" or (.[0] == "pipelines-as-code" and ($component == "" or .[1] == "pipelines-as-code-" + $component))) | @tsv' <<<"${CLI_DEPLOYMENTS}")
  if [[ ${CLI_ACTION} == --up ]]; then cli_read_status; fi
}

cli_require_jq() {
  if [[ ${CLI_MANAGED} == true ]] && ! command -v jq >/dev/null 2>&1; then
    if [[ ${CLI_OUTPUT} == json ]]; then
      printf '%s\n' '{"schema_version":1,"ok":false,"action":"initialization","target":{},"data":{},"errors":[{"code":"tool_jq","message":"Agent interfaces require jq.","next_step":"Install jq."}],"warnings":[]}'
    else
      printf '%s\n' 'Agent interfaces require jq. Install jq first.' >&2
    fi
    exit 1
  fi
}

install_skills() {
  local skill_dir=${SP}/skills/startpaac directory destination
  local -a directories=()
  if [[ ! -f ${skill_dir}/SKILL.md ]]; then
    printf 'Bundled skill not found at %s. Use a complete startpaac checkout.\n' "${skill_dir}" >&2
    return 1
  fi
  case $1 in
  agents) directories=("${HOME}/.agents/skills") ;;
  claude) directories=("${HOME}/.claude/skills") ;;
  all) directories=("${HOME}/.agents/skills" "${HOME}/.claude/skills") ;;
  esac

  for directory in "${directories[@]}"; do
    destination=${directory}/startpaac
    if [[ -L ${destination} && ${destination} -ef ${skill_dir} ]]; then
      continue
    fi
    if [[ -e ${destination} || -L ${destination} ]]; then
      printf 'Skill path already exists: %s. Move it aside to link this checkout.\n' "${destination}" >&2
      return 1
    fi
  done

  for directory in "${directories[@]}"; do
    destination=${directory}/startpaac
    if [[ -L ${destination} && ${destination} -ef ${skill_dir} ]]; then
      printf 'Skill already linked at %s\n' "${destination}"
      continue
    fi
    mkdir -p -- "${directory}"
    ln -s -- "${skill_dir}" "${directory}/"
    printf 'Linked skill at %s\n' "${destination}"
  done
}

cli_main() {
  cli_parse "$@"
  case ${CLI_ACTION} in
  --help)
    help
    return
    ;;
  --install-skills)
    install_skills "${CLI_VALUE}"
    return
    ;;
  esac
  cli_require_jq
  exec 3>&1
  [[ ${CLI_OUTPUT} != json ]] || exec 1>&2
  CLI_ERRORS='[]' CLI_WARNINGS='[]' CLI_CHECKS='[]' CLI_DATA='{}' CLI_STEP=initialization CLI_FAILURE_CODE=1
  CLI_TEMP_FILES=()
  trap cli_cleanup EXIT
  if [[ ${CLI_ACTION} == --describe ]]; then
    cli_describe
    return
  fi
  if [[ ${CLI_MANAGED} == true ]]; then
    export STARTPAAC_CREATE_CONFIG=false
  fi
  local requested_noninteractive=${CLI_NON_INTERACTIVE_OVERRIDE} requested_ci=${CLI_CI_OVERRIDE} requested_menu=${CLI_MENU_OVERRIDE} requested_e2e_config=${CLI_E2E_CONFIG_OVERRIDE} env_e2e_config=${PAC_E2E_CONFIG-}
  [[ -n ${requested_noninteractive} ]] || unset NON_INTERACTIVE
  [[ -n ${requested_ci} ]] || unset CI_MODE
  [[ -n ${requested_menu} ]] || unset FORCE_INTERACTIVE
  source "${SP}/lib/config.sh"
  NON_INTERACTIVE=${requested_noninteractive:-${NON_INTERACTIVE:-false}}
  CI_MODE=${requested_ci:-${CI_MODE:-false}}
  FORCE_INTERACTIVE=${requested_menu:-${FORCE_INTERACTIVE:-false}}
  if [[ -n ${requested_e2e_config} ]]; then
    PAC_E2E_CONFIG=${requested_e2e_config}
  elif [[ -n ${env_e2e_config} ]]; then
    PAC_E2E_CONFIG=${env_e2e_config}
  fi
  if [[ -n ${PAC_E2E_CONFIG:-} ]]; then
    if ! pac_e2e_config_is_pass "${PAC_E2E_CONFIG}"; then
      PAC_E2E_CONFIG=${PAC_E2E_CONFIG/#\~/${HOME}}
      [[ ${PAC_E2E_CONFIG} == /* ]] || PAC_E2E_CONFIG=${PWD}/${PAC_E2E_CONFIG}
    fi
    export PAC_E2E_CONFIG
  fi
  if [[ ${CLI_ACTION} == --configure-pac-target && ${#CLI_EXTRA[@]} -ge 3 ]]; then
    local target_secrets=${CLI_EXTRA[2]}
    if ! pac_e2e_config_is_pass "${target_secrets}"; then
      target_secrets=${target_secrets/#\~/${HOME}}
      [[ ${target_secrets} == /* ]] || target_secrets=${PWD}/${target_secrets}
    fi
    CLI_EXTRA[2]=${target_secrets}
    export PAC_E2E_CONFIG=${target_secrets}
    export CLI_E2E_CONFIG_EXPLICIT=true
  fi
  cli_validate
  cli_require_jq
  if [[ ${CLI_MANAGED} == true ]] && pac_e2e_config_is_pass "${PAC_E2E_CONFIG:-}"; then
    export PASSWORD_STORE_GPG_OPTS="${PASSWORD_STORE_GPG_OPTS:-} --batch --no-tty --pinentry-mode error"
  fi
  initialize_runtime
  if [[ ${CLI_MANAGED} == true ]]; then
    if [[ ${CLI_ACTION} == --setup-github-app || ${FORCE_INTERACTIVE} == true ]]; then
      cli_error requires_interaction 'This action requires an interactive session.' 'Run it separately in a terminal without --non-interactive.'
      exit 1
    fi
    [[ ${KUBECONFIG} == /* || ${KUBECONFIG} == *:* ]] || KUBECONFIG=${PWD}/${KUBECONFIG}
    [[ -z ${HOOKS_DIR} || ${HOOKS_DIR} == /* ]] || HOOKS_DIR=${PWD}/${HOOKS_DIR}
    [[ -z ${PAC_DIR:-} || ${PAC_DIR} == /* ]] || PAC_DIR=${PWD}/${PAC_DIR}
    cli_preflight
    case ${CLI_ACTION} in
    --up | --install-paac | --deploy-component | --stop-kind) cli_build_plan ;;
    --status) [[ ${CLI_ERRORS} != '[]' ]] || cli_read_status ;;
    esac
    if [[ ${CLI_ERRORS} != '[]' ]]; then exit 1; fi
    if [[ ${CLI_PLAN} == true || ${CLI_ACTION} == --doctor || ${CLI_ACTION} == --status ]]; then return; fi
    case ${CLI_ACTION} in
    --up | --install-paac | --deploy-component | --stop-kind)
      if [[ ${CLI_ACTION} == --up ]]; then cd "${PAC_DIR}" || exit 1; fi
      cli_execute_core
      [[ ${CLI_ERRORS} == '[]' ]] || exit 1
      return
      ;;
    esac
  fi
  [[ ${SETUP_GITHUB_APP_ONLY} == true ]] || check_tools
  TMPFILE=$(mktemp /tmp/.startpaac.XXXXXX)
  CLI_TEMP_FILES+=("${TMPFILE}")
  execute_action "${CLI_EXTRA[@]}"
}
