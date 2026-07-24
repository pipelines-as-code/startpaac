# StartPAC Architecture

This document describes the architecture and design of StartPAC, an automated setup tool for Pipelines as Code development environments.

## Overview

StartPAC is a modular Bash-based orchestration tool that automates the creation of a complete Pipelines as Code development environment on Kubernetes using Kind (Kubernetes in Docker).

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         StartPAC CLI                           │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Interactive Menu (gum) │ Preferences (JSON) │ Config     │  │
│  └───────────────────────────────────────────────────────────┘  │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Component Installers                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │  Kind    │ │  Envoy   │ │ Registry │ │  Tekton  │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │   PAC    │ │ Forgejo  │ │PostgreSQL│ │Dashboard │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Kubernetes (Kind Cluster)                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Namespaces:                                             │   │
│  │  • tekton-pipelines (Tekton core + Dashboard)           │   │
│  │  • pipelines-as-code (PAC controllers)                  │   │
│  │  • envoy-gateway-system (Gateway API impl.)              │   │
│  │  • default (Forgejo, PostgreSQL)                        │   │
│  │  • gosmee (Webhook proxy)                               │   │
│  └─────────────────────────────────────────────────────────┘   │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Docker / Container Runtime                  │
└─────────────────────────────────────────────────────────────────┘
```

## Component Architecture

### Core Components (Always Installed)

#### 1. Kind Cluster
- **Purpose**: Provides local Kubernetes cluster
- **Configuration**: `lib/kind/kind.yaml`
- **Features**:
  - Insecure registry support
  - Port forwarding for Envoy Gateway NodePorts (80->31080, 443->31443)
  - Custom containerd registry configuration

#### 2. Envoy Gateway
- **Purpose**: HTTP(S) routing to services via the Kubernetes Gateway API
- **Namespace**: `envoy-gateway-system`
- **Features**:
  - TLS termination with a wildcard self-signed certificate (minica)
  - Single shared `Gateway`; per-component `HTTPRoute` resources use its HTTPS listener
  - Routes traffic to PAC, Forgejo, Dashboard, Registry

#### 3. Docker Registry
- **Purpose**: Store locally built container images
- **Location**: `lib/registry/install.sh`
- **Access**: `https://registry.127.0.0.1.nip.io` (local mode)
- **Features**:
  - Insecure registry mode for development
  - Used by `ko` to push PAC images

#### 4. Tekton Pipelines
- **Purpose**: Core CI/CD pipeline engine
- **Namespace**: `tekton-pipelines`
- **Version**: Latest release from upstream
- **Features**:
  - Step actions enabled
  - Webhook-based admission control

### Optional Components

#### 5. Pipelines as Code (PAC)
- **Purpose**: GitOps-style pipeline definitions
- **Namespace**: `pipelines-as-code`
- **Build Method**: `ko` from local source
- **Components**:
  - Controller: Main reconciliation loop
  - Watcher: Monitors PipelineRun status
  - Webhook: Receives GitHub/GitLab events
- **Configuration**:
  - GitHub App credentials (via secrets)
  - Webhook proxy (gosmee)
  - Ingress with TLS

#### 6. Tekton Dashboard
- **Purpose**: Web UI for Tekton
- **Namespace**: `tekton-pipelines`
- **Access**: `https://dashboard.127.0.0.1.nip.io`

#### 7. Tekton Triggers
- **Purpose**: Event-driven pipeline execution
- **Namespace**: `tekton-pipelines`

#### 8. Tekton Chains
- **Purpose**: Supply chain security (signing, attestation)
- **Namespace**: `tekton-chains`

#### 9. Forgejo
- **Purpose**: Self-hosted Git forge for local testing
- **Namespace**: `default`
- **Deployment**: Helm chart
- **Access**: `https://gitea.127.0.0.1.nip.io`
- **Features**:
  - Lightweight Git server
  - Webhook support
  - SQLite backend (no persistence)

#### 10. PostgreSQL
- **Purpose**: Database backend for PAC
- **Namespace**: `default`
- **Deployment**: Bitnami Helm chart
- **Features**:
  - No persistence (development mode)
  - Custom credentials via values.yaml

#### 11. GitHub Second Controller
- **Purpose**: Support multiple GitHub instances (e.g., GitHub Enterprise)
- **Namespace**: `pipelines-as-code`
- **Features**:
  - Separate secret management
  - Dedicated ingress endpoint
  - Independent gosmee proxy

## Directory Structure

