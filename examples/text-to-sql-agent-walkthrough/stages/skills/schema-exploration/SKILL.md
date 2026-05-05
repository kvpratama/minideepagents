---
name: schema-exploration
description: Lists tables, describes columns and data types, identifies foreign key relationships, and maps entity relationships in a database. Use when the user asks about database schema, table structure, column types, what tables exist, ERD, foreign keys, or how entities relate.
---

# Schema Exploration Skill

## Workflow

### 1. List All Tables

Use the `sql_db_list_tables` tool to see all available tables in the database. This returns the complete list of tables you can query.

### 2. Get Schema for Specific Tables

Use `sql_db_schema` with table names to examine:

- **Column names** — what fields are available.
- **Data types** — INTEGER, TEXT, DATETIME, etc.
- **Sample data** — three example rows to understand content.
- **Primary keys** — unique identifiers for rows.
- **Foreign keys** — relationships to other tables.

### 3. Map Relationships

Identify how tables connect:

- Look for columns ending in `Id` (e.g. `CustomerId`, `ArtistId`).
- Foreign keys link to primary keys in other tables.
- Document parent-child relationships.

### 4. Answer the Question

Provide clear information about:

- Available tables and their purpose.
- Column names and what they contain.
- How tables relate to each other.
- Sample data to illustrate content.

## Example: "What tables are available?"

**Step 1:** Use `sql_db_list_tables`.

**Response:**

```
The Chinook database has 11 tables:
1. Artist - Music artists
2. Album - Music albums
3. Track - Individual songs
4. Genre - Music genres
5. MediaType - File formats (MP3, AAC, etc.)
6. Playlist - User-created playlists
7. PlaylistTrack - Tracks in playlists
8. Customer - Store customers
9. Employee - Store employees
10. Invoice - Customer purchases
11. InvoiceLine - Individual items in invoices
```

## Example: "How do I find revenue by artist?"

**Step 1:** Identify tables needed — `Artist`, `Album`, `Track`, `InvoiceLine`, `Invoice`.

**Step 2:** Map relationships:

```
Artist (ArtistId)
  ↓ 1:many
Album (ArtistId, AlbumId)
  ↓ 1:many
Track (AlbumId, TrackId)
  ↓ 1:many
InvoiceLine (TrackId, UnitPrice, Quantity)
```

**Step 3:** Hand off to the `query-writing` skill to execute.

## Quality Guidelines

**For "list tables" questions:** show all table names with brief descriptions; group related tables.

**For "describe table" questions:** list columns with types, explain content, show sample data, note PK/FK and cross-table relationships.

**For "how do I query X" questions:** identify required tables, map the JOIN path, suggest the next step (use the `query-writing` skill).
