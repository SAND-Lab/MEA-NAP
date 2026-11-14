---
key: spreadsheet
name: Recording spreadsheet
tab: Data
labels: Spreadsheet file; Spreadsheet range; Custom group order
params: spreadsheet_file_name, spreadsheet_range, custom_grp_order
related: data_input, output
---
The table that lists every recording in the batch, with its age and group. It decides what is analysed and how recordings are grouped and compared.

## What it does

The columns are read **by position**, not by header:

| Column | Holds | Example |
|---|---|---|
| 1 | Recording name, with no extension | `MEC_DIV14_A1` |
| 2 | Age (DIV), a number | `14` |
| 3 | Group or genotype | `WT` |
| 4 (optional) | **Ground**: channel IDs to silence, comma-separated | `15, 82` |

A `StimConditions` column is found by its header, wherever it is (MEA-Stim only). The first row is the header.

**Spreadsheet range** sets which rows are read. The numbers are file lines, and the header is line 1. The default, `A2:A100000`, reads every row. `A2:A3` reads only the first two recordings, and `2:3` works too. The letters are ignored.

**Custom group order** is a comma-separated list such as `WT,KO`. It sets the order of groups in the group-comparison figures and in the step-5 statistics. Leave it empty to order groups alphabetically.

## Choosing a value

- Click **Edit…** to open the sheet in a table editor, or to start one from the raw data folder. It fills in the names, and the DIV wherever a name contains one (`DIV14`). It checks names, DIVs and groups as you type. It never guesses the genotype, because a wrong guess would silently mix groups.
- Use the range to test settings on a few recordings before running the whole batch.

## How MEA-NAP uses it

Every step loops over the rows in the range. Recordings that share a column-2 value are pooled as one age, and recordings that share a column-3 value as one group. Electrodes in the Ground column have their spikes removed before steps 2–4.

## Things to watch for

- **Save the sheet as `.csv`.** The file picker offers `.xlsx`, but the run reads the sheet with a CSV reader and fails on an Excel file.
- Group names are compared as exact text, so `WT` and `wt` are two different groups.
- Column 2 has to be a number. `DIV14` in that column stops the run.