```
startpaac/
├── startpaac              # Main entry point
├── lib/
│   ├── common.sh          # Shared utilities
│   ├── config.sh          # Configuration loading
│   ├── kind/
│   │   └── kind.yaml      # Kind cluster config
│   ├── registry/
│   │   └── install.sh     # Registry installer
│   ├── forgejo/
│   │   ├── install.sh     # Forgejo installer
│   │   └── values.yaml    # Helm values
│   ├── postgresql/
│   │   ├── install.sh     # PostgreSQL installer
│   │   └── values.yaml    # Helm values
│   └── helm/
│       └── install.sh     # Helm installer
├── misc/
│   └── _startpaac         # ZSH completion
└── docs/
    └── architecture.md    # This file
```

## Data Flow

### Installation Flow

```
1. User runs: ./startpaac
   │
   ├─→ Load configuration from ~/.config/startpaac/config
   ├─→ Check prerequisites (docker, kubectl, helm, ko, etc.)
   ├─→ Load or prompt for component preferences
   │
2. Component Selection
   │
   ├─→ Show interactive menu (if first run or --menu flag)
   ├─→ Save preferences to ~/.config/startpaac/preferences.json
   │
3. Infrastructure Setup
   │
   ├─→ Create Kind cluster
   ├─→ Install Envoy Gateway
   ├─→ Install Docker Registry
   ├─→ Install Tekton Pipelines
   │
4. Optional Components (based on preferences)
   │
   ├─→ Install Tekton Dashboard, Triggers, Chains
   ├─→ Build and deploy PAC using ko
   ├─→ Configure PAC (secrets, HTTPRoute, configmaps)
   ├─→ Install Forgejo, PostgreSQL
   ├─→ Install GitHub Second Controller
   │
5. Finalization
   │
   ├─→ Start gosmee webhook proxy
   ├─→ Set kubectl context to pipelines-as-code namespace
   └─→ Display configuration summary
```

### PAC Webhook Flow (Runtime)

```
GitHub/GitLab Event
   │
   ▼
Webhook URL (GitHub App)
   │
   ▼
Gosmee Proxy (local or in-cluster)
   │
   ▼
Envoy Gateway (https://paac.127.0.0.1.nip.io)
   │
   ▼
PAC Webhook Service (port 8080)
   │
   ▼
PAC Controller (reconciliation)
   │
   ├─→ Create PipelineRun
   ├─→ Fetch .tekton/ files from repo
   └─→ Execute pipeline
        │
        ▼
   Tekton Pipelines Engine
        │
        ▼
   Results reported back to GitHub/GitLab
```

## Deployment Modes

### Local Mode (TARGET_HOST=local)
- Kind cluster runs on localhost
- Uses 127.0.0.1.nip.io for DNS
- Insecure registry mode
- Gosmee runs as local systemd user service

### Remote Mode (TARGET_HOST=vm.example.com)
- Kind cluster runs on remote VM
- Requires SSH access to remote host
- Uses custom DNS or nip.io
- Kubeconfig synced from remote host
- Gosmee can run locally or in-cluster

## Secret Management

### Two Approaches

1. **Password Store (`pass`)**
   - Encrypted secret storage
   - Recommended for security
   - Environment: `PAC_PASS_SECRET_FOLDER`

2. **Plain Text Files**
   - Simple file-based storage
   - Development only
   - Environment: `PAC_SECRET_FOLDER`

When no usable credentials exist, interactive runs (and `--setup-github-app`)
can create the GitHub App automatically via GitHub's App Manifest flow: a local
Python callback server (`lib/github_app_create.py`) receives the redirect,
exchanges the temporary code for credentials, and startpaac stores them in
`pass` or `~/.local/share/startpaac/secrets`. Webhook delivery is forwarded
from a hook.pipelinesascode.com relay by a gosmee user service (systemd user
unit on Linux, LaunchAgent on macOS).

### Required Secrets
```
secrets/
├── github-application-id   # GitHub App ID
├── github-private-key      # GitHub App private key (PEM)
├── webhook.secret          # Webhook shared secret
└── smee                    # Webhook proxy URL
```

## Configuration System

### Configuration Hierarchy

1. **System Defaults** (in code)
2. **User Config** (`~/.config/startpaac/config`)
3. **Environment Variables** (override config file)
4. **Component Preferences** (`~/.config/startpaac/preferences.json`)

### Key Configuration Variables

