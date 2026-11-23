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
    if args and args[0] == "apply":
        with open(state.parent / "applied", "a") as applied:
            for index, arg in enumerate(args[:-1]):
                if arg == "-f" and args[index + 1] != "-":
                    applied.write("# " + args[index + 1] + "\n" + pathlib.Path(args[index + 1]).read_text() + "\n")
                    if args[index + 1].endswith("kueue-config.yaml"):
                        (state.parent / "kueue-config").write_text(pathlib.Path(args[index + 1]).read_text())
    if "--kubeconfig=/dev/stdin" in args:
        sys.stdin.read()
    if "config" in args and "view" in args:
        if args[-1] == "json":
            config = {"clusters": [{"name": "kind-kind", "cluster": {"server": "https://127.0.0.1:6443",
                "certificate-authority-data": "other-CA" if os.environ.get("FAKE_MISMATCH") else "CA"}}],
                "contexts": [{"name": "kind-kind", "context": {"cluster": "kind-kind", "user": "kind-kind"}}],
                "users": [{"name": "kind-kind", "user": {}}]}
            if os.environ.get("FAKE_CA_FILE"):
                cluster = config["clusters"][0]["cluster"]
                ca_file = os.environ["FAKE_CA_FILE"]
                if "--flatten" in args:
                    cluster["certificate-authority-data"] = (pathlib.Path(os.environ["KUBECONFIG"]).parent / ca_file).read_text()
                else:
                    del cluster["certificate-authority-data"]
                    cluster["certificate-authority"] = ca_file
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
        items = [{"metadata": {"namespace": ns, "name": name, "generation": 2},
            "spec": {"replicas": 1}, "status": {"observedGeneration": 1 if os.environ.get("FAKE_STALE") else 2,
            "replicas": 2 if os.environ.get("FAKE_ROLLING_UPDATE") and name == "pipelines-as-code-watcher" else 1,
            "availableReplicas": 1, "updatedReplicas": 1}} for ns, name in wanted]
        for index in range(int(os.environ.get("FAKE_MANY_DEPLOYMENTS", "0"))):
            items.append({"metadata": {"namespace": "filler", "name": "filler-%d" % index, "generation": 1,
                "annotations": {"payload": "x" * 2048}}, "spec": {"replicas": 1}, "status": {}})
        print(json.dumps({"items": items}))
    elif args[0] == "apply" and os.environ.get("FAKE_APPLY_TARGET"):
        path = pathlib.Path(os.environ["KUBECONFIG"]).resolve()
        pathlib.Path(os.environ["FAKE_APPLY_TARGET"]).write_text(str(path))
    elif args[:3] == ["get", "configmap", "kueue-manager-config"]:
        if (state.parent / "kueue-config").exists():
            print((state.parent / "kueue-config").read_text())
    elif args[:2] == ["get", "namespaces"] and "-l" in args:
        print(os.environ.get("FAKE_KUEUE_NAMESPACES", ""))
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
        body = "{}"
        if any("tekton-kueue" in arg for arg in args):
            body = "webhooks:\n  - admissionReviewVersions:\n      - v1\n    name: pipelinerun-kueue-defaulter.tekton-kueue.io\n"
        pathlib.Path(args[args.index("-o") + 1]).write_text(body)
elif tool == "helm":
    if os.environ.get("FAKE_HELM_CHECK_TARGET") and (
        os.environ.get("HELM_KUBECONTEXT") != "kind-kind"
        or any(name.startswith("HELM_KUBE") and name != "HELM_KUBECONTEXT" for name in os.environ)
    ):
        sys.exit(64)
    envoy_release = state.parent / "envoy-helm-release"
    if args[0] == "list" and envoy_release.exists():
        print("envoy-gateway")
    elif args[0] in ["install", "upgrade"] and "envoy-gateway" in args:
        envoy_release.touch()
    elif args[0] in ["repo", "status"]:
        print("twuni")
elif tool == "ko":
    (state.parent / "ko-cwd").write_text(os.getcwd())
    if os.environ.get("FAKE_FAIL_KO"):
        print("build failed", file=sys.stderr)
        sys.exit(1)
    print("{}")
elif tool == "systemctl":
    sys.exit(0 if os.environ.get("FAKE_FORWARDER_RUNNING") and "is-active" in args else 1)
elif tool == "gum" and args[0] == "choose":
    print(os.environ.get("FAKE_GUM_CHOICES", ""))
