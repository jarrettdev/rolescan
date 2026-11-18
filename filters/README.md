# Filters

`active.json` is the document the kit runs. It is **not** committed: `setup.sh`
copies `example.json` to `active.json` on first run, and `.gitignore` keeps your
version local.

- `JOBKIT_FILTERS=/path/to/file.json` overrides the path for one run.
- With no `active.json` the kit falls back to `example.json`, so a fresh clone
  still runs.

## Shape

```json
{
  "note": "why this set exists",
  "base": { "...": "shared hiring.cafe search config" },
  "locations": { "US": ["United States"], "US_ALT": ["..."] },
  "filters": [
    { "name": "Software Engineer", "location": "US", "overrides": { "jobTitleQuery": "..." } }
  ],
  "blocked_companies": ["somecompany"],
  "title_exclude": ["Senior", "Staff", "Manager", "Lead", "Principal", "Sr", "SR"]
}
```

Each `filters[]` entry is `base`, then the named location preset, then its own
`overrides`. `jobTitleQuery`, `technologyKeywordsQuery` and `searchQuery` use
quoted terms, bare words, `AND`, `OR`, `NOT` and parentheses.

- `blocked_companies` drops a company everywhere (lowercase, exact on the
  company name).
- `title_exclude` is a regex of title words never to notify. The default drops
  senior titles but keeps **Graduate**, **New Grad** and **Intern** shapes, so
  an early-career search works out of the box.
- `validate` with `doctor.sh`, which prints the failing JSON pointer.

Checked against `schema.json` (JSON Schema 2020-12). Examples:

```bash
python3 -m json.tool filters/active.json > /dev/null   # syntax
./doctor.sh                                            # schema + pointers
```