- `TARGET_HOST`: Where to run Kind (local or remote VM)
- `DOMAIN_NAME`: Base domain for ingress
- `PAC_DIR`: Path to Pipelines as Code source
- `PAC_SECRET_FOLDER`: Path to plain text secrets
- `PAC_PASS_SECRET_FOLDER`: Pass store path for secrets
- `INSTALL_*`: Boolean flags for optional components

## Network Architecture

### Ingress Routes

```
https://paac.127.0.0.1.nip.io
   └─→ pipelines-as-code/pipelines-as-code-controller:8080

https://dashboard.127.0.0.1.nip.io
   └─→ tekton-pipelines/tekton-dashboard:9097

https://gitea.127.0.0.1.nip.io
   └─→ default/forgejo-http:3000

https://registry.127.0.0.1.nip.io
   └─→ default/registry:5000
```

### Port Forwarding (Kind)

```
Host              Kind Node
────────────────────────────
80:32080    →    80:32080
443:32443   →    443:32443
```

## Build Process

### PAC Build with Ko

```
1. Read PAC source from PAC_DIR
2. Ko resolve YAML manifests
   │
   ├─→ Build Go binaries
   ├─→ Create container images
   ├─→ Push to registry.127.0.0.1.nip.io
   └─→ Update YAML with image references
3. Apply YAML to cluster
```

## State Management

### Cache Locations

- **YAML Cache**: `~/.cache/startpaac/` (downloaded manifests)
- **TLS Certificates**: `/tmp/certs/` (minica-generated)
- **Kubeconfig**: `~/.kube/config.<domain>` (per-environment)
- **Preferences**: `~/.config/startpaac/preferences.json` (JSON)

### Stateless Design

- No persistent state in cluster (development mode)
- Cluster can be recreated at any time
- Preferences survive cluster recreation
- Secrets managed externally

## Extension Points

### Adding New Components

1. Create installer script: `lib/newcomponent/install.sh`
2. Add menu entry in `build_component_menu()`
3. Add flag in `parse_menu_selections()`
4. Add installation call in `all()` function
5. Add preferences handling in `load_preferences()` / `save_preferences()`

### Custom Objects

Users can inject custom Kubernetes objects via:
```bash
INSTALL_CUSTOM_OBJECT=~/path/to/yamls/
INSTALL_CUSTOM_OBJECT_ENABLED=true
```

## Design Principles

1. **Modular**: Each component is independent and can be installed separately
2. **Idempotent**: Can be run multiple times safely
3. **Fast Iteration**: Quick rebuild and redeploy of PAC changes
4. **Developer-Focused**: Optimized for rapid development, not production
5. **Self-Contained**: Minimal external dependencies
6. **Interactive**: User-friendly menus and clear feedback
7. **Reproducible**: Preferences ensure consistent environments

## Performance Considerations

### Resource Usage

- **Minimum**: 4 cores, 8GB RAM, 20GB disk
- **Recommended**: 8 cores, 16GB RAM, 50GB disk
- **Peak Usage**: During initial install (image pulls)
- **Steady State**: ~2-4GB RAM, minimal CPU

### Optimization Strategies

1. **YAML Caching**: Downloaded manifests cached locally
2. **Insecure Registry**: Faster image pushes (no TLS overhead)
3. **Local Registry**: No external network for image pulls
4. **Component Scaling**: Can scale down unused components
5. **No Persistence**: SQLite/in-memory for dev (faster, less disk)

## Security Model

### Threat Model

- **Scope**: Local development only
- **Assumptions**: Single developer, trusted local machine
- **Not Designed For**: Production, multi-user, internet exposure

### Security Features

- TLS for all ingress (self-signed)
- Namespace isolation
- Secret injection via kubectl
- Optional encrypted secrets (pass)

### Security Limitations

- Weak default passwords (development only)
- Self-signed certificates
- No RBAC configuration
- Insecure registry mode
- No network policies

## Future Architecture Considerations

### Potential Enhancements

1. **Multi-cluster Support**: Manage multiple environments
2. **Cloud Provider Support**: EKS, GKE, AKS variants
3. **Production Mode**: Hardened configuration option
4. **Plugin System**: Third-party component integrations
5. **Observability**: Prometheus, Grafana pre-configured
6. **Testing**: Automated smoke tests on install

## Related Documentation

- [README.md](../README.md) - User guide and getting started
- [configuration.md](configuration.md) - Full configuration reference
- [Pipelines as Code Docs](https://pipelinesascode.com/docs/) - PAC documentation
- [Tekton Docs](https://tekton.dev/docs/) - Tekton documentation
