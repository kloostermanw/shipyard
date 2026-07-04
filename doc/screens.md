# Shipyard - Screen Mockups

## 1. Dashboard Screen

The home screen showing all applications at a glance with their **latest GitHub version** and **deployed version per environment**. Environment columns are built dynamically from the union of all environment names across all apps, sorted by deploy-pipeline priority (`prd` → `uat` → `staging` → `dev` → alphabetical). Select a row and press `enter` to open.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Applications                                                               │
│                                                                             │
│  ┌──────────────┬────────┬────────┬────────┬─────────┐                      │
│  │ Application  │ Latest │ PRD    │ UAT    │ STAGING │                      │
│  ├──────────────┼────────┼────────┼────────┼─────────┤                      │
│  │▶Mainappl     │ v3.4   │ v3.2   │ v3.3   │ v3.4    │                      │
│  │ Frontend App │ v2.1   │ v2.0   │ -      │ v2.1    │                      │
│  │ API Service  │ v5.0   │ v4.9   │ v5.0   │ v5.0    │                      │
│  │ Admin Panel  │ v1.3   │ v1.3   │ -      │ -       │                      │
│  │              │        │        │        │         │                      │
│  └──────────────┴────────┴────────┴────────┴─────────┘                      │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ r Refresh  s Servers  e Secrets  q Quit           enter Open (on table row)  │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **Latest** column shows the latest GitHub release/tag, fetched asynchronously in parallel. Displays `...` while loading, then the version or `-` if unavailable.
- **Environment columns** (PRD, UAT, STAGING, etc.) show the deployed Docker image tag extracted from the first container in each environment's container cache. Displays `-` until container data is available.
- Both columns update reactively: GitHub versions resolve progressively via `update_cell()`, and environment versions refresh when the container cache updates.

Key bindings (all `priority=True`):
- `r` — Re-populate the table, trigger a container cache refresh, and re-fetch GitHub versions
- `s` — Open Servers screen
- `e` — Open Secrets screen
- `q` — Quit the application
- `enter` — Open the selected application (handled via `on_data_table_row_selected`)

## 2. Application Screen

Detail view for a single application. Environments are shown in a **TabbedContent** widget — one tab per environment, each containing an `EnvironmentPanel` with server info and container status table.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Mainappl                                                                   │
│  Mainappl application                                                       │
│  GitHub: myorg/mainappl (tracking tags)                                     │
│                                                                             │
│  ┌─ PRD ──┬─ UAT ──┬─ STAGING ──────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  Server: prod-web-01                                                 │   │
│  │  Path: /opt/apps/mainappl                            ● synced        │   │
│  │  Local: ~/repos/mainappl                                             │   │
│  │                                                                      │   │
│  │  Container              Status     Image                    Uptime   │   │
│  │  ──────────────────────────────────────────────────────────────────  │   │
│  │  mainappl-prd-php       running    myorg/mainappl:v3.2      2d ago   │   │
│  │  mainappl-prd-queue     running    myorg/mainappl:v3.2      2d ago   │   │
│  │  mainappl-prd-scheduler running    myorg/mainappl:v3.2      2d ago   │   │
│  │  mainappl-prd-nginx     running    myorg/mainappl:v3.2      2d ago   │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ escape Back  d Deploy  l Logs  r Refresh                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

Key bindings (all `priority=True`):
- `d` — Open Deploy screen for this application
- `l` — Open Log viewer for the first container in the active tab's environment
- `y` — Open Sync screen for the active tab's environment (if `local-path` is configured)
- `r` — Refresh container status via SSH
- `escape` — Back to Dashboard

## 3. Deploy Screen - Version Selection

