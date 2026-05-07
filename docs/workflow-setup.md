# Workflow Worker Setup

The Render Workflow service for SF Pulse Python is created manually in the Dashboard because Render Workflows are not yet first-class in `render.yaml`.

## 1. Create the workflow service

1. Render Dashboard → **New** → **Workflow**.
2. Connect your GitHub fork of `render-examples/sf-pulse-python`. Branch: `main`.
3. **Name**: `sf-pulse-python-workflow`
4. **Build Command**: `pip install --upgrade uv && uv sync --frozen`
5. **Start Command**: `uv run python -m workflow.main`
6. **Plan**: Starter
7. Under **Environment**, attach the `sf-pulse-python-env` env group plus:

   | Variable | Source |
   | --- | --- |
   | `DATABASE_URL` | Copy from `sf-pulse-python-db` connection string |

   > Workflow services don't currently support `fromDatabase`/`fromService` references in the YAML the same way web services do, so set `DATABASE_URL` directly here once.

8. Save and deploy.

## 2. Note the slug

After the worker is live, go to the service's **Settings** page. Copy the **Slug** value. You'll set it on the cron service as `SF_PULSE_WORKFLOW_SLUG`.

## 3. Wire up the cron trigger

On the `sf-pulse-python-daily` cron service (provisioned by `render.yaml`):

| Variable | Value |
| --- | --- |
| `RENDER_API_KEY` | Dashboard → Account Settings → API Keys → New API Key |
| `SF_PULSE_WORKFLOW_SLUG` | Slug from step 2 |

The cron entrypoint (`bin/trigger_workflow.py`) reads these env vars and calls:

```python
client = Render()
run = client.workflows.run_task(f"{slug}/daily-refresh", [])
```

## 4. Test locally

You can run the worker locally with the Render CLI:

```sh
render workflows dev -- python -m workflow.main
```

Then in another terminal, trigger a task manually:

```python
from render_sdk import Render
r = Render()
r.workflows.run_task("sf-pulse-python-workflow/daily-refresh", [])
```

Or hit the orchestrator directly without the Workflows runtime:

```sh
uv run python -c "import asyncio; from workflow.tasks.daily_refresh import daily_refresh; asyncio.run(daily_refresh())"
```

## Troubleshooting

- **`RENDER_API_KEY` not configured** in the cron logs → set it on the cron service env vars.
- **`Task not found`** → double-check the workflow slug and that the worker has deployed at least once.
- **Tasks timeout** → the orchestrator has a 600s timeout. If sources are slow, increase the timeout on the `daily_refresh` decorator.
- **No restaurants/events appear after a run** → check that `LLM_API_KEY` is set on the workflow service. Without it, only the regex sources (SFist, Michelin, FunCheap, FAMSF, Cal Academy) produce results.
