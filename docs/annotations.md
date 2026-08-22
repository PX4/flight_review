# Annotations

Flight Review plots what the vehicle recorded. It has no way to show what somebody *knows* about
a stretch of that flight - ground truth from a test sheet, a reviewer's note, the verdict of an
external analyzer. Today that knowledge lives in a spreadsheet next to the browser, and matching
it against a plot is done by eye.

Annotations close that gap. One or more YAML files are uploaded alongside the log; the intervals
they describe are listed in a compact table above the plots, and drawn as coloured bars along the
bottom edge of the plot each one names.

Everything is optional at every step: a log uploaded without annotations renders exactly as it
does today.

## The file

```yaml
version: 1                    # optional; a bare list of sources is version 1
sources:
  - name: Ground Truth        # who is saying this
    color: "#b3261e"          # optional default for this source's categories
    annotations:
      - category: takeoff_wobble
        graph: Roll Angle     # the plot's title, or its 'Nav-...' fragment id
        color: "#a06000"      # optional, overrides the source colour
        intervals:
          - start: "01:23"
            end: "01:40"
            annotation: "oscillation"       # optional free text
          - start: "02:10"                  # no end -> vertical dotted line
            value: "roll rate 12.4 deg/s"   # optional free text drawn at the line
```

The top level may also be the bare list of sources - `- name: Ground Truth` … - which is what a
hand-written file usually looks like. Both parse to the same thing.

| Field | Where | Meaning |
|---|---|---|
| `version` | document | Schema the file was written against. Optional, defaults to 1. |
| `name` | source | Shown in the table's *annotation* column and on every bar the source draws. Required. |
| `color` | source, category | `#rgb`, `#rrggbb` or a CSS colour name. Optional; categories otherwise cycle `config.colors8`, the palette the plots themselves use, less its black entry. |
| `category` | annotation | What this is. One category is one bar on one plot. Required. |
| `graph` | annotation | Which plot to draw on: its title (`Roll Angle`) or its anchor (`Nav-Roll-Angle`). Required. |
| `start`, `end` | interval | `mm:ss`, `h:mm:ss`, `mm:ss.mmm`, or seconds as a number. `end` is optional. |
| `annotation` | interval | Free text, shown in the table. |
| `value` | interval | Free text, drawn beside the dotted line of a point interval. |

`value` is a **string**, not a number, because a Flight Review plot carries several series: a bare
`12.4` cannot say what it measured, and `roll rate 12.4 deg/s` can.

### Times are the boot clock

`start` and `end` are read the way the x-axis is labelled. `plotting.py` formats a tick by
dividing the raw microsecond timestamp by 1e6 with **no** subtraction of `ulog.start_timestamp`,
so `01:23` on the axis is 83 seconds since the board booted, not since the log began. An
annotation time is therefore whatever you read off the axis, and the conversion is a
multiplication.

This is also why the feature never touches the ULog: no message names, no field names, no
timestamps are read to place an annotation. A change to the log format cannot invalidate one.

## Where annotations are stored

In `Logs.Annotations`, a `TEXT` column holding normalized, versioned JSON
(`{"v": 1, "sources": [...]}`).

The alternative was a sidecar file beside the `.ulg`, as the KML and preview image are stored. The
column wins on the part nobody enjoys maintaining:

* **Deletion is free.** `edit_entry.py` and `prune_old_logs.py` already `DELETE FROM Logs`. A
  sidecar needs its own `os.unlink` in both, and the precedent is not encouraging - `prune_old_logs.py`
  does not clean up `.kml` files today, so that path already leaks.
* **Backup is free.** `backup_db.py` dumps the database. A sidecar is invisible to it.
* **Writing is atomic.** The annotations go in on the same `INSERT` as the log entry, inside the
  same transaction, so there is no window where a file exists with no row pointing at it.
* **Nothing new to configure.** No directory, no `config_default.ini` key, no `makedirs` in
  `setup_db.py`.

Serializing structure into a `TEXT` column is the existing idiom here: `ErrorLabels` and
`FlightModeDurations` both do it. The column is added to `Logs` - the table that already holds
everything the *uploader* supplies - and not to `LogsGenerated`, which is a cache of what the ULog
itself says. Existing databases pick it up through the same
`PRAGMA table_info` → `ALTER TABLE … DEFAULT ''` upgrade branch that added the nine columns before
it, so `python setup_db.py` is the whole migration.

## Two schema versions

`_STORED_VERSION` versions the JSON in the column; `_YAML_VERSION` is the highest `version:` an
uploaded file may declare. They are separate because they move for different reasons: the stored
shape can change for something the YAML never sees (a new computed field), and a file's schema can
change without the storage doing so.