Select an environment (left) and a version from GitHub tags/releases (right). Versions are fetched asynchronously on mount. If there are active GitHub Actions workflow runs, they are displayed above the selection lists and auto-refresh at the configured `polling_interval` (default 2s). The running-workflows panel shows in-progress runs with an animated Braille spinner and queued runs with a static `○`. The list is filtered to the highlighted environment's `workflow_filter` when one is configured, otherwise all runs are shown.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Deploy Mainappl                                                            │
│                                                                             │
│  ┌─ Environment ──────────┐ ┌─ Version ──────────────────────────────────┐  │
│  │                        │ │                                            │  │
│  │ ▶ PRD                  │ │ ▶ v3.4.0                                   │  │
│  │   UAT                  │ │   v3.3.1                                   │  │
│  │   STAGING              │ │   v3.3.0                                   │  │
│  │                        │ │   v3.2.0                                   │  │
│  │                        │ │   v3.1.0                                   │  │
│  │                        │ │   v3.0.0                                   │  │
│  │                        │ │   v2.9.0 [pre-release]                     │  │
│  │                        │ │                                            │  │
│  └────────────────────────┘ └────────────────────────────────────────────┘  │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ escape Back                                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

Selection flow:
1. Highlight an environment in the left `ListView` (auto-selected if only one; highlighting is enough, no Enter needed)
2. Select a version in the right `ListView` by pressing Enter
3. Confirmation modal appears

## 4. Deploy Screen - Confirmation Modal

Modal dialog shown after selecting environment + version.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Deploy Mainappl                                                            │
│                                                                             │
│  ┌─ Environment ──┐ ┌─ Ve┌──────────────────────────────────────┐────────┐  │
│  │                │ │    │                                      │        │  │
│  │ ▶ PRD          │ │ ▶ v│        Deploy Mainappl?              │        │  │
│  │   UAT          │ │   v│                                      │        │  │
│  │   STAGING      │ │   v│  Version:     v3.4.0                 │        │  │
│  │                │ │   v│  Environment: prd                    │        │  │
│  │                │ │   v│  Server:      prod-web-01            │        │  │
│  │                │ │   v│                                      │        │  │
│  │                │ │   v│       [ Deploy ]  [ Cancel ]         │        │  │
│  │                │ │    │                                      │        │  │
│  └────────────────┘ └── └──────────────────────────────────────┘────────┘  │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ escape Back                                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 5. Deploy Screen - Running

After confirmation, the version selection is hidden and the `DeployProgress` widget is shown, streaming live output from `rerun.sh`.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Deploy Mainappl                                                            │
│                                                                             │
│  DEPLOYING Running ./rerun.sh v3.4.0 in /opt/apps/mainappl                 │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ Connecting to prod-web-01...                                            ││
│  │ Running ./rerun.sh v3.4.0 in /opt/apps/mainappl                         ││
│  │ Pulling ghcr.io/myorg/mainappl:v3.4.0...                                ││
│  │ v3.4.0: Pulling from myorg/mainappl                                     ││
│  │ a2abf6c4d29d: Already exists                                            ││
│  │ c5608244554d: Pull complete                                             ││
│  │ Digest: sha256:abc123...                                                ││
│  │ Status: Downloaded newer image                                          ││
│  │ Stopping mainappl-prd-php...                                            ││
│  │ Stopping mainappl-prd-queue...                                          ││
│  │ Stopping mainappl-prd-nginx...                                          ││
│  │ Starting mainappl-prd-php...                                            ││
│  │ Starting mainappl-prd-queue...                                          ││
│  │ Starting mainappl-prd-nginx...                                          ││
│  │ All containers started                                                  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ escape Back                                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 6. Deploy Screen - Success

After a successful deployment.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Deploy Mainappl                                                            │
│                                                                             │
│  SUCCESS Deploy completed successfully (exit code 0)                        │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ Connecting to prod-web-01...                                            ││
│  │ Running ./rerun.sh v3.4.0 in /opt/apps/mainappl                        ││
│  │ Pulling ghcr.io/myorg/mainappl:v3.4.0...                               ││
│  │ ...                                                                     ││
│  │ All containers started                                                  ││
│  │ Deploy completed successfully (exit code 0)                             ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ escape Back                                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 7. Servers Screen

