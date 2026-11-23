#!/usr/bin/env bash
# Shell-level tests for the GitHub App setup helpers in lib/common.sh
# Run with: ./tests/test_shell_helpers.sh
set -uo pipefail

SP=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck disable=SC1091
source "${SP}/lib/common.sh"

failures=0
assert() {
  local desc=$1
  shift
  if "$@"; then
    echo "ok - ${desc}"
  else
    echo "FAIL - ${desc}"
    failures=$((failures + 1))
  fi
}
assert_not() {
  local desc=$1
  shift
  if "$@"; then
    echo "FAIL - ${desc}"
    failures=$((failures + 1))
  else
    echo "ok - ${desc}"
  fi
}

TESTTMP=$(mktemp -d /tmp/.startpaac-tests.XXXXXX)
trap 'rm -rf "${TESTTMP}"' EXIT

# --- provider hostname validation ---
assert "provider hostname accepts a DNS name" \
  is_provider_hostname "ghe.example.com"
assert_not "provider hostname rejects a URL" \
  is_provider_hostname "https://ghe.example.com"
assert_not "provider hostname rejects a port" \
  is_provider_hostname "ghe.example.com:8443"
assert_not "provider hostname rejects an empty value" \
  is_provider_hostname ""

# --- provider hostname normalization ---
assert "normalize_provider_hostname keeps a bare hostname" \
  test "$(normalize_provider_hostname "ghe.example.com")" = "ghe.example.com"
assert "normalize_provider_hostname strips https scheme and path" \
  test "$(normalize_provider_hostname "https://ghe.example.com/api/v3")" = "ghe.example.com"
assert "normalize_provider_hostname strips port" \
  test "$(normalize_provider_hostname "https://ghe.example.com:8443/api/v3")" = "ghe.example.com"
assert "normalize_provider_hostname returns empty on invalid input" \
  test -z "$(normalize_provider_hostname "not a host")"

# --- PAC_E2E_CONFIG (yaml-only secret backend) ---
unset PAC_E2E_CONFIG
assert_not "secrets fail when PAC_E2E_CONFIG is unset" pac_secrets_complete

e2e_cfg="${TESTTMP}/e2e-config.yaml"
cat >"${e2e_cfg}" <<'EOF'
common:
  webhook_secret: "yaml-webhook-secret"
github:
  application_id: 98765
  private_key: |
    -----BEGIN RSA PRIVATE KEY-----
    YAML-KEY-LINE-1
    YAML-KEY-LINE-2
    -----END RSA PRIVATE KEY-----
  smee_url: "https://hook.pipelinesascode.com/yaml-primary"
github_enterprise:
  api_url: "https://ghe.internal.example/api/v3"
  application_id: "54321"
  private_key: |
    -----BEGIN RSA PRIVATE KEY-----
    GHE-KEY-LINE-1
    -----END RSA PRIVATE KEY-----
  webhook_secret: "ghe-webhook-secret"
  smee_url: "https://hook.pipelinesascode.com/yaml-ghe"
EOF

export PAC_E2E_CONFIG="${e2e_cfg}"
assert "yaml primary secrets are complete" pac_secrets_complete primary
assert "yaml primary reads integer application_id" \
  test "$(pac_secret_read github-application-id primary)" = "98765"
assert "yaml primary reads common.webhook_secret" \
  test "$(pac_secret_read webhook.secret primary)" = "yaml-webhook-secret"
assert "yaml primary reads github.smee_url" \
  test "$(get_smee_url)" = "https://hook.pipelinesascode.com/yaml-primary"
assert "yaml primary preserves multiline PEM private_key" \
  grep -q "YAML-KEY-LINE-2" <<<"$(pac_secret_read github-private-key primary)"

assert "yaml second controller secrets are complete" pac_secrets_complete second
assert "yaml second reads github_enterprise.application_id" \
  test "$(pac_secret_read github-application-id second)" = "54321"
assert "yaml second reads github_enterprise.webhook_secret" \
  test "$(pac_secret_read webhook.secret second)" = "ghe-webhook-secret"
assert "yaml second reads github_enterprise.smee_url" \
  test "$(get_smee_url second)" = "https://hook.pipelinesascode.com/yaml-ghe"

# Incomplete PAC_E2E_CONFIG fails check
e2e_incomplete="${TESTTMP}/e2e-incomplete.yaml"
cat >"${e2e_incomplete}" <<'EOF'
common:
  webhook_secret: ""
github:
  application_id: ""