The version belongs *in the file* because the file outlives this server. Annotations get generated
by external tools, committed to repositories, and re-uploaded months later; the only party that
can say which schema a file was written against is the file. A file declaring a newer version is
refused by name - the uploader can then go and find a server that understands it, which a
half-rendered page would never tell them.

## Validate loudly, render quietly

The two halves of the feature have opposite failure policies, on purpose.

**Upload rejects.** A malformed file fails the upload with a 400 naming the problem
(`Invalid annotations file: Ground Truth/takeoff_wobble: interval ends before it starts`), while
the user is still looking at the form and can fix it. Validation runs *before* the `.ulg` is
written, so a rejected upload leaves nothing behind.

`from_upload` guarantees that by wrapping its whole body the way `helper.load_ulog_file` does:
`except ValueError: raise` passes through the messages written for the uploader, and one
`except Exception` converts everything else into a `ValueError` too. Enumerating the exceptions a
hostile YAML file can provoke does not work - the first attempt missed `RecursionError` from the
parser and `OverflowError` from `.inf` - and each one missed is a 500 for something the uploader
could have fixed. Like `load_ulog_file`, this attributes any failure inside the parse boundary to
the input; that is the right default when the boundary's only job is to read a user's file.

**Rendering never fails.** `render` swallows every exception. By the time a page is being drawn,
the alternative to "no annotations" is "no plots", and nobody's annotation is worth someone else's
log page. A log whose column is *empty* renders with no annotations section at all; a log whose
column holds something this server cannot use - corrupt JSON, or a `_STORED_VERSION` it does not
know - still gets the section, carrying one line saying so, with the reason on the server's stdout.
The distinction matters: "this log has no annotations" and "this log's annotations are not being
shown" look identical otherwise.

That notice is an inline Bootstrap card - the same shape `plotted_tables.get_corrupt_log_html` uses
- not a toast. Flight Review has no toast anywhere: it reports through a full error page
(`CustomHTTPError`), a Bokeh `Div` in place of the plots, a Bootstrap `alert`/`card` block in the
page body (`error_labels_html`, `hardfault_html`, `corrupt_log_html`), or a hidden `<div>` revealed
by JS on the upload form. Bootstrap 5 ships the toast component in the bundled CSS/JS, but nothing
here uses it, and a message that vanishes on a timer is the wrong shape for a page state that is
still true after it fades.

Note that a *database* failure is invisible by design, and not specific to annotations:
`main.py` wraps the whole `select` in a bare `except` that prints and leaves `db_data` at its
defaults, so a failed read looks exactly like a log with no description, no rating, and no
annotations. Annotations behave like every other column rather than inventing a second policy.

Between those sits the one case that is neither: a `graph` that no longer matches any plot - after
an upstream rename, or because this log didn't record that topic. That annotation is still listed
in the table, just without a link and without shading. Plot names are resolved late, against the
`plots` variable `configured_plots` hands the template, and are never stored as truth.

## Limits

Annotations arrive on an upload, so they are not trusted input.

| Limit | Value | On breach |
|---|---|---|
| File size | 1 MB per file | Upload rejected |
| `name`, `category`, `graph` | 64 characters | Truncated |
| `annotation`, `value` | 200 characters | Truncated |
| `start`, `end` | 0 to 30 days | Upload rejected |
| Categories per log | 50 | Upload rejected |
| Intervals per log | 1000 | Upload rejected |
| Rows drawn on one plot | 6 | Extra rows listed in the table only |

Free text truncates because an over-long note is cosmetic and losing the upload over it is not
proportionate. Counts reject because silently dropping annotations would leave the uploader
believing the log carries data it does not. Counts are checked after deduplication, so
re-uploading a corrected file cannot creep towards the limit.

The time bound is not about display, it is about arithmetic: YAML's `.inf`, `1e400` and integers
too large for a float all reach `_time`, and without it they raise `OverflowError` - a 500 for
something the uploader could have fixed. For the same reason a value that is a list or a mapping is
never passed to `str()`: YAML aliases can make a small file describe an enormous structure, and
`str()` on one of those builds it. Free text is also stripped of lone surrogates, which YAML
accepts but UTF-8 cannot encode - one in a `name` would otherwise pass validation, reach the
database, and then break the whole log page at the point Tornado writes it, well outside anything
`render` can catch.

Duplicates - the same `(source, category, graph)` uploaded twice - are resolved by a linear scan,
last definition wins, keeping the position of the first. Re-uploading a corrected file replaces a
category rather than doubling it.

