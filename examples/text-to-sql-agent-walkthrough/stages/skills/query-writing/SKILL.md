---
name: query-writing
description: Writes and executes SQL queries from simple SELECTs to complex multi-table JOINs, aggregations, and subqueries. Use when the user asks to query a database, write SQL, run a SELECT statement, retrieve data, filter records, or generate reports from database tables.
---

# Query Writing Skill

## Workflow for Simple Queries

For straightforward questions about a single table:

1. **Identify the table** — which table has the data?
2. **Get the schema** — use `sql_db_schema` to see columns.
3. **Write the query** — `SELECT` relevant columns with `WHERE`/`LIMIT`/`ORDER BY`.
4. **Execute** — run with `sql_db_query`.
5. **Format answer** — present results clearly.

## Workflow for Complex Queries

For questions requiring multiple tables:

### 1. Plan Your Approach

**Use `write_todos` to break down the task:**

- Identify all tables needed.
- Map relationships (foreign keys).
- Plan the JOIN structure.
- Determine aggregations.

### 2. Examine Schemas

Use `sql_db_schema` for **each** table to find join columns and needed fields.

### 3. Construct Query

- `SELECT` — columns and aggregates.
- `FROM`/`JOIN` — connect tables on FK = PK.
- `WHERE` — filters before aggregation.
- `GROUP BY` — all non-aggregate columns.
- `ORDER BY` — sort meaningfully.
- `LIMIT` — default 5 rows.

### 4. Validate and Execute

Check that all JOINs have conditions and `GROUP BY` is correct, then run the query.

## Example: Revenue by Country

```sql
SELECT
    c.Country,
    ROUND(SUM(i.Total), 2) AS TotalRevenue
FROM Invoice i
INNER JOIN Customer c ON i.CustomerId = c.CustomerId
GROUP BY c.Country
ORDER BY TotalRevenue DESC
LIMIT 5;
```

## Error Recovery

If a query fails or returns unexpected results:

1. **Empty results** — verify column names and `WHERE` conditions against the schema; check for case sensitivity or `NULL`.
2. **Syntax error** — re-examine JOINs, `GROUP BY` completeness, and alias references.
3. **Timeout** — add stricter `WHERE` filters or `LIMIT` to reduce the result set, then refine.

## Quality Guidelines

- Query only relevant columns (not `SELECT *`).
- Always apply `LIMIT` (5 default).
- Use table aliases for clarity.
- For complex queries: use `write_todos` to plan.
- Never use DML statements (`INSERT`, `UPDATE`, `DELETE`, `DROP`).
