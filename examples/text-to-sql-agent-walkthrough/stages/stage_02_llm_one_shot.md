# Stage 02 — One-shot LLM → SQL

## What's new

- `ChatAnthropic` is added. One LLM call per question.
- A `SYSTEM_PROMPT` instructs the model to emit a fenced `sql` block.
- `extract_sql()` strips the SQL out of the response.
- `run_sql()` executes it. Same `sqlite3` primitive from stage 01.

The graph is still a single node. The user's question now actually matters.

## What to read first

1. `HARDCODED_SCHEMA` — what the model "knows" about the database.
2. `SYSTEM_PROMPT` — the contract: emit SQL in a fenced block, SELECT only, LIMIT 5.
3. `extract_sql()` — defensive parsing of LLM output.
4. `answer()` — orchestrates the three steps: LLM call → parse → execute.

## Tradeoff vs. stage 01

| | Stage 01 | Stage 02 |
|---|----------|----------|
| Flexibility | None — query is hardcoded | Anything the model can write |
| Determinism | Total | Best-effort (model output varies) |
| Failure modes | None | Hallucinated columns, syntax errors, wrong table |
| Cost | $0 | One LLM call per question |

## Alternative we did not take

**Use OpenAI structured output / tool-calling for the SQL** instead of regex-extracting from a fenced block. Structured output is more reliable in production, but it hides the model's reasoning — for learning, the fenced-block pattern keeps the prompt visible and the parsing transparent.

## Aha insight

> The schema is the **only** context that matters. If the model has the table and column names, it can usually write the SQL. The rest of the agent stack we're about to build is just better ways of getting the right schema in front of the model at the right time.

## Failure to provoke (try this!)

Ask `"Which 5 albums have the most tracks?"`. There's a good chance the model gets it right because the schema is small. Now imagine a real database with 200 tables — the entire schema would not fit in the prompt. **That problem is what stages 03 and 04 solve.**

## Exercise

1. Delete the `Album` line from `HARDCODED_SCHEMA`. Re-run any album-related question. Observe the model either hallucinate the column name or refuse.
2. Add a deliberately wrong type (e.g. `Album(AlbumId PK, Title TEXT, ArtistId TEXT FK)`). Notice how the wrong schema does *not* cause an SQL execution error here — the model just produces SQL that runs because SQLite is permissive. **This is why stage 03 stops trusting your hand-written schema description.**