Overview of all configured servers and their connectivity status. Status is checked asynchronously via SSH and updated in-place.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Servers                                                                    │
│                                                                             │
│  ┌────────────┬─────────────┬──────┬────────┬───────────┬──────────────────┐│
│  │ Server     │ Hostname    │ Port │ User   │ Status    │ Description      ││
│  ├────────────┼─────────────┼──────┼────────┼───────────┼──────────────────┤│
│  │▶prod-web-01│ 10.0.1.10   │ 22   │ deploy │ reachable │ Production web 1 ││
│  │ prod-web-02│ 10.0.1.11   │ 22   │ deploy │ reachable │ Production web 2 ││
│  │ staging-01 │ 10.0.2.10   │ 22   │ deploy │ reachable │ Staging server   ││
│  │ uat-01     │ 10.0.3.10   │ 2222 │ deploy │unreachable│ UAT server       ││
│  │            │             │      │        │           │                  ││
│  │            │             │      │        │           │                  ││
│  │            │             │      │        │           │                  ││
│  └────────────┴─────────────┴──────┴────────┴───────────┴──────────────────┘│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ escape Back  r Refresh                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

Key bindings:
- `r` — Re-check all server connectivity
- `escape` — Back to Dashboard (`priority=True`)
- `enter` — Open server detail (handled via `on_data_table_row_selected`)

## 8. Server Detail Screen

Detail view for a single server showing all Docker containers (via `docker ps -a --format json`). Container status is color-coded: green for running, red for exited/dead, yellow for other states.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  prod-web-01 — 10.0.1.10                                                   │
│  4 container(s)                                                             │
│                                                                             │
│  ┌──────────────────────┬──────────┬───────────────────────────┬───────────┐│
│  │ Container            │ Status   │ Image                     │ Uptime    ││
│  ├──────────────────────┼──────────┼───────────────────────────┼───────────┤│
│  │ mainappl-prd-php     │ running  │ myorg/mainappl:v3.2       │ Up 2 days ││
│  │ mainappl-prd-queue   │ running  │ myorg/mainappl:v3.2       │ Up 2 days ││
│  │ mainappl-prd-nginx   │ running  │ myorg/mainappl:v3.2       │ Up 2 days ││
│  │ old-app-worker       │ exited   │ myorg/old-app:v1.0        │ Exited 3d ││
│  │                      │          │                           │           ││
│  │                      │          │                           │           ││
│  └──────────────────────┴──────────┴───────────────────────────┴───────────┘│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ escape Back  r Refresh                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

Container data is read from the shared `server_container_cache` (populated at startup). No separate SSH call is made when opening this screen.

Key bindings:
- `r` — Triggers a global container cache refresh (same as other screens)
- `escape` — Back to Servers screen (`priority=True`)

## 9. Log Viewer Screen

Live streaming of Docker container logs via `docker logs -f --tail 100`.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Logs: mainappl-prd-php on prod-web-01                        FOLLOWING    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ [2026-02-21 12:30:01] INFO: Worker started pid=42                       ││
│  │ [2026-02-21 12:30:01] INFO: Listening on 0.0.0.0:9000                   ││
│  │ [2026-02-21 12:30:15] INFO: GET /api/health 200 2ms                     ││
│  │ [2026-02-21 12:30:30] INFO: GET /api/health 200 1ms                     ││
│  │ [2026-02-21 12:30:45] INFO: GET /api/health 200 2ms                     ││
│  │ [2026-02-21 12:31:02] INFO: POST /api/samples 201 145ms                 ││
│  │ [2026-02-21 12:31:03] INFO: GET /api/samples/1234 200 12ms              ││
│  │ [2026-02-21 12:31:15] INFO: GET /api/health 200 1ms                     ││
│  │ [2026-02-21 12:31:22] WARN: Slow query detected (320ms)                 ││
│  │ [2026-02-21 12:31:30] INFO: GET /api/health 200 2ms                     ││
│  │ [2026-02-21 12:31:45] INFO: GET /api/health 200 1ms                     ││
│  │ [2026-02-21 12:32:00] INFO: GET /api/health 200 2ms                     ││
│  │ [2026-02-21 12:32:05] INFO: PUT /api/samples/1234 200 89ms              ││
│  │ [2026-02-21 12:32:15] INFO: GET /api/health 200 1ms                     ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ escape Back  f Follow  c Clear                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