EOF
assert_not "incomplete PAC_E2E_CONFIG fails check" \
  env PAC_E2E_CONFIG="${e2e_incomplete}" /bin/bash -c 'source "$1/lib/common.sh"; pac_secrets_complete primary' _ "${SP}"

# Collection-valued credential fields (list/map) are rejected
e2e_collection="${TESTTMP}/e2e-collection.yaml"
cat >"${e2e_collection}" <<'EOF'
common:
  webhook_secret: "yaml-webhook-secret"
github:
  application_id: 12345
  private_key: []
EOF
assert_not "collection-valued private_key fails pac_secrets_complete" \
  env PAC_E2E_CONFIG="${e2e_collection}" /bin/bash -c 'source "$1/lib/common.sh"; pac_secrets_complete primary' _ "${SP}"
assert_not "collection-valued private_key fails pac_e2e_config_valid" \
  pac_e2e_config_valid "${e2e_collection}"

# False-valued boolean scalars are preserved across parser backends
e2e_bool="${TESTTMP}/e2e-bool.yaml"
printf 'common:\n  webhook_secret: false\n' >"${e2e_bool}"
assert "boolean false scalar is read without error" \
  test "$(pac_e2e_config_read common webhook_secret "${e2e_bool}")" = "false"

# Malformed YAML fails closed with nonzero exit status
e2e_malformed="${TESTTMP}/e2e-malformed.yaml"
printf 'github:\n  application_id: [unterminated\n' >"${e2e_malformed}"
assert_not "malformed YAML returns nonzero from pac_e2e_config_read" \
  pac_e2e_config_read github application_id "${e2e_malformed}"
assert_not "malformed YAML fails pac_secrets_complete" \
  env PAC_E2E_CONFIG="${e2e_malformed}" /bin/bash -c 'source "$1/lib/common.sh"; pac_secrets_complete primary' _ "${SP}"

# Python fallback when yq is not on PATH
if python3 -c 'import yaml' >/dev/null 2>&1; then
  py_only_bin="${TESTTMP}/py-only-bin"
  mkdir -p "${py_only_bin}"
  ln -sf "$(command -v python3)" "${py_only_bin}/python3"
  ln -sf "$(command -v cat)" "${py_only_bin}/cat"
  py_val=$(PATH="${py_only_bin}" PAC_E2E_CONFIG="${e2e_cfg}" /bin/bash -c 'source "$1/lib/common.sh"; pac_secret_read webhook.secret primary' _ "${SP}")
  assert "python3 PyYAML fallback reads PAC_E2E_CONFIG without yq" \
    test "${py_val}" = "yaml-webhook-secret"
fi

# pac_e2e_config_write_primary enforces 0600 on existing 0644 files and preserves other sections
ghapp_out="${TESTTMP}/ghapp-out"
mkdir -p "${ghapp_out}"
printf '42424' >"${ghapp_out}/github-application-id"
printf '%s\n%s\n%s\n' '-----BEGIN RSA PRIVATE KEY-----' 'NEWKEY' '-----END RSA PRIVATE KEY-----' >"${ghapp_out}/github-private-key"
printf 'new-webhook-secret' >"${ghapp_out}/webhook.secret"
printf 'https://hook.pipelinesascode.com/new-smee' >"${ghapp_out}/smee"

existing_cfg="${TESTTMP}/existing-0644.yaml"
cp "${e2e_cfg}" "${existing_cfg}"
chmod 644 "${existing_cfg}"
assert "pac_e2e_config_write_primary succeeds on existing 0644 file" \
  pac_e2e_config_write_primary "${existing_cfg}" "${ghapp_out}"
existing_mode=$(stat -c '%a' "${existing_cfg}" 2>/dev/null || stat -f '%Lp' "${existing_cfg}")
assert "pac_e2e_config_write_primary tightens existing 0644 file to 600" \
  test "${existing_mode}" = "600"
assert "pac_e2e_config_write_primary updates github.application_id" \
  test "$(pac_e2e_config_read github application_id "${existing_cfg}")" = "42424"
assert "pac_e2e_config_write_primary preserves github_enterprise section" \
  test "$(pac_e2e_config_read github_enterprise application_id "${existing_cfg}")" = "54321"

