# Domain Knowledge for Template Parsing

## Definitions

- Main template sheet: the sheet where users are expected to input data (not instruction or lookup sheets).
- Header row: the row containing column names (for example, ID, Name, Price).
- Data row: the first row where users will start entering data.

## Key Domain Insight

- These files are templates, not filled datasets.
- The correct `data_row` is often empty (or mostly empty).
- The `data_row` marks the start of input space, not an already-filled row.
- Rows with content are not automatically better candidates than empty rows.
