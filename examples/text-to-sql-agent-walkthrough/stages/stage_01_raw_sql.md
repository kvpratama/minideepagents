# Stage 01 — Raw SQL

## What's new

Everything. This is the baseline:

- `sqlite3` opens Chinook in **read-only** mode (`mode=ro`).
- A hardcoded SQL string is executed and the rows are printed.
- A single-node `StateGraph` wraps the call so Studio can show you the trace.

There is **no LLM**. The whole file is ~50 lines.

## What to read first

1. `DEMO_SQL` — the fixed query.
2. `run_sql()` — the only primitive that ever talks to the database.
3. `execute_demo()` — the lone graph node.
4. The `builder = StateGraph(...)` block — compiles into the `graph` symbol that LangGraph Studio loads.

## Tradeoff vs. previous stage

There is no previous stage. The tradeoff to call out is what we *gave up* to start here: **flexibility**. The query is hardcoded, so the user's question doesn't matter. Stage 02 fixes that.

## Alternative we did not take

Use [SQLAlchemy](https://docs.sqlalchemy.org/) directly instead of `sqlite3`. SQLAlchemy is what `langchain_community.SQLDatabase` uses under the hood, and it would generalize to Postgres/MySQL with one line. We chose `sqlite3` because the standard library is enough to make the primitive nature obvious — *nothing magic is happening here*.

## Aha insight

> The agent's only superpower is generating SQL strings. Everything else — planning, tools, schemas, memory — exists to help it generate a *better* string. If you remember nothing else from this walkthrough, remember: **the bottom of the stack is `cur.execute(sql)`**.

## Run it

```bash
# CLI
uv run python stages/stage_01_raw_sql.py "How many customers are from Canada?"

# Studio (then pick "stage_01_raw_sql" in the dropdown)
make studio
```

## Exercise

Change `DEMO_SQL` to count customers per country and re-run. Notice that **the agent gets smarter not by changing this layer, but by *generating* the right query for the user's question.** Stage 02 is where that starts.