# yq-only write path (no PyYAML) preserves other sections and enforces 600
if [[ $(pac_yaml_parser 2>/dev/null || true) == yq-go ]]; then
  noyaml_bin="${TESTTMP}/noyaml-bin"
  mkdir -p "${noyaml_bin}"
  cat >"${noyaml_bin}/python3" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
  chmod +x "${noyaml_bin}/python3"
  existing_yq="${TESTTMP}/existing-yq.yaml"
  cp "${e2e_cfg}" "${existing_yq}"
  chmod 644 "${existing_yq}"
  assert "pac_e2e_config_write_primary updates existing file via yq-go without PyYAML" \
    env PATH="${noyaml_bin}:${PATH}" /bin/bash -c 'source "$1/lib/common.sh"; pac_e2e_config_write_primary "$2" "$3"' _ "${SP}" "${existing_yq}" "${ghapp_out}"
  yq_mode=$(stat -c '%a' "${existing_yq}" 2>/dev/null || stat -f '%Lp' "${existing_yq}")
  assert "yq-go write path tightens permissions to 600" test "${yq_mode}" = "600"
  assert "yq-go write path preserves github_enterprise section" \
    test "$(pac_e2e_config_read github_enterprise application_id "${existing_yq}")" = "54321"
fi

# pass:<entry> support (streaming YAML directly from pass without plaintext files on disk)
pass_bin="${TESTTMP}/pass-bin"
mkdir -p "${pass_bin}"
pass_store="${TESTTMP}/pass-store"
mkdir -p "${pass_store}/pac"
cp "${e2e_cfg}" "${pass_store}/pac/e2e-test.yaml"
cat >"${pass_bin}/pass" <<EOF
#!/usr/bin/env bash
case "\$1" in
show)
  [[ -f "${pass_store}/\$2.yaml" ]] || exit 1
  cat "${pass_store}/\$2.yaml"
  ;;
insert)
  shift
  while [[ \$1 == -* ]]; do shift; done
  mkdir -p "\$(dirname "${pass_store}/\$1.yaml")"
  cat >"${pass_store}/\$1.yaml"
  ;;
*) exit 1 ;;
esac
EOF
chmod +x "${pass_bin}/pass"

assert "pass:<entry> is detected and completes primary checks" \
  env PATH="${pass_bin}:${PATH}" PAC_E2E_CONFIG="pass:pac/e2e-test" /bin/bash -c 'source "$1/lib/common.sh"; pac_secrets_complete primary' _ "${SP}"
assert "pass:<entry> reads second controller application_id" \
  test "$(PATH="${pass_bin}:${PATH}" PAC_E2E_CONFIG="pass:pac/e2e-test" /bin/bash -c 'source "$1/lib/common.sh"; pac_secret_read github-application-id second' _ "${SP}")" = "54321"
assert_not "missing pass:<entry> fails closed" \
  env PATH="${pass_bin}:${PATH}" PAC_E2E_CONFIG="pass:pac/missing" /bin/bash -c 'source "$1/lib/common.sh"; pac_secrets_complete primary' _ "${SP}"
assert "pac_e2e_config_write_primary updates pass:<entry> preserving github_enterprise" \
  env PATH="${pass_bin}:${PATH}" /bin/bash -c 'source "$1/lib/common.sh"; pac_e2e_config_write_primary "pass:pac/e2e-test" "$2" && [[ $(pac_e2e_config_read github application_id "pass:pac/e2e-test") == 42424 && $(pac_e2e_config_read github_enterprise application_id "pass:pac/e2e-test") == 54321 ]]' _ "${SP}" "${ghapp_out}"

# PAC_E2E_CONFIG_OVERRIDE (partial YAML overlay)
e2e_overlay="${TESTTMP}/e2e-overlay.yaml"
cat >"${e2e_overlay}" <<'EOF'
github:
  application_id: "77777"
  smee_url: "https://hook.pipelinesascode.com/overlay-smee"
EOF
assert "overlay overrides github.application_id" \
  test "$(PAC_E2E_CONFIG="${e2e_cfg}" PAC_E2E_CONFIG_OVERRIDE="${e2e_overlay}" pac_secret_read github-application-id primary)" = "77777"
assert "overlay overrides github.smee_url" \
  test "$(PAC_E2E_CONFIG="${e2e_cfg}" PAC_E2E_CONFIG_OVERRIDE="${e2e_overlay}" get_smee_url)" = "https://hook.pipelinesascode.com/overlay-smee"
assert "overlay falls back to base for omitted webhook_secret" \
  test "$(PAC_E2E_CONFIG="${e2e_cfg}" PAC_E2E_CONFIG_OVERRIDE="${e2e_overlay}" pac_secret_read webhook.secret primary)" = "yaml-webhook-secret"
assert "overlay falls back to base for omitted github_enterprise section" \
  test "$(PAC_E2E_CONFIG="${e2e_cfg}" PAC_E2E_CONFIG_OVERRIDE="${e2e_overlay}" pac_secret_read github-application-id second)" = "54321"
