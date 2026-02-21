# Shipyard - Screen Mockups

## 1. Dashboard Screen

The home screen showing all applications at a glance. Select a row and press `enter` to open.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Applications                                                               │
│                                                                             │
│  ┌───────────────────────┬──────────────────────┬──────────────────────────┐│
│  │ Application           │ Environments         │ GitHub                   ││
│  ├───────────────────────┼──────────────────────┼──────────────────────────┤│
│  │▶Genotool              │ prd, uat, staging    │ myorg/genotool           ││
│  │ Frontend App          │ prd, staging         │ myorg/frontend           ││
│  │ API Service           │ prd, uat, staging    │ myorg/api-service        ││
│  │ Admin Panel           │ prd                  │ myorg/admin-panel        ││
│  │                       │                      │                          ││
│  │                       │                      │                          ││
│  │                       │                      │                          ││
│  │                       │                      │                          ││
│  └───────────────────────┴──────────────────────┴──────────────────────────┘│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ r Refresh  s Servers  q Quit                     enter Open (on table row)  │
└─────────────────────────────────────────────────────────────────────────────┘
```

Key bindings (all `priority=True`):
- `r` — Refresh the application list
- `s` — Open Servers screen
- `q` — Quit the application
- `enter` — Open the selected application (handled via `on_data_table_row_selected`)

## 2. Application Screen

Detail view for a single application. Environments are shown in a **TabbedContent** widget — one tab per environment, each containing an `EnvironmentPanel` with server info and container status table.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Genotool                                                                   │
│  Genotool application                                                       │
│  GitHub: myorg/genotool (tracking tags)                                     │
│                                                                             │
│  ┌─ PRD ──┬─ UAT ──┬─ STAGING ─────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  Server: prod-web-01                                                 │   │
│  │  Path: /opt/apps/genotool                                            │   │
│  │                                                                      │   │
│  │  Container              Status     Image                    Uptime   │   │
│  │  ──────────────────────────────────────────────────────────────────   │   │
│  │  genotool-prd-php       running    myorg/genotool:v3.2      2d ago   │   │
│  │  genotool-prd-queue     running    myorg/genotool:v3.2      2d ago   │   │
│  │  genotool-prd-scheduler running    myorg/genotool:v3.2      2d ago   │   │
│  │  genotool-prd-nginx     running    myorg/genotool:v3.2      2d ago   │   │
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
- `r` — Refresh container status via SSH
- `escape` — Back to Dashboard

## 3. Deploy Screen - Version Selection

Select an environment (left) and a version from GitHub tags/releases (right). Versions are fetched asynchronously on mount.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Deploy Genotool                                                            │
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
1. Select an environment in the left `ListView` (auto-selected if only one)
2. Select a version in the right `ListView`
3. Confirmation modal appears

## 4. Deploy Screen - Confirmation Modal

Modal dialog shown after selecting environment + version.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Deploy Genotool                                                            │
│                                                                             │
│  ┌─ Environment ──┐ ┌─ Ve┌──────────────────────────────────────┐────────┐  │
│  │                │ │    │                                      │        │  │
│  │ ▶ PRD          │ │ ▶ v│        Deploy Genotool?              │        │  │
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
│  Deploy Genotool                                                            │
│                                                                             │
│  DEPLOYING Running ./rerun.sh v3.4.0 in /opt/apps/genotool                 │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ Connecting to prod-web-01...                                            ││
│  │ Running ./rerun.sh v3.4.0 in /opt/apps/genotool                        ││
│  │ Pulling ghcr.io/myorg/genotool:v3.4.0...                               ││
│  │ v3.4.0: Pulling from myorg/genotool                                     ││
│  │ a2abf6c4d29d: Already exists                                            ││
│  │ c5608244554d: Pull complete                                             ││
│  │ Digest: sha256:abc123...                                                ││
│  │ Status: Downloaded newer image                                          ││
│  │ Stopping genotool-prd-php...                                            ││
│  │ Stopping genotool-prd-queue...                                          ││
│  │ Stopping genotool-prd-nginx...                                          ││
│  │ Starting genotool-prd-php...                                            ││
│  │ Starting genotool-prd-queue...                                          ││
│  │ Starting genotool-prd-nginx...                                          ││
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
│  Deploy Genotool                                                            │
│                                                                             │
│  SUCCESS Deploy completed successfully (exit code 0)                        │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ Connecting to prod-web-01...                                            ││
│  │ Running ./rerun.sh v3.4.0 in /opt/apps/genotool                        ││
│  │ Pulling ghcr.io/myorg/genotool:v3.4.0...                               ││
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

## 8. Log Viewer Screen

Live streaming of Docker container logs via `docker logs -f --tail 100`.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Shipyard - Docker Deployment Manager                              12:34:56  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Logs: genotool-prd-php on prod-web-01                        FOLLOWING    │
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

## Screen Navigation

```
                    ┌───────────┐
                    │ Dashboard │ (home)
                    └─────┬─────┘
                          │
              ┌───────────┼───────────┐
              │ enter     │           │ s
              ▼           │           ▼
      ┌───────────┐      │    ┌───────────┐
      │Application│      │    │  Servers   │
      └─────┬─────┘      │    └───────────┘
            │             │
      ┌─────┼─────┐      │
      │ d   │ l   │      │
      ▼     ▼     │      │
┌──────────┐ ┌────────┐  │
│  Deploy  │ │  Logs  │  │
├──────────┤ └────────┘  │
│ Confirm  │             │
│ (modal)  │             │
└──────────┘             │

Key: ▼ = push_screen()
     escape = pop_screen() (back)
```

## Implementation Notes

- All screen-level key bindings use `priority=True` to ensure they fire even when child widgets (DataTable, TabbedContent, ListView) have focus
- Dashboard uses `on_data_table_row_selected` instead of an `enter` binding because DataTable handles `enter` internally
- Deploy screen uses index-based selection (not widget IDs) for version/environment lists, since version tags can contain dots which are invalid in Textual IDs
- Servers screen stores column keys from `add_columns()` for use with `update_cell()`, since Textual column keys are objects, not label strings
- All async operations (SSH connectivity, GitHub API, deploy streaming) run in Textual workers via `run_worker()`