Key bindings:
- `f` — Toggle follow mode (FOLLOWING / PAUSED)
- `c` — Clear the log display
- `escape` — Stop log stream and go back (`priority=True`)

## 10. Sync Screen

Shows file sync progress when syncing local files to a remote server via SFTP. Opened from the Application screen by pressing `y` on an environment that has `local-path` configured.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Sync Mainappl / PRD                                                        │
│  Local: ~/repos/mainappl → Remote: prod-web-01:/opt/apps/mainappl           │
│                                                                             │
│  SYNCING [3/5] Uploading: config/app.yaml                                   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ Scanning local files...                                                ││
│  │ Found 5 local file(s)                                                  ││
│  │ Getting remote checksums...                                            ││
│  │ 5 file(s) to sync                                                     ││
│  │ Creating directory: config                                             ││
│  │ Uploading: docker-compose.yml                                          ││
│  │ Uploading: rerun.sh                                                    ││
│  │ Uploading: config/app.yaml                                             ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ escape Back                                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

Key bindings:
- `escape` — Back to Application screen (`priority=True`)

## 11. Secrets Screen

Manage the encrypted secret store. Accessible from the Dashboard via `e`. The screen has two states:

### Locked State

Shows a password input to unlock the store. On successful unlock, the screen rebuilds to show the table view.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Unlock Secret Store                                                        │
│  Enter the master password to unlock your secrets.                          │
│                                                                             │
│  ┌────────────────────────────────────┐                                     │
│  │ ●●●●●●●●                          │                                     │
│  └────────────────────────────────────┘                                     │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ escape Back                                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Unlocked State

Shows a DataTable of all secrets. Values are masked as `********` by default; press `r` on a row to toggle revealing the cleartext value (toggle again to hide). Reveal state resets when the screen is left.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Secrets                                                                    │
│                                                                             │
│  ┌──────────────────────────────┬──────────────────────────────────────────┐│
│  │ Key                          │ Value                                    ││
│  ├──────────────────────────────┼──────────────────────────────────────────┤│
│  │▶DB_PASSWORD                  │ ********                                 ││
│  │ API_KEY                      │ ********                                 ││
│  │ SMTP_PASSWORD                │ ********                                 ││
│  │                              │                                          ││
│  └──────────────────────────────┴──────────────────────────────────────────┘│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ a Add  e Edit  r Reveal  x Delete  escape Back                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

Key bindings (all `priority=True`):
- `a` — Add new secret (opens SecretInputModal)
- `e` — Edit selected secret (opens SecretInputModal pre-filled)
- `r` — Toggle reveal/mask of the selected row's value
- `x` — Delete selected secret
- `escape` — Back to Dashboard

### SecretInputModal

Modal dialog for adding or editing a secret. Key input is disabled when editing.

```
┌──────────────────────────────────────────┐
│          Add Secret                       │
│                                           │
│  Key:                                     │
│  ┌──────────────────────────────────┐     │
│  │ DB_PASSWORD                      │     │
│  └──────────────────────────────────┘     │
│  Value:                                   │
│  ┌──────────────────────────────────┐     │
│  │ ●●●●●●●●                        │     │
│  └──────────────────────────────────┘     │
│                                           │
│       [ Save ]  [ Cancel ]                │
└──────────────────────────────────────────┘
```

## 12. Template Detail Screen

Inspects a `.j2` template file's KEY=VALUE entries and their secret linkage. Opened from the Application screen by selecting a template in the Templates list (requires the secret store to be unlocked).