## How it is drawn

The bar is a `BoxAnnotation` with its **x in data units and its y in screen units**, which is
`plot_flight_modes_background`'s own trick for the VTOL strip: a fixed-height bar spanning a time
range, whatever the y-range does, sitting below the flight-mode background rather than tinting it.
Rows stack upward from the bottom edge, starting above the VTOL strip on the plots that have one -
the strip's own `top` is read off the figure rather than assumed, so upstream is free to change
`vtol_state_height` without the two overlapping. A category's intervals share one row, which is
what lets a single bar have disjoint sections.

The row is labelled `Ground Truth: takeoff_wobble` - source and category - pinned to the left edge
of the frame in screen units, so it holds its place under pan and zoom the way the row it names
does.

An interval with no `end` is an instant. A zero-width box renders as nothing at all, so those
become a dashed `Span` instead, plus a small marker where the line crosses the row.

### What the mouse reveals

At rest the strip shows only geometry - bands, instant lines and row labels. Per-interval text is
drawn but hidden, and arrives two ways when the mouse comes near:

* **A tooltip** on the band or the instant marker, carrying source, category, time and note - the
  same fields as the table row.
* **The `value` text**, revealed for the whole plot on `MouseEnter` and hidden again on
  `MouseLeave`. This is `plot_flight_modes_background`'s own trick for flight mode names
  (`plotting.py:161-183`): a `LabelSet` with `visible = False` and a two-line `CustomJS`.

Tooltips need a `DataRenderer`, and `BoxAnnotation`, `Span` and `Label` are none of them, so the
visible band cannot itself be hovered. Rather than redraw the band as a glyph - which would give up
the screen-unit trick above, and with it the exact row heights and the VTOL clearance - an
*invisible* `quad` is laid over it purely as a hover target, and the instants get a visible marker
because a one-pixel dashed line is hard to point at. Both are scoped into one `HoverTool` per plot,
as `plotting.py:51` scopes the dropout hover; nothing in `plot_app` uses `renderers='auto'`, so
there is no ambient hover to capture them. `tooltips` is given as a list of pairs rather than an
HTML string, so Bokeh inserts the uploaded strings as text and not as markup.

A glyph cannot use screen units, so those targets live on an `extra_y_ranges` entry fixed at
`Range1d(0, 1)` and their pixel offsets are divided by the frame height - which Python does not
know, so it uses `plot.height - 60`, the same allowance `plotting.py:137` makes for its own labels.
The target is a full row *spacing* tall rather than a row height, so it still covers the band if that
estimate is off by a few pixels. Being invisible, an error there costs hover accuracy, never
appearance.

The **row label is not itself a hover target**, for the same `DataRenderer` reason: a data-space
glyph cannot be pinned to the frame edge. Hovering the band it names gives the same text.

Two things Bokeh will not do for a `Label`, both handled in Python before rendering:

* **It does not flip at the frame edge.** A label in the right quarter of the x range is given
  `text_align='right'` so it extends leftwards instead of off the plot.
* **It does not declutter.** Labels sharing a row are packed onto as many lines as they need, up to
  three, using an approximate character width. Without this, two instants a few seconds apart on a
  three-minute flight draw on top of each other.

The table itself is a Bootstrap `card` + `table table-sm`, styled entirely by classes from the
bundled theme, as every other block Flight Review builds in Python is. No stylesheet is added: the
only rule Bootstrap has no utility for is the scroll cap that keeps the section from pushing the
plots down, and that is one inline `style` on one `<div>` - the same way `upload.html` and
`plotted_tables.py` express their one-off rules. Custom CSS worth reusing belongs in
`static/css/main.css`, and this feature has none.

## Not included

* Attaching or editing annotations on a log that is already uploaded. They ride along with the
  upload, because that is when the log id is assigned.
* Serving the annotations back for download.
* Any interpretation of what an annotation means - this feature displays them, it does not judge
  the flight.

## Where the code is

| File | Role |
|---|---|
| `app/plot_app/annotations.py` | All of it, behind two entry points: `from_upload` and `render`. |
| `app/tornado_handlers/upload.py` | Passes the `annotations` parts to `from_upload`, stores the result on the log row. |
| `app/plot_app/main.py` | Calls `render` after `generate_plots`. |
| `app/plot_app/templates/upload.html` | The file input. |
| `app/plot_app/templates/index.html` | Where the table is placed. |
| `app/setup_db.py` | The `Logs.Annotations` column and its upgrade branch. |
