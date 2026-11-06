# Instructions for AI agents

This kit was built and tested with Claude, but any agent with the abilities listed in [README.md](README.md#which-ai-it-needs) can run it.

**Read [CLAUDE.md](CLAUDE.md) and follow it as your own instructions.** Where it says "Claude," it means you. Then follow [SETUP.md](SETUP.md) for a new setup, and [job-finder/PLAYBOOK.md](job-finder/PLAYBOOK.md) for job-search runs and resume drafts.

## Mapping Claude-specific pieces to your own

| The docs say | Do this instead |
|---|---|
| The `job-finder` MCP server, "registered by the installer" | The installer writes Claude's `.mcp.json`. Register the same stdio server in your agent's MCP config. The command is your Python with `-I` plus the absolute path to `job-finder/mcp/server.py`; copy it from `.mcp.json` after running the installer. |
| Tool names like `setup_mark`, `job_save`, `resume_draft_save` | Same tools, from that MCP server. |
| **Connectors** (Indeed, ZipRecruiter, Dice, Crunchbase) | Use your platform's equivalents if it has them. If not, skip them: LinkedIn's public feed and company job boards come from the kit's own server. Say which sources are missing in the daily summary. |
| **Scheduled tasks** in the Claude desktop app | Your platform's scheduler or routines: an unattended run in this folder, with the same tools, using the prompts in SETUP.md Step 9. If there is none, the person asks for each run by hand; tell them so during setup. |
| `PushNotification` | Your notification tool, if any. Otherwise put the same one-line summary at the top of the run's output. |
| `.claude/launch.json` and the "job-report" preview | Optional. The report is a plain local web server: `python -I job-finder/app/server.py`, then open http://127.0.0.1:8765. |

The hard rules in CLAUDE.md apply to every agent without exception: never apply, sign in, submit forms, or contact anyone, and every request goes through the guard.