Each row shows a key from the template, its value status, and its secret linkage:
- **LINKED** (green dot): `{{VAR}}` exists in the secret store
- **FAILED LINK** (red x): `{{VAR}}` referenced but missing from the secret store
- **Non-linked** (masked): plain value, not a secret reference

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Template: subfolder/env.j2                                                 │
│  Path: ~/repos/mainappl                                                     │
│                                                                             │
│  ┌──────────────────┬─────────────┬────────────────────────────────────────┐│
│  │ Key              │ Value       │ Secret                                 ││
│  ├──────────────────┼─────────────┼────────────────────────────────────────┤│
│  │▶DB_PASSWORD      │ LINKED      │ ● APP_DB_PASSWORD                      ││
│  │ API_KEY          │ ******      │ -                                      ││
│  │ SMTP_PASSWORD    │ FAILED LINK │ x APP_SMTP_PASSWORD                    ││
│  │                  │             │                                        ││
│  └──────────────────┴─────────────┴────────────────────────────────────────┘│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ escape Back                                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

Selecting a row opens a modal based on entry type:

- **LINKED** → LinkedSecretModal: edit the secret value or delete the secret
- **Non-linked** → ConvertToSecretModal: store the value as a secret and rewrite the template line to `{{SECRET_NAME}}`
- **FAILED LINK** → CreateMissingSecretModal: create the missing secret

Key bindings:
- `escape` — Back to Application screen (`priority=True`)

## Screen Navigation

```
                    ┌───────────┐
                    │ Dashboard │ (home)
                    └─────┬─────┘
                          │
              ┌───────────┼───────────┬───────────┐
              │ enter     │           │ s         │ e
              ▼           │           ▼           ▼
      ┌───────────┐      │    ┌───────────┐ ┌─────────┐
      │Application│      │    │  Servers   │ │ Secrets │
      └─────┬─────┘      │    └─────┬─────┘ └────┬────┘
            │             │          │ enter       │
  ┌─────┼─────┼────┼───┐ │          ▼            ▼
  │ d   │ l   │ y  │tpl│ │   ┌──────────────┐ ┌──────────┐
  ▼     ▼     ▼    ▼   │ │   │Server Detail │ │  Secret  │
┌──────┐┌────┐┌────┐┌────────┐└────────────┘ │  Input   │
│Deploy││Logs││Sync││Template│               │ (modal)  │
├──────┤└────┘└────┘│ Detail │               └──────────┘
│Confirm│           ├────────┤
│(modal)│           │Modals  │
└──────┘            └────────┘

Key: ▼ = push_screen()
     escape = pop_screen() (back)
     tpl = select template from list
```

## Fetch Status Bar

All screens include a `FetchStatusBar` widget docked to the bottom (above the Footer). This 1-line bar shows progress during container cache refreshes:

- Displays "Fetching servers: 0/N" when a refresh starts, updating as each server completes
- Yellow text while in progress, green when all servers have responded
- Auto-hides after 2 seconds once the cache update is complete

The bar reacts to `FetchProgress` and `ContainerCacheUpdated` messages posted by `ShipyardApp`.

## Implementation Notes

- All screen-level key bindings use `priority=True` to ensure they fire even when child widgets (DataTable, TabbedContent, ListView) have focus
- Dashboard uses `on_data_table_row_selected` instead of an `enter` binding because DataTable handles `enter` internally
- Deploy screen uses index-based selection (not widget IDs) for version/environment lists, since version tags can contain dots which are invalid in Textual IDs
- Servers screen stores column keys from `add_columns()` for use with `update_cell()`, since Textual column keys are objects, not label strings
- All async operations (SSH connectivity, GitHub API, deploy streaming) run in Textual workers via `run_worker()`

## MCP Server

When `global.mcp.enabled: true`, the TUI also exposes a Unix-socket control plane that powers the optional `shipyard mcp` stdio server. The TUI must be running for any MCP tool call to succeed; the secret store must be unlocked for any secret-related tool. There is no dedicated screen for MCP in the TUI today (an audit-log viewer is planned). See `doc/mcp.md` for the full guide.
