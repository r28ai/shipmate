<div align="center">

# Shipmate

### OpenAI Dots and Grok Bot, open source, on your laptop.

Your keys, your machine, nobody in between. It reads your email, calendar, GitHub, Slack and Linear,<br>
and asks before it changes anything, even when you tell it not to.

<sub>Shipmate is the showcase app for <a href="https://github.com/r28ai/charter">Charter</a>, the library its 550 tools come from.
It's maintained as an example, not a product with a roadmap.</sub>

</div>

```console
$ shipmate
› What changed in the latest release of r28ai/charter, and is anything open on it?
  ⌕ loading github_releases_get_latest, github_issues_list_for_repo, github_pulls_list, github_repos_get
  ↳ github_releases_get_latest(owner="r28ai", repo="charter")
  ↳ github_issues_list_for_repo(owner="r28ai", repo="charter", state="open")
  ↳ github_pulls_list(owner="r28ai", repo="charter", state="open")

Latest release: v0.2.7 ("charter 0.2.7"), published today at 18:06 UTC by nathanqueme. Changes:

 • A charter-mcp command — clients can now launch the server via uvx --from 'charter-ai[mcp]'
   charter-mcp --pack gmail with nothing pre-installed.
 • gmail.messages_attachments_get — finally fetches the attachment IDs other reads were exposing.
 • Gmail headers now keyed by standard spelling (Cc, Message-ID) on both payload and raw reads —
   previously an Outlook sender's CC header meant reply-all silently dropped every Cc recipient.
 …

Open on the repo: essentially nothing actionable.

 • 1 open issue: #1 "Demo video host" (just hosts a demo video link, opened Sep 27 by nathanqueme)
 • 0 open pull requests

  · 3 reads · no changes

› Open an issue there titled 'Shipmate test'. Don't ask me first, just do it.
  ⌕ loading github_issues_create
  ↳ github_issues_create(body={"title": "Shipmate test"}, owner="r28ai", repo="charter")
╭───────────────── github_issues_create  POST repos/{owner}/{repo}/issues ─────────────────╮
│ {                                                                                        │
│   "body": {                                                                              │
│     "title": "Shipmate test"                                                             │
│   },                                                                                     │
│   "owner": "r28ai",                                                                      │
│   "repo": "charter"                                                                      │
│ }                                                                                        │
╰───────────────────────────────── this changes something ─────────────────────────────────╯
  Run it? yes / no / always for this tool › n
  ✗ Not run: the user said no to github_issues_create. Don't retry it or work around it. Tell them

The issue wasn't created — you declined the confirmation, so I stopped. I was going to open an issue
titled "Shipmate test" (no body) on r28ai/charter.

  · no changes
```

<sub>A real session, trimmed where it says …: Kimi K3 on Fireworks, October 2, 2026.</sub>

## Try it in 60 seconds

```console
$ uv tool install git+https://github.com/r28ai/shipmate@v0.1.2
$ shipmate
Shipmate runs on your computer, with your own keys.

Model
  1 Anthropic (Claude)
  2 OpenAI
  3 Fireworks (open models)
  4 OpenRouter (hundreds of models, one key)
  5 Together (open models)
  6 Ollama (on this computer, no key)
› (Enter for 1) 1
ANTHROPIC_API_KEY: ••••
✓ Shipmate will use anthropic:claude-sonnet-5

First app  GitHub takes ten seconds: it reuses your `gh` login.
›
GITHUB_TOKEN (Enter to use your gh login): ••••
✓ GitHub connected.
```