assert_not "missing overlay file fails closed" \
  env PAC_E2E_CONFIG="${e2e_cfg}" PAC_E2E_CONFIG_OVERRIDE="${TESTTMP}/no-such-overlay.yaml" /bin/bash -c 'source "$1/lib/common.sh"; pac_secrets_complete primary' _ "${SP}"
assert_not "malformed overlay fails closed" \
  env PAC_E2E_CONFIG="${e2e_cfg}" PAC_E2E_CONFIG_OVERRIDE="${e2e_malformed}" /bin/bash -c 'source "$1/lib/common.sh"; pac_secrets_complete primary' _ "${SP}"
assert_not "collection-valued field in overlay fails closed instead of falling back" \
  env PAC_E2E_CONFIG="${e2e_cfg}" PAC_E2E_CONFIG_OVERRIDE="${e2e_collection}" /bin/bash -c 'source "$1/lib/common.sh"; pac_secrets_complete primary' _ "${SP}"

cp "${e2e_overlay}" "${pass_store}/pac/e2e-overlay.yaml"
assert "pass:<entry> overlay works on top of file base" \
  test "$(PATH="${pass_bin}:${PATH}" PAC_E2E_CONFIG="${e2e_cfg}" PAC_E2E_CONFIG_OVERRIDE="pass:pac/e2e-overlay" /bin/bash -c 'source "$1/lib/common.sh"; pac_secret_read github-application-id primary' _ "${SP}")" = "77777"
unset PAC_E2E_CONFIG PAC_E2E_CONFIG_OVERRIDE

fakebin="${TESTTMP}/bin"
mkdir -p "${fakebin}"
export PATH="${fakebin}:${PATH}"

# --- gosmee forwarder safety ---
out=$(start_gosmee_forwarder gosmee "" "http://target" 2>&1)
assert "forwarder skips without a smee url" \
  grep -q "Skipping gosmee forwarder" <<<"${out}"

# A target with no host component ("https://" from an unset PAC/TARGET_HOST)
# must never install a service.
out=$(start_gosmee_forwarder gosmee "https://smee/x" "https://" 2>&1)
assert "forwarder skips a target with no host" \
  grep -q "Skipping gosmee forwarder" <<<"${out}"
assert "forwarder hints at the missing PAC setting" \
  grep -q "Set PAC" <<<"${out}"

export HOME="${TESTTMP}/home"
mkdir -p "${HOME}/Library/LaunchAgents"

# unmanaged plist must never be overwritten
plist="${HOME}/Library/LaunchAgents/com.startpaac.gosmee.plist"
echo "<plist>user owned</plist>" >"${plist}"
out=$(start_gosmee_launchagent gosmee "https://smee/x" "http://target" 2>&1)
assert "launchagent refuses to overwrite an unmanaged plist" \
  grep -q "Refusing to overwrite" <<<"${out}"
assert "unmanaged plist content is untouched" \
  grep -q "user owned" "${plist}"
rm -f "${plist}"

# XML metacharacters in URLs must be escaped in generated LaunchAgents.
cat >"${fakebin}/gosmee" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat >"${fakebin}/launchctl" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "${fakebin}/gosmee" "${fakebin}/launchctl"
echo "<!-- ${GOSMEE_SERVICE_MARKER} -->" >"${plist}"
out=$(start_gosmee_launchagent gosmee "https://smee/x?a=1&b=2" "http://target/hook?a=1&b=2" 2>&1)
assert "launchagent escapes ampersands in URL arguments" \
  grep -q 'https://smee/x?a=1&amp;b=2' "${plist}"
if command -v plutil >/dev/null 2>&1; then
  assert "escaped launchagent plist is valid" plutil -lint "${plist}" >/dev/null
fi
rm -f "${plist}"

# CI mode never creates services, prints the manual command instead
out=$(CI_MODE=true start_gosmee_launchagent gosmee "https://smee/x" "http://target" 2>&1)
assert "launchagent not created in CI mode" test ! -e "${plist}"
if command -v gosmee >/dev/null 2>&1; then
  assert "manual command printed in CI mode" \
    grep -q "gosmee client" <<<"${out}"
fi

out=$(print_gosmee_manual_command "https://smee/x" "http://target" 2>&1)
assert "manual command contains smee and target urls" \
  grep -q "https://smee/x http://target" <<<"${out}"

echo
if [[ ${failures} -gt 0 ]]; then
  echo "${failures} test(s) failed"
  exit 1
fi
echo "All shell tests passed"