elif tool == "gum" and args[0] == "confirm":
    sys.exit(0 if os.environ.get("FAKE_GUM_YES") and os.environ["FAKE_GUM_YES"] in args[-1] else 1)
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
        self.e2e_config = self.base / "e2e-config.yaml"
        self.e2e_config.write_text(
            "common:\n"
            "  webhook_secret: SECRET-SENTINEL\n"
            "github:\n"
            "  application_id: SECRET-SENTINEL\n"
            "  private_key: |\n"
            "    SECRET-SENTINEL\n"
            "  smee_url: https://relay.example/RELAY-SENTINEL\n"
        )
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
            "PAC_DIR": str(self.pac), "PAC_E2E_CONFIG": str(self.e2e_config),
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
        self.e2e_config.write_text("common:\n  webhook_secret: ''\n")
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

    def test_text_plan_lists_target_and_effects(self):
        self.existing_cluster()
        hook = self.home / ".config/startpaac/hooks/pre-install-pac"
        hook.parent.mkdir(parents=True)
        hook.touch(mode=0o755)
        result = self.run_cli("-c", "watcher", "-O", "controller", "--plan")
        for detail in ["Target: local / kind", f"Kubeconfig: {self.home / '.kube/config.local'}",
                       f"PAC checkout: {self.pac}", "Component: watcher", f"Hook: {hook}", "Scale down: controller"]:
            self.assertIn(detail, result.stdout)
        result = self.run_cli("--stop-kind", "--plan")
        self.assertIn("Deletes the Kind cluster and its kubeconfig", result.stdout)
        self.assertEqual(self.mutations(), [])
        self.assertTrue(self.state.exists())

    def test_explicit_local_target_overrides_remote_configuration(self):
        config = pathlib.Path(self.env["STARTPAC_CONFIG_FILE"])
        config.parent.mkdir(parents=True)
        config.write_text("TARGET_HOST=remote.example\n")
        data = json.loads(self.run_cli("--up", "--plan", "local", "--output=json").stdout)
        self.assertEqual(data["target"]["host"], "local")
        self.assertEqual(self.mutations(), [])

    def test_missing_credentials_prevent_all_deployment_changes(self):
        self.existing_cluster()
        self.e2e_config.write_text("common:\n  webhook_secret: SECRET-SENTINEL\ngithub:\n  application_id: SECRET-SENTINEL\n")
        data = json.loads(self.run_cli("-p", "--non-interactive", "--output=json", code=1).stdout)
        self.assertIn("credentials", [error["code"] for error in data["errors"]])
        self.assertEqual(self.mutations(), [])

    def test_go_is_required_before_a_source_build(self):
        (self.bin / "go").unlink()
        for tool in ["cat", "jq", "sed", "mktemp"]:
            (self.bin / tool).symlink_to(shutil.which(tool))
        yaml_tool = shutil.which("yq") or shutil.which("python3")
        (self.bin / pathlib.Path(yaml_tool).name).symlink_to(yaml_tool)
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
        gateway_installs = [cmd for cmd in commands if cmd[:2] == ["helm", "install"] and "envoy-gateway" in cmd]
        self.assertEqual(len(gateway_installs), 1)
        self.assertFalse(any(cmd[:2] == ["helm", "upgrade"] for cmd in commands))

    def test_up_pins_helm_to_the_validated_kind_context(self):
        self.existing_cluster()
        config = pathlib.Path(self.env["STARTPAC_CONFIG_FILE"])
        config.parent.mkdir(parents=True)
        config.write_text("export HELM_KUBEAPISERVER=https://other.example\n")
        env = dict(self.env, FAKE_HELM_CHECK_TARGET="1", HELM_KUBECONTEXT="other", HELM_KUBECAFILE="custom-ca.crt")
        self.run_cli("--up", "--output=json", env=env)

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

    def test_preflight_accepts_a_matching_ca_file(self):
        self.existing_cluster()
        ca_file = self.home / ".kube/kind-ca.crt"
        ca_file.write_text("CA")
        self.env["FAKE_CA_FILE"] = ca_file.name
        self.run_cli("--stop-kind", "--plan", "--output=json")
        ca_file.write_text("other-CA")
        result = self.run_cli("--stop-kind", "--plan", "--output=json", code=1)
        self.assertIn("kubeconfig_mismatch", [issue["code"] for issue in json.loads(result.stdout)["errors"]])
        self.assertTrue(self.state.exists())

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
        self.env.update(PAC_DIR=str(self.base / "missing-source"), PAC_E2E_CONFIG=str(self.base / "missing-e2e.yaml"))
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
                env = dict(self.env, INSTALL_FORGE="false", INSTALL_TEKTON_DASHBOARD="false", **overrides)
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

    def test_status_reads_a_deployment_list_larger_than_one_argument(self):
        self.existing_cluster()
        self.env["FAKE_MANY_DEPLOYMENTS"] = "200"
        data = json.loads(self.run_cli("--status", "--output=json").stdout)
        self.assertTrue(data["ok"])
        self.assertIn("pipelines-as-code-watcher",
            [component["name"] for component in data["data"]["components"] if component["ready"]])

    def test_status_waits_for_old_replicas_to_leave_a_rollout(self):
        self.existing_cluster()
        self.env["FAKE_ROLLING_UPDATE"] = "1"
        data = json.loads(self.run_cli("--status", "--output=json", code=1).stdout)
        unready = [component["name"] for component in data["data"]["components"] if not component["ready"]]
        self.assertEqual(unready, ["pipelines-as-code-watcher"])
        self.assertIn("components_not_ready", [error["code"] for error in data["errors"]])

    def test_text_status_reports_registry_and_forwarder_state(self):
        self.existing_cluster()
        result = self.run_cli("--status")
        self.assertIn("Registry: https://registry.127.0.0.1.nip.io (ready)", result.stdout)
        self.assertIn("Webhook forwarder: unverified", result.stdout)

        self.env.update(FAKE_FAIL_CURL="1", FAKE_FORWARDER_RUNNING="1")
        result = self.run_cli("--status", code=1)
        self.assertIn("Registry: https://registry.127.0.0.1.nip.io (unavailable)", result.stdout)
        self.assertIn("Webhook forwarder: running", result.stdout)
        self.assertIn("Webhook delivery: unverified", result.stdout)

    def test_plain_up_preserves_cluster_credentials_when_access_is_lost(self):
        self.existing_cluster()
        hook = self.home / ".config/startpaac/hooks/pre-configure-pac"
        hook.parent.mkdir(parents=True)
        hook.write_text(f'#!/bin/bash\nrm "{self.e2e_config}"\n')
        hook.chmod(0o755)

        result = self.run_cli("--up", code=1, env=dict(self.env, NON_INTERACTIVE="false"))
        self.assertFalse(self.e2e_config.exists())
        self.assertIn("existing cluster secrets were left unchanged", result.stdout)
        self.assertFalse(any("secret" in cmd and "pipelines-as-code-secret" in cmd for cmd in self.mutations()))

    def test_registry_timeout_returns_failure(self):
        self.env["FAKE_FAIL_CURL"] = "1"
        result = subprocess.run(["/bin/bash", "-c", 'source "$1/lib/common.sh"; wait_for_registry https://registry.invalid/v2/ 0', "bash", str(ROOT)],
            env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertIn("timed out", result.stderr)
        curl = next(cmd for cmd in self.commands() if cmd[0] == "curl")
        self.assertIn("--max-time", curl)

    def write_e2e_config(self, path, include_primary=True, include_ghe=True):
        sections = []
        if include_primary:
            sections.append(
                "common:\n"
                "  webhook_secret: yaml-secret\n"
                "github:\n"
                "  application_id: '11111'\n"
                "  private_key: |\n"
                "    -----BEGIN RSA PRIVATE KEY-----\n"
                "    TESTKEY\n"
                "    -----END RSA PRIVATE KEY-----\n"
                "  smee_url: https://hook.pipelinesascode.com/yaml-test\n"
            )
        else:
            sections.append("common:\n  webhook_secret: ''\ngithub:\n  application_id: ''\n")
        if include_ghe:
            sections.append(
                "github_enterprise:\n"
                "  api_url: https://ghe.example.com/api/v3\n"
                "  application_id: '22222'\n"
                "  private_key: |\n"
                "    -----BEGIN RSA PRIVATE KEY-----\n"
                "    GHEKEY\n"
                "    -----END RSA PRIVATE KEY-----\n"
                "  webhook_secret: ghe-secret\n"
                "  smee_url: https://hook.pipelinesascode.com/yaml-ghe\n"
            )
        path.write_text("".join(sections))
        return path

    def test_e2e_config_flag_satisfies_doctor(self):
        cfg = self.write_e2e_config(self.base / "e2e-config-flag.yaml")
        env = dict(self.env)
        env.pop("PAC_E2E_CONFIG", None)
        (self.base / "config").write_text(f"PAC_DIR={self.pac}\nTARGET_HOST=local\n")
        data = json.loads(self.run_cli("--doctor", "--e2e-config", str(cfg), "--output=json", env=env).stdout)
        self.assertTrue(data["ok"], data)
        checks = {c["id"]: c["ok"] for c in data["data"]["checks"]}
        self.assertTrue(checks.get("e2e_config_file"))
        self.assertTrue(checks.get("tool_yaml_parser"))
        self.assertTrue(checks.get("credentials"))

    def test_e2e_config_env_var_works_with_relative_path(self):
        cfg = self.write_e2e_config(self.base / "rel-e2e.yaml")
        env = dict(self.env, PAC_E2E_CONFIG=cfg.name)
        (self.base / "config").write_text(f"PAC_DIR={self.pac}\nTARGET_HOST=local\n")
        result = subprocess.run(
            [str(ROOT / "startpaac"), "--doctor", "--output=json"],
            cwd=str(self.base), env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["ok"], data)

    def test_e2e_config_missing_file_fails_doctor(self):
        missing = self.base / "does-not-exist.yaml"
        data = json.loads(
            self.run_cli("--doctor", f"--e2e-config={missing}", "--output=json", code=1).stdout
        )
        self.assertFalse(data["ok"])
        codes = {e["code"] for e in data["errors"]}
        self.assertIn("e2e_config_file", codes)
        self.assertIn("credentials", codes)

    def test_e2e_config_install_paac_applies_secret_from_yaml(self):
        self.existing_cluster()
        cfg = self.write_e2e_config(self.base / "e2e-config-install.yaml")
        env = dict(self.env)
        env.pop("PAC_E2E_CONFIG", None)
        (self.base / "config").write_text(f"PAC_DIR={self.pac}\nTARGET_HOST=local\n")
        data = json.loads(self.run_cli("-p", f"--e2e-config={cfg}", "--output=json", env=env).stdout)
        self.assertTrue(data["ok"], data)
        self.assertTrue(
            any("create" in cmd and "pipelines-as-code-secret" in cmd for cmd in self.commands())
        )

    def test_e2e_config_requires_value(self):
        data = json.loads(self.run_cli("--doctor", "--e2e-config", "--output=json", code=2).stdout)
        self.assertEqual(data["errors"][0]["code"], "invalid_arguments")

    def test_configure_pac_target_accepts_relative_yaml_and_rejects_malformed_without_deleting(self):
        self.existing_cluster()
        cfg = self.write_e2e_config(self.base / "target-e2e.yaml")
        kubeconfig = self.base / "kubeconfig"
        kubeconfig.write_text("apiVersion: v1\nkind: Config\n")
        result = subprocess.run(
            [str(ROOT / "startpaac"), "--configure-pac-target", str(kubeconfig), "pipelines-as-code", cfg.name],
            cwd=str(self.base), env=self.env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(
            any("create" in cmd and "pipelines-as-code-secret" in cmd for cmd in self.commands())
        )

        # Positional config must take precedence even when the configured PAC_E2E_CONFIG is missing.
        (self.base / "commands").unlink(missing_ok=True)
        missing_env = dict(self.env, PAC_E2E_CONFIG=str(self.base / "stale-missing.yaml"))
        result = subprocess.run(
            [str(ROOT / "startpaac"), "--configure-pac-target", str(kubeconfig), "pipelines-as-code", cfg.name],
            cwd=str(self.base), env=missing_env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(
            any("create" in cmd and "pipelines-as-code-secret" in cmd for cmd in self.commands())
        )

        # Malformed YAML must fail nonzero and never delete pipelines-as-code-secret.
        (self.base / "commands").unlink(missing_ok=True)
        bad = self.base / "bad-target.yaml"
        bad.write_text("github:\n  application_id: [unterminated\n")
        result = subprocess.run(
            [str(ROOT / "startpaac"), "--configure-pac-target", str(kubeconfig), "pipelines-as-code", bad.name],
            cwd=str(self.base), env=self.env, capture_output=True, text=True, timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(
            any("delete" in cmd and "pipelines-as-code-secret" in cmd for cmd in self.commands())
        )

        # Missing relative file in cwd must NOT fall back to a same-named file inside PAC_DIR.
        (self.base / "commands").unlink(missing_ok=True)
        self.write_e2e_config(self.pac / "shadow.yaml")
        result = subprocess.run(
            [str(ROOT / "startpaac"), "--configure-pac-target", str(kubeconfig), "pipelines-as-code", "shadow.yaml"],
            cwd=str(self.base), env=self.env, capture_output=True, text=True, timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(
            any("pipelines-as-code-secret" in cmd for cmd in self.commands())
        )

    def test_configure_pac_with_malformed_env_yaml_fails_without_deleting_secret(self):
        self.existing_cluster()
        bad = self.base / "bad-env.yaml"
        bad.write_text("github:\n  application_id: [unterminated\n")
        env = dict(self.env, PAC_E2E_CONFIG=str(bad))
        result = subprocess.run(
            [str(ROOT / "startpaac"), "--configure-pac"],
            cwd=str(self.base), env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(
            any("delete" in cmd and "pipelines-as-code-secret" in cmd for cmd in self.commands())
        )

    def test_e2e_config_override_supplies_missing_field_and_validates_existence(self):
        base = self.base / "base-no-smee.yaml"
        base.write_text(
            "common:\n"
            "  webhook_secret: yaml-secret\n"
            "github:\n"
            "  application_id: '11111'\n"
            "  private_key: |\n"
            "    -----BEGIN RSA PRIVATE KEY-----\n"
            "    TESTKEY\n"
            "    -----END RSA PRIVATE KEY-----\n"
        )
        overlay = self.base / "overlay.yaml"
        overlay.write_text("github:\n  smee_url: https://hook.pipelinesascode.com/overlay-test\n")
        env = dict(self.env, PAC_E2E_CONFIG=str(base))
        result = subprocess.run(
            [str(ROOT / "startpaac"), "--doctor", "--e2e-config-override", overlay.name, "--output=json"],
            cwd=str(self.base), env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["ok"], data)
        checks = {c["id"]: c["ok"] for c in data["data"]["checks"]}
        self.assertTrue(checks.get("e2e_config_override"))
        self.assertTrue(checks.get("credentials"))

        missing = self.base / "missing-overlay.yaml"
        data = json.loads(
            self.run_cli("--doctor", f"--e2e-config-override={missing}", "--output=json", code=1).stdout
        )
        self.assertFalse(data["ok"])
        self.assertIn("e2e_config_override", {e["code"] for e in data["errors"]})

    def test_e2e_config_override_requires_value(self):
        data = json.loads(self.run_cli("--doctor", "--e2e-config-override", "--output=json", code=2).stdout)
        self.assertEqual(data["errors"][0]["code"], "invalid_arguments")

    def kueue_commands(self):
        return [cmd for cmd in self.commands() if any("kueue" in arg for arg in cmd)]

    def test_install_kueue_is_a_legacy_action(self):
        self.assertIn("--install-kueue", self.run_cli("--help").stdout)
        self.assertIn("--install-kueue", (ROOT / "misc/_startpaac").read_text())
        for args in [("--install-kueue", "--non-interactive"), ("--install-kueue", "--plan"), ("--install-kueue=x",),
                ("--install-kueue", "--install-tekton")]:
            with self.subTest(args=args):
                self.run_cli(*args, code=2)

    def test_install_kueue_deploys_scoped_queue_with_hooks(self):
        self.existing_cluster()
        hooks = self.home / ".config/startpaac/hooks"
        hooks.mkdir(parents=True)
        hook_log = self.base / "kueue-hooks"
        for phase in ["pre", "post"]:
            hook = hooks / (phase + "-install-kueue")
            hook.write_text(f'#!/bin/bash\nprintf "%s\\n" {phase} >> "{hook_log}"\n')
            hook.chmod(0o755)
        self.env.update(KUEUE_NAMESPACES="default sample", FAKE_KUEUE_NAMESPACES="default old")
        self.run_cli("--install-kueue", redacted=False)
        self.assertEqual(hook_log.read_text().splitlines(), ["pre", "post"])
        commands = self.commands()
        for version in ["cert-manager/releases/download/v1.19.2/", "kueue/releases/download/v0.16.6/",
                "tekton-kueue/previous/v0.4.3/"]:
            self.assertTrue(any(cmd[0] == "curl" and any(version in arg for arg in cmd) for cmd in commands), version)
        for namespace, name in [("cert-manager", "cert-manager-webhook"), ("kueue-system", "kueue-controller-manager"),
                ("tekton-kueue", "tekton-kueue-webhook")]:
            self.assertIn(["kubectl", "rollout", "status", "deployment/" + name, "-n", namespace, "--timeout=300s"], commands)
        applied = (self.base / "applied").read_text()
        self.assertIn("    name: pipelinerun-kueue-defaulter.tekton-kueue.io\n    namespaceSelector:\n"
            "      matchLabels:\n        startpaac.dev/kueue: enabled\n", applied)
        self.assertIn("- PipelineRun.v1.tekton.dev", applied)
        self.assertIn("nominalQuota: 1", applied)
        for namespace in ["default", "sample"]:
            self.assertIn(["kubectl", "label", "namespace", namespace, "startpaac.dev/kueue=enabled", "--overwrite"], commands)
            self.assertIn(["kubectl", "apply", "-n", namespace, "-f", "-"], commands)
        self.assertIn(["kubectl", "label", "namespace", "old", "startpaac.dev/kueue-"], commands)
        self.assertIn(["kubectl", "delete", "localqueue", "pipelines-queue", "-n", "old", "--ignore-not-found"], commands)
        self.assertFalse(any(cmd[:4] == ["kubectl", "label", "namespace", "default"] and "startpaac.dev/kueue-" in cmd
            for cmd in commands))

    def test_kueue_restarts_only_when_its_configuration_changes(self):
        self.existing_cluster()
        restart = ["kubectl", "rollout", "restart", "deployment/kueue-controller-manager", "-n", "kueue-system"]
        cases = [("fresh install", None, True), ("unchanged", "same", False), ("changed", "old configuration", True)]
        for name, before, restarted in cases:
            with self.subTest(name):
                if before == "old configuration":
                    (self.base / "kueue-config").write_text(before)
                self.log.unlink(missing_ok=True)
                self.run_cli("--install-kueue", redacted=False)
                self.assertEqual(restart in self.commands(), restarted)

    def test_install_kueue_stops_when_a_controller_is_not_ready(self):
        self.existing_cluster()
        hooks = self.home / ".config/startpaac/hooks"
        hooks.mkdir(parents=True)
        marker = self.base / "post-hook-ran"
        hook = hooks / "post-install-kueue"
        hook.write_text(f'#!/bin/bash\ntouch "{marker}"\n')
        hook.chmod(0o755)
        self.env["FAKE_FAIL_ROLLOUT"] = "3"
        result = subprocess.run(["/bin/bash", str(ROOT / "startpaac"), "--install-kueue"], env=self.env, cwd=self.pac,
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(marker.exists())
        self.assertFalse(any(cmd[:2] == ["kubectl", "label"] for cmd in self.commands()))
        self.assertNotIn("startpaac-pipelines", (self.base / "applied").read_text())

    def test_kueue_is_off_by_default_and_saved_from_the_menu(self):
        preferences = self.home / ".config/startpaac/preferences.json"
        env = dict(self.env, FAKE_GUM_YES="Save")
        self.run_cli(code=1, env=env, redacted=False)
        choose = [cmd for cmd in self.commands() if cmd[:2] == ["gum", "choose"]][-1]
        self.assertFalse(any("Kueue" in arg for arg in choose))
        self.assertFalse(json.loads(preferences.read_text())["kueue"])

        env["FAKE_GUM_CHOICES"] = "Kueue"
        self.run_cli("--menu", code=1, env=env, redacted=False)
        self.assertTrue(json.loads(preferences.read_text())["kueue"])
        self.assertEqual(self.kueue_commands(), [])

    def test_saved_kueue_preference_installs_it_in_full_runs_but_not_up(self):
        preferences = self.home / ".config/startpaac/preferences.json"
        preferences.parent.mkdir(parents=True)
        preferences.write_text('{"pac":false,"tekton_dashboard":false,"forgejo":false,"kueue":true}')
        self.run_cli("--ci", redacted=False)
        self.assertTrue(any(cmd[:4] == ["kubectl", "rollout", "status", "deployment/kueue-controller-manager"]
            for cmd in self.commands()))
        self.assertFalse(any(cmd[0] == "ko" or "forgejo" in cmd for cmd in self.commands()))

        self.log.unlink()
        self.env["INSTALL_KUEUE"] = "true"
        self.run_cli("--up")
        self.assertEqual(self.kueue_commands(), [])


if __name__ == "__main__":
    unittest.main()
