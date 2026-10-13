# Event calendars

One CSV per calendar (`fomc.csv`, `cpi.csv`, ...), loaded with `calendars.load(name)`.
Columns: `date`, `source_url` (required); `announced`, `event`, `notes` (optional).

Every date must be checked against an official source and the URL recorded.
Never type event dates from memory into a strategy file.
