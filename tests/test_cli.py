import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MOCK = r'''
import json, os, pathlib, sys
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
state = pathlib.Path(os.environ["FAKE_STATE"])
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps([tool] + args) + "\n")
if tool == "git":
    print(os.environ.get("FAKE_GIT_ROOT") or os.environ.get("PAC_DIR", ""))
elif tool == "kind":
    if os.environ.get("FAKE_KIND_DOCKER_HOST") and (
        os.environ.get("DOCKER_HOST") != os.environ["FAKE_KIND_DOCKER_HOST"]
        or os.environ.get("DOCKER_CONTEXT") or os.environ.get("KIND_EXPERIMENTAL_PROVIDER") != "docker"
    ):
        sys.exit(64)
    if args[:2] == ["get", "clusters"] and state.exists():
        print("kind")
    elif args[:2] == ["get", "kubeconfig"]:
        print("kind kubeconfig")
    elif args[:2] == ["create", "cluster"]:
        state.write_text("cluster-identity")
        path = pathlib.Path(args[args.index("--kubeconfig") + 1])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("kind kubeconfig")
    elif args[:2] == ["delete", "cluster"]:
        state.unlink(missing_ok=True)
    elif args[:2] == ["export", "kubeconfig"]:
        pathlib.Path(args[args.index("--kubeconfig") + 1]).write_text("kind kubeconfig")
elif tool == "docker":
    if args[:2] == ["context", "inspect"]:
        if os.environ.get("FAKE_DOCKER_CONTEXT_ERROR"):
            sys.exit(1)
        print(os.environ.get("DOCKER_HOST") or os.environ.get("FAKE_DOCKER_ENDPOINT", "unix:///var/run/docker.sock"))
    elif args[0] == "inspect":
        ports = {} if os.environ.get("FAKE_INCOMPATIBLE") else {
            str(port) + "/tcp": [{"HostPort": str(host), "HostIp": "127.0.0.1"}]
            for port, host in [(31080, 80), (31443, 443), (30080, 30080)]}
        print(json.dumps(ports))
elif tool == "kubectl":
    selected = state.parent / "selected-context"
    if args[:2] == ["config", "use-context"]:
        selected.touch()
    elif os.environ.get("FAKE_CURRENT_CONTEXT") and "--context=kind-kind" not in args and not selected.exists():
        sys.exit(71)
    if "rollout" in args and os.environ.get("FAKE_FAIL_ROLLOUT"):
        sys.exit(int(os.environ["FAKE_FAIL_ROLLOUT"]))
    if "--kubeconfig=/dev/stdin" in args:
        sys.stdin.read()
    if "config" in args and "view" in args:
        if args[-1] == "json":
            config = {"clusters": [{"name": "kind-kind", "cluster": {"server": "https://127.0.0.1:6443",
                "certificate-authority-data": "other-CA" if os.environ.get("FAKE_MISMATCH") else "CA"}}],
                "contexts": [{"name": "kind-kind", "context": {"cluster": "kind-kind", "user": "kind-kind"}}],
                "users": [{"name": "kind-kind", "user": {}}]}
            if os.environ.get("FAKE_SHARED_KUBECONFIG"):
                config[os.environ["FAKE_SHARED_KUBECONFIG"]].append({"name": "other"})
            print(json.dumps(config))
        else:
            print("other-cluster" if os.environ.get("FAKE_MISMATCH") and "--kubeconfig=/dev/stdin" not in args else "https://127.0.0.1:6443|CA")
    elif "deployments" in args:
        wanted = [("envoy-gateway-system", "envoy-gateway"), ("registry", "docker-registry"),
            ("tekton-pipelines", "tekton-pipelines-controller"), ("tekton-pipelines", "tekton-pipelines-webhook"),
            ("tekton-pipelines", "tekton-dashboard")] + [("pipelines-as-code", "pipelines-as-code-" + c)
            for c in ["controller", "watcher", "webhook"]]
        print(json.dumps({"items": [{"metadata": {"namespace": ns, "name": name, "generation": 2},
            "spec": {"replicas": 1}, "status": {"observedGeneration": 1 if os.environ.get("FAKE_STALE") else 2,
            "replicas": 2 if os.environ.get("FAKE_ROLLING_UPDATE") and name == "pipelines-as-code-watcher" else 1,
            "availableReplicas": 1, "updatedReplicas": 1}} for ns, name in wanted]}))
    elif args[0] == "apply" and os.environ.get("FAKE_APPLY_TARGET"):
        path = pathlib.Path(os.environ["KUBECONFIG"]).resolve()
        pathlib.Path(os.environ["FAKE_APPLY_TARGET"]).write_text(str(path))
    elif "get" in args and "ep" in args:
        print("127.0.0.1")
    elif any("jsonpath=" in arg for arg in args):
        print("1")
    elif "-f" in args and "-" in args:
        sys.stdin.read()
    elif "create" in args and "--dry-run=client" in args:
        print("{}")
elif tool == "curl":
    if os.environ.get("FAKE_FAIL_CURL"):
        sys.exit(1)
    if "-o" in args:
        pathlib.Path(args[args.index("-o") + 1]).write_text("{}")
elif tool == "helm":
    print("twuni")
elif tool == "ko":
    (state.parent / "ko-cwd").write_text(os.getcwd())
    if os.environ.get("FAKE_FAIL_KO"):
        print("build failed", file=sys.stderr)
        sys.exit(1)
    print("{}")
elif tool == "pass":
    if "--pinentry-mode error" not in os.environ.get("PASSWORD_STORE_GPG_OPTS", ""):
        sys.exit(90)
    counter = state.parent / "pass-count"
    count = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(count))
    if os.environ.get("FAKE_LOCKED") or count >= int(os.environ.get("FAKE_PASS_FAIL_AT", "999")):
        sys.exit(1)
    print("https://relay.example/RELAY-SENTINEL" if args[-1].endswith("/smee") else "SECRET-SENTINEL")
elif tool == "systemctl":
    sys.exit(1)
elif tool == "gum" and args[0] == "confirm":
    sys.exit(1)
'''


class AgentCliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = pathlib.Path(self.temp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.log = self.base / "commands"
        self.state = self.base / "cluster"
        self.pac = self.base / "pac"
        (self.pac / "config").mkdir(parents=True)
        (self.pac / "go.mod").touch()
        for manifest in ["400-controller.yaml", "500-watcher.yaml", "600-webhook.yaml"]:
            (self.pac / "config" / manifest).touch()
        self.secrets = self.base / "secrets"
        self.secrets.mkdir()
        for name in ["github-application-id", "github-private-key", "webhook.secret", "smee"]:
            (self.secrets / name).write_text("RELAY-SENTINEL" if name == "smee" else "SECRET-SENTINEL")
        certs = self.base / "certs"
        for domain in ["_.127.0.0.1.nip.io", "registry.127.0.0.1.nip.io"]:
            folder = certs / domain
            folder.mkdir(parents=True)
            (folder / "cert.pem").touch()
            (folder / "key.pem").touch()
        (certs / "minica.pem").touch()
        for tool in ["kind", "docker", "kubectl", "curl", "helm", "ko", "go", "minica", "git", "ping", "systemctl", "sleep", "gum"]:
            path = self.bin / tool
            path.write_text("#!" + sys.executable + "\n" + MOCK)
            path.chmod(0o755)
        self.env = {"PATH": str(self.bin) + ":/usr/bin:/bin", "HOME": str(self.home), "TARGET_HOST": "local",
            "PAC_DIR": str(self.pac), "PAC_SECRET_FOLDER": str(self.secrets),
            "STARTPAC_CONFIG_FILE": str(self.home / ".config/startpaac/config"),
            "CERT_DIR": str(certs), "FAKE_STATE": str(self.state), "FAKE_LOG": str(self.log)}

    def run_cli(self, *args, code=0, env=None, redacted=True, cwd=None):
        result = subprocess.run(["/bin/bash", str(ROOT / "startpaac"), *args],
            env=self.env if env is None else env, cwd=self.pac if cwd is None else cwd, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn("SECRET-SENTINEL", result.stdout + result.stderr)
        if redacted:
            self.assertNotIn("RELAY-SENTINEL", result.stdout + result.stderr)
        return result

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def mutations(self):
        return [cmd for cmd in self.commands() if cmd[0] == "kubectl" and
            any(action in cmd for action in ["create", "delete", "apply", "patch", "scale", "set"])]

    def existing_cluster(self, kubeconfig=True):
        self.state.write_text("existing-identity")
        if kubeconfig:
            folder = self.home / ".kube"
            folder.mkdir()
            (folder / "config.local").write_text("kind kubeconfig")

    def test_help_needs_no_dependencies_or_configuration(self):
        env = dict(self.env, PATH=str(self.bin / "absent"))
        self.assertIn("--up", self.run_cli("--help", env=env).stdout)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_install_skills_links_selected_agents_without_loading_config(self):
        config = pathlib.Path(self.env["STARTPAC_CONFIG_FILE"])
        config.parent.mkdir(parents=True)
        config.write_text("exit 99\n")
        for command in ["ln", "mkdir"]:
            (self.bin / command).symlink_to(shutil.which(command))
        env = dict(self.env, PATH=str(self.bin), NON_INTERACTIVE="true")
        skill = ROOT / "skills/startpaac"
        agents = self.home / ".agents/skills/startpaac"
        claude = self.home / ".claude/skills/startpaac"

        self.run_cli("--install-skills", "agents", env=env)
        self.assertTrue(agents.is_symlink())
        self.assertTrue(agents.samefile(skill))
        self.assertFalse(claude.parent.exists())
        self.run_cli("--install-skills=claude", env=env)
        self.assertTrue(claude.is_symlink())
        self.assertTrue(claude.samefile(skill))
        self.run_cli("--install-skills", "all", env=env)
        self.assertTrue(agents.samefile(skill))
        self.assertTrue(claude.samefile(skill))
        self.assertEqual(self.commands(), [])

    def test_install_skills_preserves_conflicting_destinations(self):
        agents = self.home / ".agents/skills/startpaac"
        claude = self.home / ".claude/skills/startpaac"
        claude.mkdir(parents=True)
        custom_skill = claude / "SKILL.md"
        custom_skill.write_text("custom skill")
        self.assertIn(str(claude), self.run_cli("--install-skills", "all", code=1).stderr)
        self.assertFalse(agents.parent.exists())
        self.assertEqual(list(claude.iterdir()), [custom_skill])
        self.assertEqual(custom_skill.read_text(), "custom skill")

        missing = self.home / "missing-skill"
        agents.parent.mkdir(parents=True)
        agents.symlink_to(missing)
        self.run_cli("--install-skills", "agents", code=1)
        self.assertEqual(agents.readlink(), missing)

    def test_describe_does_not_source_configuration(self):
        config = pathlib.Path(self.env["STARTPAC_CONFIG_FILE"])
        config.parent.mkdir(parents=True)
        marker = self.home / "sourced"
        config.write_text(f'touch "{marker}"\necho SECRET-SENTINEL\n')
        data = json.loads(self.run_cli("--describe", "--output", "json").stdout)
        self.assertEqual(data["schema_version"], 1)
        self.assertTrue(any(action["flag"] == "--up" for action in data["data"]["actions"]))
        self.assertFalse(marker.exists())
        self.assertEqual(self.commands(), [])

    def test_inspections_preserve_caller_temp_files(self):
        paths = {name: self.base / name for name in ["TMPFILE", "tmppac"]}
        for path in paths.values():
            path.write_text("caller file")
        config = pathlib.Path(self.env["STARTPAC_CONFIG_FILE"])
        config.parent.mkdir(parents=True)
        config.write_text("".join(f'{name}="{path}"\n' for name, path in paths.items()))
        env = dict(self.env, **{name: str(path) for name, path in paths.items()})
        for args, code in [(('--describe',), 0), (('--status',), 1), (('--up', '--plan'), 0)]:
            with self.subTest(args=args):
                self.run_cli(*args, "--output=json", code=code, env=env)
                self.assertEqual([path.read_text() for path in paths.values()], ["caller file"] * 2)

    def test_invalid_arguments_fail_before_configuration(self):
        for args in [("--all", "--output=json"), ("--up", "--stop-kind", "--output=json"),
                     ("-c", "typo", "--output=json"), ("--up", "--plan=unexpected", "--output=json"),
                     ("--install-skills=typo", "--output=json")]:
            with self.subTest(args=args):
                data = json.loads(self.run_cli(*args, code=2).stdout)
                self.assertEqual(data["errors"][0]["code"], "invalid_arguments")
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(self.commands(), [])

    def test_doctor_collects_failures_without_writing(self):
        for path in self.secrets.iterdir():
            path.unlink()
        data = json.loads(self.run_cli("--doctor", "--output=json", code=1).stdout)
        self.assertIn("credentials", [error["code"] for error in data["errors"]])
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(self.mutations(), [])
        self.assertFalse(self.state.exists())

    def test_configured_menu_conflict_returns_one_json_argument_error(self):
        config = pathlib.Path(self.env["STARTPAC_CONFIG_FILE"])
        config.parent.mkdir(parents=True)
        config.write_text("FORCE_INTERACTIVE=true\n")
        result = self.run_cli("--doctor", "--output=json", code=2)
        data = json.loads(result.stdout)
        self.assertEqual(data["errors"][0]["code"], "invalid_arguments")
        self.assertNotIn('"schema_version"', result.stderr)
        self.assertEqual(self.mutations(), [])

    def test_plan_lists_hooks_and_reuse_without_execution(self):
        self.existing_cluster(kubeconfig=False)
        hooks = self.home / ".config/startpaac/hooks"
        hooks.mkdir(parents=True)
        hook = hooks / "pre-all"
        hook.write_text("#!/bin/bash\ntouch SHOULD-NOT-EXIST\n")
        hook.chmod(0o755)
        data = json.loads(self.run_cli("--up", "--plan", "--output=json").stdout)
        self.assertEqual(data["data"]["steps"][0], "reuse-kind")
        self.assertIn(str(hook), data["data"]["hooks"])
        self.assertFalse((self.home / ".kube").exists())
        self.assertEqual(self.mutations(), [])

    def test_explicit_local_target_overrides_remote_configuration(self):
        config = pathlib.Path(self.env["STARTPAC_CONFIG_FILE"])
        config.parent.mkdir(parents=True)
        config.write_text("TARGET_HOST=remote.example\n")
        data = json.loads(self.run_cli("--up", "--plan", "local", "--output=json").stdout)
        self.assertEqual(data["target"]["host"], "local")
        self.assertEqual(self.mutations(), [])

    def test_missing_credentials_prevent_all_deployment_changes(self):
        self.existing_cluster()
        (self.secrets / "github-private-key").unlink()
        data = json.loads(self.run_cli("-p", "--non-interactive", "--output=json", code=1).stdout)
        self.assertIn("credentials", [error["code"] for error in data["errors"]])
        self.assertEqual(self.mutations(), [])

    def test_go_is_required_before_a_source_build(self):
        (self.bin / "go").unlink()
        for tool in ["cat", "jq", "sed", "mktemp"]:
            (self.bin / tool).symlink_to(shutil.which(tool))
        env = dict(self.env, PATH=str(self.bin))
        for args in [("--doctor",), ("--up", "--plan"), ("--up",)]:
            with self.subTest(args=args):
                data = json.loads(self.run_cli(*args, "--output=json", code=1, env=env).stdout)
                self.assertEqual([error["code"] for error in data["errors"]], ["tool_go"])
        self.assertFalse(self.state.exists())
        self.assertEqual(self.mutations(), [])

        self.existing_cluster()
        for args in [("-p", "--plan"), ("-c", "watcher", "--plan")]:
            with self.subTest(args=args):
                data = json.loads(self.run_cli(*args, "--output=json", code=1, env=env).stdout)
                self.assertEqual([error["code"] for error in data["errors"]], ["tool_go"])
        self.run_cli("--status", "--output=json", env=env)

    def test_up_creates_then_reuses_cluster_ignoring_preferences(self):
        preferences = self.home / ".config/startpaac/preferences.json"
        preferences.parent.mkdir(parents=True)
        preferences.write_text('{"pac":false,"forgejo":true,"postgresql":true}')
        first = json.loads(self.run_cli("--up", "--non-interactive", "--output=json").stdout)
        self.assertTrue(first["ok"])
        identity = self.state.read_text()
        second = json.loads(self.run_cli("--output=json", "--non-interactive", "--up").stdout)
        self.assertEqual(self.state.read_text(), identity)
        self.assertTrue(all(component["ready"] for component in second["data"]["components"]))
        commands = self.commands()
        self.assertEqual(sum(cmd[:3] == ["kind", "create", "cluster"] for cmd in commands), 1)
        self.assertFalse(any(cmd[:3] == ["kind", "delete", "cluster"] for cmd in commands))
        self.assertEqual(sum(cmd[0] == "ko" for cmd in commands), 2)
        self.assertFalse(any(cmd[:3] == ["kubectl", "delete", "secret"] for cmd in commands))
        self.assertFalse(any(cmd[0] == "systemctl" and "restart" in cmd for cmd in commands))
        self.assertFalse(any(cmd[0] == "helm" and "forgejo" in cmd for cmd in commands))

    def test_incompatible_cluster_is_preserved(self):
        self.existing_cluster()
        self.env["FAKE_INCOMPATIBLE"] = "1"
        data = json.loads(self.run_cli("--up", "--output=json", code=1).stdout)
        self.assertIn("cluster_compatible", [error["code"] for error in data["errors"]])
        self.assertEqual(self.state.read_text(), "existing-identity")
        self.assertEqual(self.mutations(), [])

    def test_teardown_refuses_another_clusters_kubeconfig(self):
        self.existing_cluster()
        self.env["FAKE_MISMATCH"] = "1"
        data = json.loads(self.run_cli("--stop-kind", "--output=json", code=1).stdout)
        self.assertIn("kubeconfig_mismatch", [error["code"] for error in data["errors"]])
        self.assertEqual(self.state.read_text(), "existing-identity")

    def test_teardown_preserves_a_shared_kubeconfig(self):
        self.existing_cluster()
        kubeconfig = self.home / ".kube/config.local"
        for section in ["clusters", "contexts", "users"]:
            with self.subTest(section=section):
                self.env["FAKE_SHARED_KUBECONFIG"] = section
                data = json.loads(self.run_cli("--stop-kind", "--output=json", code=1).stdout)
                self.assertIn("kubeconfig_mismatch", [error["code"] for error in data["errors"]])
                self.assertEqual(self.state.read_text(), "existing-identity")
                self.assertEqual(kubeconfig.read_text(), "kind kubeconfig")
                self.assertFalse(any(cmd[:3] == ["kind", "delete", "cluster"] for cmd in self.commands()))

    def test_setup_does_not_overwrite_kubeconfig_when_cluster_is_absent(self):
        self.existing_cluster()
        self.state.unlink()
        data = json.loads(self.run_cli("--up", "--output=json", code=1).stdout)
        self.assertIn("kubeconfig_exists", [error["code"] for error in data["errors"]])
        self.assertFalse(self.state.exists())
        self.assertEqual(self.mutations(), [])

    def test_component_redeployment_parses_later_modifiers(self):
        self.existing_cluster()
        self.run_cli("-cwatcher", "--output=json", "--non-interactive", "-Ocontroller")
        self.assertTrue(any(cmd[0] == "ko" and "-fconfig/500-watcher.yaml" in cmd for cmd in self.commands()))
        self.assertTrue(any(cmd[0] == "kubectl" and "--replicas=0" in cmd for cmd in self.commands()))
        self.assertTrue(any(cmd[0] == "kubectl" and "rollout" in cmd and "deployment/pipelines-as-code-watcher" in cmd for cmd in self.commands()))

    def test_component_redeployment_does_not_apply_full_install_manifest(self):
        self.existing_cluster()
        extra = self.pac / "pkg/test/nonoai/deployment.yaml"
        extra.parent.mkdir(parents=True)
        extra.touch()

        self.run_cli("-c", "watcher", "--output=json")
        self.run_cli("-p", "--output=json")
        component_build, full_build = [cmd for cmd in self.commands() if cmd[0] == "ko"]
        self.assertIn("-fconfig/500-watcher.yaml", component_build)
        self.assertNotIn(str(extra), component_build)
        self.assertIn(str(extra), full_build)

    def test_runtime_failure_still_emits_one_json_result(self):
        self.existing_cluster()
        for failure, status in [("FAKE_FAIL_KO", "1"), ("FAKE_FAIL_ROLLOUT", "1"), ("FAKE_FAIL_ROLLOUT", "2")]:
            with self.subTest(failure=failure, status=status):
                self.env[failure] = status
                data = json.loads(self.run_cli("-c", "watcher", "--output=json", code=1).stdout)
                self.assertEqual(data["errors"][0]["code"], "operation_failed")
                self.assertFalse(data["ok"])
                del self.env[failure]

    def test_explicit_teardown_needs_no_source_or_credentials(self):
        self.existing_cluster()
        del self.env["TARGET_HOST"]
        endpoint = "unix:///tmp/custom-docker.sock"
        self.env.update(PAC_DIR=str(self.base / "missing-source"), PAC_SECRET_FOLDER=str(self.base / "missing-secrets"))
        self.env.update(DOCKER_CONTEXT="alternate-local", FAKE_DOCKER_ENDPOINT=endpoint, FAKE_KIND_DOCKER_HOST=endpoint)
        plan = json.loads(self.run_cli("--stop-kind", "--plan", "--output=json").stdout)
        self.assertTrue(plan["data"]["destructive"])
        self.assertTrue(self.state.exists())
        self.run_cli("--stop-kind", "--non-interactive", "--output=json")
        self.assertFalse(self.state.exists())
        self.assertFalse((self.home / ".kube/config.local").exists())

    def test_managed_teardown_requires_a_local_docker_socket(self):
        self.existing_cluster()
        kubeconfig = self.home / ".kube/config.local"
        cases = [
            ({"DOCKER_HOST": "tcp://192.0.2.1:2375"}, "docker_endpoint_nonlocal"),
            ({"DOCKER_CONTEXT": "remote", "FAKE_DOCKER_ENDPOINT": "ssh://docker.example"}, "docker_endpoint_nonlocal"),
            ({"FAKE_DOCKER_CONTEXT_ERROR": "1"}, "docker_endpoint_unavailable"),
            ({"KIND_EXPERIMENTAL_PROVIDER": "podman"}, "kind_provider"),
        ]
        for overrides, error in cases:
            with self.subTest(overrides=overrides):
                env = dict(self.env, **overrides)
                for options in [("--plan",), ()]:
                    data = json.loads(self.run_cli("--stop-kind", *options, "--output=json", code=1, env=env).stdout)
                    self.assertIn(error, [issue["code"] for issue in data["errors"]])
                self.assertTrue(kubeconfig.is_file())
                self.assertTrue(self.state.exists())
        self.assertFalse(any(cmd[0] == "kind" for cmd in self.commands()))

    def test_legacy_actions_require_a_target_host(self):
        self.existing_cluster()
        for target in [None, ""]:
            env = dict(self.env)
            if target is None:
                del env["TARGET_HOST"]
            else:
                env["TARGET_HOST"] = target
            for args in [("--stop-kind",), ("--ci", "-a")]:
                with self.subTest(target=target, args=args):
                    result = self.run_cli(*args, code=1, env=env)
                    self.assertIn("TARGET_HOST", result.stdout + result.stderr)
                    self.assertEqual(self.state.read_text(), "existing-identity")
        self.assertFalse(any(cmd[0] == "kind" for cmd in self.commands()))

    def test_plain_up_leaves_existing_forwarder_in_place(self):
        self.existing_cluster()
        self.run_cli("--up")
        self.assertFalse(any(cmd[:3] == ["kubectl", "scale", "deployment"] and "gosmee-ghe" in cmd
            for cmd in self.commands()))

    def test_legacy_ci_install_preserves_explicit_recreation(self):
        self.env.update(INSTALL_FORGE="false", INSTALL_TEKTON_DASHBOARD="false")
        for args in [("--ci", "-a"), ("-a", "--ci")]:
            self.run_cli(*args, redacted=False)
        self.assertEqual(sum(cmd[:3] == ["kind", "delete", "cluster"] for cmd in self.commands()), 2)

    def test_redeploy_kind_stops_cluster_and_runs_hooks_once(self):
        hooks = self.home / ".config/startpaac/hooks"
        hooks.mkdir(parents=True)
        hook_log = self.base / "stop-hooks"
        for phase in ["pre", "post"]:
            hook = hooks / (phase + "-stop-kind")
            hook.write_text(f'#!/bin/bash\nprintf "%s\\n" {phase} >> "{hook_log}"\n')
            hook.chmod(0o755)
        self.run_cli("--redeploy-kind")
        self.assertEqual(hook_log.read_text().splitlines(), ["pre", "post"])
        self.assertEqual(sum(cmd[:3] == ["kind", "delete", "cluster"] for cmd in self.commands()), 1)

    def test_configured_modes_and_explicit_overrides(self):
        self.existing_cluster()
        config = pathlib.Path(self.env["STARTPAC_CONFIG_FILE"])
        config.parent.mkdir(parents=True)
        preferences = config.parent / "preferences.json"
        cases = [
            ('CI_MODE=true', {}, (), 0, False, False, False),
            ('CI_MODE=${CI_MODE:-true}', {}, (), 0, False, False, False),
            ('CI_MODE=false', {}, ("--ci",), 0, False, False, False),
            ('CI_MODE=true', {"CI_MODE": "false"}, (), 1, True, False, False),
            ('FORCE_INTERACTIVE=true', {}, (), 1, True, False, True),
            ('FORCE_INTERACTIVE=true', {"FORCE_INTERACTIVE": "false"}, (), 1, False, False, True),
            ('NON_INTERACTIVE=true', {}, ("-c", "watcher"), 0, False, True, False),
            ('NON_INTERACTIVE=true', {"NON_INTERACTIVE": "false"}, ("-c", "watcher"), 0, False, False, False),
            ('NON_INTERACTIVE=false', {}, ("-c", "watcher", "--non-interactive"), 0, False, True, False),
        ]
        for content, overrides, args, code, choose, managed, saved in cases:
            with self.subTest(config=content, overrides=overrides, args=args):
                config.write_text(content + "\n")
                self.log.unlink(missing_ok=True)
                if saved:
                    preferences.write_text('{"pac":true}')
                else:
                    preferences.unlink(missing_ok=True)
                env = dict(self.env, INSTALL_FORGE="false", INSTALL_TEKTON_DASHBOARD="false",
                    PAC_PASS_SECOND_FOLDER="test/app", **overrides)
                self.run_cli(*args, code=code, env=env, redacted=False)
                self.assertEqual(any(cmd[:2] == ["gum", "choose"] for cmd in self.commands()), choose)
                self.assertEqual(any(cmd[:3] == ["kubectl", "config", "use-context"] for cmd in self.commands()), managed)

    def test_named_kind_context_is_used_for_inspection_and_deployment(self):
        self.existing_cluster()
        self.env["FAKE_CURRENT_CONTEXT"] = "unset-or-other"
        original = (self.home / ".kube/config.local").read_text()
        self.run_cli("--status", "--output=json")
        self.assertEqual((self.home / ".kube/config.local").read_text(), original)
        self.assertFalse((self.base / "selected-context").exists())
        self.run_cli("-c", "watcher", "--output=json")
        self.assertTrue((self.base / "selected-context").exists())

    def test_relative_paths_use_the_same_kubeconfig_and_hooks_as_preflight(self):
        self.existing_cluster(kubeconfig=False)
        invocation = self.base / "invocation"
        invocation.mkdir()
        expected_hook = invocation / "hooks/pre-install-pac"
        hook_log = self.base / "hook-log"
        applied_target = self.base / "apply-target"
        for directory in [invocation, self.pac]:
            (directory / "kubeconfig").write_text(str(directory))
            hook = directory / "hooks/pre-install-pac"
            hook.parent.mkdir()
            hook.write_text(f'#!/bin/bash\necho "$0" >> "{hook_log}"\n')
            hook.chmod(0o755)
        config = pathlib.Path(self.env["STARTPAC_CONFIG_FILE"])
        config.parent.mkdir(parents=True)
        config.write_text("KUBECONFIG=kubeconfig\nHOOKS_DIR=hooks\nPAC_DIR=../pac\n")
        env = dict(self.env, FAKE_APPLY_TARGET=str(applied_target))

        plan = json.loads(self.run_cli("-c", "watcher", "--plan", "--output=json", env=env, cwd=invocation).stdout)
        self.assertFalse(hook_log.exists())
        self.run_cli("-c", "watcher", "--output=json", env=env, cwd=invocation)
        self.assertEqual(applied_target.read_text(), str(invocation / "kubeconfig"))
        self.assertEqual(hook_log.read_text().splitlines(), [str(expected_hook)])
        self.assertEqual(plan["target"]["kubeconfig"], str(invocation / "kubeconfig"))
        self.assertEqual(plan["data"]["hooks"], [str(expected_hook)])
        source = pathlib.Path(plan["data"]["pac_dir"])
        self.assertTrue(source.is_absolute())
        self.assertEqual(source.resolve(), self.pac)

        hook_log.unlink()
        applied_target.unlink()
        config.write_text(config.read_text() + "NON_INTERACTIVE=true\n")
        self.run_cli("-c", "watcher", env=env, cwd=invocation)
        self.assertEqual(applied_target.read_text(), str(invocation / "kubeconfig"))
        self.assertEqual(hook_log.read_text().splitlines(), [str(expected_hook)])

    def test_legacy_deployment_respects_pac_dir_in_another_repository(self):
        unrelated = self.base / "unrelated"
        (unrelated / "config").mkdir(parents=True)
        self.env["FAKE_GIT_ROOT"] = str(unrelated)
        env = dict(self.env, STARTPAAC_CREATE_CONFIG="false")
        del env["PAC_DIR"]
        self.run_cli("-c", "watcher", env=env, cwd=unrelated, code=1)
        self.assertFalse(any(cmd[0] == "ko" for cmd in self.commands()))
        self.run_cli("-c", "watcher", cwd=unrelated)
        self.assertEqual((self.base / "ko-cwd").read_text(), str(self.pac))
        config = pathlib.Path(self.env["STARTPAC_CONFIG_FILE"])
        config.parent.mkdir(parents=True)
        config.write_text(f'PAC_DIR="{self.pac}"\n')
        self.run_cli("-c", "watcher", env=env, cwd=unrelated)
        self.assertEqual((self.base / "ko-cwd").read_text(), str(self.pac))
        self.assertFalse(any(cmd[:3] == ["kind", "delete", "cluster"] for cmd in self.commands()))

    def test_hook_wrapper_stops_installers_and_preserves_checked_failures(self):
        marker = self.base / "must-not-run"
        hooks = self.home / ".config/startpaac/hooks"
        hooks.mkdir(parents=True)
        post = hooks / "post-test"
        post.write_text(f'#!/bin/bash\ntouch "{marker}"\n')
        post.chmod(0o755)
        scripts = [
            ('installer() { false; touch "$1"; }; run_with_hooks test installer "$2"', 1),
            ('installer() { return 42; }; if run_with_hooks test installer; then exit 99; else exit $?; fi', 42),
        ]
        for script, code in scripts:
            with self.subTest(script=script):
                result = subprocess.run(["/bin/bash", "-ec", 'source "$1/lib/common.sh"; ' + script, "bash", str(ROOT), str(marker)],
                    env=self.env, capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                self.assertFalse(marker.exists())

    def test_status_does_not_claim_stale_deployments_are_ready(self):
        self.existing_cluster()
        self.env["FAKE_STALE"] = "1"
        data = json.loads(self.run_cli("--status", "--output=json", code=1).stdout)
        self.assertTrue(all(not component["ready"] for component in data["data"]["components"]))
        self.assertEqual(data["data"]["webhook_delivery"], "unverified")
        self.assertEqual(self.mutations(), [])

    def test_status_waits_for_old_replicas_to_leave_a_rollout(self):
        self.existing_cluster()
        self.env["FAKE_ROLLING_UPDATE"] = "1"
        data = json.loads(self.run_cli("--status", "--output=json", code=1).stdout)
        unready = [component["name"] for component in data["data"]["components"] if not component["ready"]]
        self.assertEqual(unready, ["pipelines-as-code-watcher"])
        self.assertIn("components_not_ready", [error["code"] for error in data["errors"]])

    def configure_pass(self):
        path = self.bin / "pass"
        path.write_text("#!" + sys.executable + "\n" + MOCK)
        path.chmod(0o755)
        self.env.update(PAC_SECRET_STORAGE="pass", PAC_PASS_SECRET_FOLDER="test/app")

    def test_locked_pass_reports_failure_without_prompting(self):
        self.configure_pass()
        self.env["FAKE_LOCKED"] = "1"
        self.run_cli("--up", "--output=json", code=1)
        self.assertEqual(self.mutations(), [])

    def test_credentials_lost_during_read_do_not_delete_cluster_secret(self):
        self.existing_cluster()
        self.configure_pass()
        for failure_at in [9, 12]:
            with self.subTest(failure_at=failure_at):
                self.env["FAKE_PASS_FAIL_AT"] = str(failure_at)
                (self.base / "pass-count").unlink(missing_ok=True)
                self.run_cli("-p", "--output=json", code=1)
                self.assertFalse(any("secret" in cmd for cmd in self.mutations()))

    def test_registry_timeout_returns_failure(self):
        self.env["FAKE_FAIL_CURL"] = "1"
        result = subprocess.run(["/bin/bash", "-c", 'source "$1/lib/common.sh"; wait_for_registry https://registry.invalid/v2/ 0', "bash", str(ROOT)],
            env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertIn("timed out", result.stderr)
        curl = next(cmd for cmd in self.commands() if cmd[0] == "curl")
        self.assertIn("--max-time", curl)


if __name__ == "__main__":
    unittest.main()