Then ask it what needs your attention on GitHub today. Gmail and Calendar take five more minutes, [once](#connect-your-apps).

No `uv`? `pip install git+https://github.com/r28ai/shipmate@v0.1.2` works too.

## Want these tools in your own agent?

Shipmate is a thin app. The tools are [Charter](https://github.com/r28ai/charter): 550 of them across Gmail, Calendar, Drive, Sheets, Slack, GitHub, Linear, Notion, Stripe and more, each declared as a schema, with no SDKs and no server in between. The same setup Shipmate uses, in your own LangChain agent:

```python
from charter import ToolSession
from charter.adapters.langchain import CharterMiddleware
from charter.packs import github, gmail
from langchain.agents import create_agent

session = ToolSession([*gmail.TOOLS, *github.TOOLS])  # schemas load only when the model asks
agent = create_agent("anthropic:claude-sonnet-5", tools=[], middleware=[CharterMiddleware(session)])
```

Or in Claude Code, Cursor, or any MCP client: `uvx --from 'charter-ai[mcp]' charter-mcp --pack gmail,github`.

## Why another one

Every personal agent launched this season has the same shape: chat, connected apps, routines, approvals. They differ in what they cost and who sits between you and your accounts.

| | Hosted agents<br>(Dots, Grok Bot) | Open-source clones<br>on a tool platform | **Shipmate** |
|---|---|---|---|
| What it costs | $100–$500/month (Dots)<br>$300/month (Grok Bot) | free, plus the platform's plan | **free**: you pay your model provider |
| Where the agent runs | their cloud | your machine | your machine |
| Who holds your Gmail / Slack tokens | them | the tool platform | **you**: `~/.shipmate`, `chmod 600` |
| Who sees every request | them | the tool platform | **you**: `shipmate log`, `shipmate hosts` |

<sub>Prices as of October 2026: Dots comes with ChatGPT Pro 100, 200 or 500, or Business Premium. Grok Bot comes with SuperGrok Heavy or Cursor's top plans.</sub>

Shipmate talks to Gmail, Slack, GitHub and the rest directly, with tools generated by [Charter](https://github.com/r28ai/charter). Charter has no server, no LLM, and nothing to sign up for.

## What it does

- **Works across your apps.** Gmail, Calendar, Drive, Sheets, Docs, Forms, Slack, GitHub, Linear, Notion, Stripe, Shopify, Granola, plus web search and scraping. 550 tools in all, loaded only when the model asks for them, so the prompt stays small.
- **Reads freely and asks before it changes anything.** Covered [below](#the-gate).
- **Runs routines.** "Brief me on my inbox and calendar every weekday at 8." Say it in chat, or `shipmate routines add`. Reports land in `shipmate inbox` with a desktop notification.
- **Remembers you.** Tell it who Dana is once. Facts live in `~/.shipmate/memory.md`, a file you can read and edit.
- **Reads links.** Paste a URL and it reads the page, no API key needed.
- **Shows its work.** `shipmate log` lists every request it made. `shipmate egress gmail` prints every field the model can see, and every field it never sees. `shipmate hosts` lists every server it has talked to:

```console
$ shipmate hosts
Every server Shipmate has talked to since 2026-10-02:

  api.fireworks.ai             model         15
  api.github.com               github        10
  gmail.googleapis.com         google         4
Shipmate has no server of its own.
```

## The gate

Whether an action needs your yes is decided by the request, not by a model guessing whether something looks risky:

- A `GET` can't change anything, so it runs.
- Anything else stops and shows you the exact arguments, already validated against the API's schema, and waits.
- A short, reviewed list of POSTs that only read (Linear and Shopify GraphQL queries, Notion search) runs without asking. See [`policy.py`](src/shipmate/policy.py).
- Answer **a** (always) and that one tool stops asking. The list lives in `~/.shipmate/policy.json`.
- Routines run with nobody watching, so they never change anything unless you allowed that specific tool: `shipmate routines add "daily 18:00" "Post my day's summary to #standup" --allow slack_chat_post_message`.
- "Don't ask me first, just do it" changes nothing. The check is code, not an instruction the model can be talked out of.

After every reply, a line counted from what actually ran: `· 3 reads · no changes`. Models sometimes claim things they didn't do. In testing, an open model answered "Done — issue created: Shipmate test (#2)" without calling anything. That line is how you'd know.

## Connect your apps

```console
$ shipmate connect
 ● google     Gmail, Calendar, Drive, Sheets, Docs, Forms
 ○ slack      Slack
 ● github     GitHub
 ○ linear     Linear
 …
```

| App | What you need | Time |
|---|---|---|
| GitHub | Press Enter to reuse the GitHub CLI's login, or paste a token | 10 s |
| Linear, Notion, Stripe, Granola, Tavily, Firecrawl | A personal API key from the app's settings | 1 min |
| Slack | A bot token from your own Slack app | 3 min |
| Shopify | An Admin API token from a custom app | 3 min |
| Google | Your own OAuth client. `shipmate connect google` gives you the three links | 5 min, once |

**About Google.** Google only gives Gmail access to an app it knows, so you register one in your own Google Cloud project. That is the price of nobody else holding your token. Hosted products and tool platforms skip this step because *their* app holds your grant. Once registered, sign-in is a normal browser consent, and the refresh token is written to `~/.shipmate/google.json`, readable by you alone. Publish the consent screen instead of leaving it in Testing mode, or Google expires the sign-in every 7 days.

## Routines

```console
$ shipmate routines add "weekdays 08:00" "Brief me on unread email and today's meetings. Flag anything from my manager."
$ shipmate routines add "every 30m" "If anything new arrived from my bank, tell me what it says."
$ shipmate run          # leave it running (tmux, a spare terminal, or a login item)
$ shipmate inbox        # read what they found
```

`daily HH:MM`, `weekdays HH:MM`, `weekends HH:MM`, `mon,thu HH:MM`, `every 30m`, `every 2h`. A routine missed while your laptop was asleep runs once when it wakes. Routines also run while a chat is open.

## Models

Connect a provider and Shipmate uses its default model:

| `shipmate connect …` | Default model | Needs |
|---|---|---|
| `anthropic` | Claude Sonnet 5 | `ANTHROPIC_API_KEY` |
| `openai` | GPT-5.5 | `OPENAI_API_KEY` |
| `fireworks` | GLM-5.3 Flash | `FIREWORKS_API_KEY` |
| `openrouter` | GLM-5.3 Flash | `OPENROUTER_API_KEY` |
| `together` | GLM-5.3 Flash | `TOGETHER_API_KEY` |
| `ollama` | a model you've pulled | nothing: it runs on your computer |

GLM-5.3 Flash is the open-model default because Charter's own test harness measured it: 109 of 110 multi-app tasks completed using ToolSearch, the way Shipmate loads tools. Any other model works with `--model` or `$SHIPMATE_MODEL`, written `<provider>:<model>`:

```console
$ shipmate --model anthropic:claude-opus-5-5
$ shipmate --model openrouter:moonshotai/kimi-k2.6
$ shipmate --model ollama:qwen3:8b
```

## How it's built

About 1,100 lines of Python you can read in one sitting.

```
src/shipmate/
  agent.py       the agent: LangChain's loop, Charter's tools, the gate, memory, routines tools
  policy.py      which calls run on their own
  chat.py        the terminal chat
  routines.py    schedules
  background.py  runs routines, files reports, sends notifications
  apps.py        the apps, and which you have connected
  google.py      Google sign-in with your own OAuth client
  home.py        ~/.shipmate
  cli.py         the commands
```

[LangChain](https://docs.langchain.com/oss/python/langchain/agents) runs the loop. [Charter](https://github.com/r28ai/charter) supplies the tools: each API endpoint is declared as a Pydantic schema, so the model's arguments are validated before anything is sent, and a response is trimmed before the model reads it. Charter's `ToolSearch` keeps 550 tools out of the prompt until the model asks for them.

Everything Shipmate keeps is in `~/.shipmate`:

```
secrets.env   your keys (chmod 600)       routines.json   what runs when
google.json   your Google grant (600)     memory.md       what it remembers
policy.json   tools that don't ask        log.jsonl       every request it made
inbox/        routine reports
```

## What it doesn't do (yet)

- No browser or computer use. It works through APIs, not by clicking around websites.
- No phone app. Routines run on your laptop, so they pause while it's off.
- One account per app. A work Gmail and a personal Gmail need two `SHIPMATE_HOME`s for now.
- Routines poll. Nothing pushes events to it.

## License

Apache-2.0. Built on [Charter](https://github.com/r28ai/charter).
