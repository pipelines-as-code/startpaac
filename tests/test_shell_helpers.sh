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

# --- pac_secret_read / pac_secrets_complete with a plain folder ---
unset PAC_PASS_SECRET_FOLDER
unset PAC_SECRET_STORAGE
export PAC_SECRET_FOLDER="${TESTTMP}/secrets"
mkdir -p "${PAC_SECRET_FOLDER}"

assert_not "incomplete secrets fail when files are missing" pac_secrets_complete

for key in github-application-id github-private-key webhook.secret; do
  : >"${PAC_SECRET_FOLDER}/${key}"
done
assert_not "incomplete secrets fail when files are empty" pac_secrets_complete

echo "12345" >"${PAC_SECRET_FOLDER}/github-application-id"
echo "PEM" >"${PAC_SECRET_FOLDER}/github-private-key"
echo "hooksecret" >"${PAC_SECRET_FOLDER}/webhook.secret"
echo "https://hook.pipelinesascode.com/abc" >"${PAC_SECRET_FOLDER}/smee"
assert "complete secrets pass" pac_secrets_complete

# Scoped storage: a configured pass folder must not shadow an explicit folder check
export PAC_PASS_SECRET_FOLDER="startpaac-tests/does-not-exist"
assert "folder-scoped check ignores pass" pac_secrets_complete folder
folder_id=$(pac_secret_read github-application-id folder)
assert "folder-scoped read ignores pass" test "${folder_id}" = "12345"
assert_not "pass-scoped check fails on missing pass entries" pac_secrets_complete pass

# An incomplete pass backend must not shadow a complete plain folder.
fakebin="${TESTTMP}/bin"
mkdir -p "${fakebin}"
cat >"${fakebin}/pass" <<'EOF'
#!/usr/bin/env bash
[[ ${FAKE_PASS_COMPLETE:-false} == true ]] || exit 1
case "${2##*/}" in
github-application-id) echo 67890 ;;
github-private-key) echo PASS-PEM ;;
webhook.secret) echo pass-hooksecret ;;
smee) echo https://pass.example/smee ;;
esac
EOF
chmod +x "${fakebin}/pass"
export PATH="${fakebin}:${PATH}"
assert "auto storage falls back from incomplete pass to complete folder" pac_secrets_complete

# An explicit choice must remain authoritative even when both backends work.
export FAKE_PASS_COMPLETE=true PAC_SECRET_STORAGE=folder
preferred_smee=$(get_smee_url)
assert "explicit folder preference overrides a complete pass backend" \
  test "${preferred_smee}" = "https://hook.pipelinesascode.com/abc"
unset FAKE_PASS_COMPLETE PAC_SECRET_STORAGE PAC_PASS_SECRET_FOLDER

smee=$(get_smee_url)
assert "get_smee_url returns the smee file content" \
  test "${smee}" = "https://hook.pipelinesascode.com/abc"

# --- gosmee forwarder safety ---
out=$(start_gosmee_forwarder gosmee "" "http://target" 2>&1)
assert "forwarder skips without a smee url" \
  grep -q "Skipping gosmee forwarder" <<<"${out}"

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
