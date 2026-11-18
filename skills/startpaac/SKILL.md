---
name: startpaac
description: Set up, inspect, troubleshoot, redeploy, or tear down a local Pipelines-as-Code (PAC) development environment with startpaac. Applies from a PAC worktree or any directory. Ordinary PAC code edits and remote or production Kubernetes work are outside this workflow.
---

## Pick the action

Find a trusted `startpaac` executable and `jq` on PATH. If startpaac is missing
from PATH, an existing trusted checkout can run it by absolute path with its
sibling `lib/` directory. Run `startpaac --describe --output json` and check
`ok`, `schema_version: 1`, and the required flag in `data.actions[].flag`.
If discovery fails or the action is unavailable, use the
[onboarding reference](references/onboarding.md) to resolve it. The JSON
interface applies to local, Docker-backed Kind.

| User request | Start here |
| --- | --- |
| Check prerequisites or prepare a first environment | Run `--doctor` and the [onboarding checks](references/onboarding.md). Preview `--up` when ready. Execute it if the user asked to bring the environment up. |
| Bring up or repair the full local stack | Preview `--up`. It creates Kind when absent and reuses a compatible cluster. On reuse it can still rebuild PAC and restart containerd. |
| Inspect or diagnose an existing environment | Run `--status`. Read its component results and errors even on failure. For a named component, focus on that deployment. |
| Rebuild a controller, watcher, or webhook | Preview and run `-c <component>`. Its plan checks its own prerequisites. Local GitHub App credentials and a passing full-stack doctor or status are unnecessary. |
| Rebuild and configure all PAC components | Preview and run `-p`. This also configures PAC and requires reusable GitHub App credentials and a relay URL. |
| Delete the local environment | Preview `--stop-kind` only when the user requests teardown. It deletes the local `kind` cluster and its dedicated kubeconfig. |

Use `--output json` for every action in the table. A request to check status or
readiness stays read-only. A request to deploy a named component does not cover
creating, replacing, or reconfiguring the full environment.

## Check the plan before changing anything

Append `--plan --output json` to the intended deployment or teardown command.
Run discovery and inspections using trusted configuration. Each command except
`--describe` loads a shell file (`STARTPAC_CONFIG_FILE` or the default
`~/.config/startpaac/config`). Let startpaac load it. Avoid sourcing it
separately, dumping it, or enabling shell tracing.

- For a source build, compare `data.pac_dir` with the intended checkout.
  Run from the requested PAC worktree and pass its absolute path as `PAC_DIR`
  when explicitly selected. Shell config can overwrite that value. If the plan
  points to a different worktree, resolve the config or checkout choice before
  building. Two worktrees at the same commit may have different edits.
- Check `target.host`, `target.cluster`, and `target.kubeconfig` against the
  intended target. Use the dedicated kubeconfig from the plan for follow-up
  reads.
  On incompatible Kind or missing, stale, or shared kubeconfig, follow the
  [onboarding recovery notes](references/onboarding.md#cluster-and-kubeconfig).
- Check `data.component`, `data.steps`, `data.hooks`, `data.scale_down`,
  `data.destructive`, and `warnings`. Inspect unfamiliar listed hooks before
  executing. Hooks run user code and can have effects beyond the listed steps.
  Resolve any effects outside the request before proceeding.
- Proceed only after a successful plan for the intended action. Use the same
  executable, working directory, config, and target settings, replacing
  `--plan` with `--non-interactive` and keeping `--output json`. Replan if the
  checkout, configuration, hooks, or target changes.

## Read the result and verify the request

Capture stdout and stderr separately and preserve the exit status. Parse stdout
with jq, including on failure. Require one JSON object with the supported schema.
A successful command requires exit 0, `ok: true`, and the expected `action`.
Exit 1 means a failed check or operation. Exit 2 means invalid arguments. Use
`errors[].code`, `message`, and `next_step` to find the cause. A timeout,
interruption, malformed result, or failed deployment can leave partial changes.
Inspect the current state before retrying. Treat suggested next steps as
diagnostic hints and keep recovery within the requested scope.

- `--up` returns `data.components`, `registry_ready`, and endpoint URLs after
  its rollout checks. Report the observed readiness. The PAC and Dashboard
  URLs are configured addresses, so probe them separately if reachability
  matters to the request.
- `-c` waits for the requested rollout. `-p` waits for the PAC deployments.
  Report that result directly. If you need a fresh or more detailed check,
  use the plan's kubeconfig, `--context=kind-kind`, and namespace
  `pipelines-as-code` to inspect just the relevant deployment
  (`pipelines-as-code-controller`, `pipelines-as-code-watcher`, or
  `pipelines-as-code-webhook`). The CLI skips rollout checks for components
  explicitly selected for scale-down. Report those as scaled down.
- `--status` checks the full stack. If another component or the registry fails,
  report the requested deployment's own readiness when `data.components`
  contains it. If preflight fails or the API is unreachable, report readiness
  as unknown. For diagnosis, start with events for the affected namespace and
  recent logs for the affected deployment. Keep these reads scoped to the
  target and redact credentials, private keys, relay URLs, and webhook payloads.
- A running forwarder only confirms an observed service. Verify GitHub
  delivery with an actual event and evidence that PAC received it. Use existing
  delivery evidence when available and respect the request's scope before
  triggering an event. Report delivery as unverified when there is no evidence.
  Starting a forwarder or creating a GitHub App is a separate workflow.

[CLI and installation guide](https://github.com/pipelines-as-code/startpaac/blob/main/docs/agents.md)
