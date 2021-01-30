# Meta

* *Maintainer:* Herman Øie Kolden
* *Review policy:* Self-approval

# Flight Review

This is a web application for flight log analysis. It allows users to upload
ULog flight logs, and analyze them through the browser.

It uses the [bokeh](http://bokeh.pydata.org) library for plotting and the
[Tornado Web Server](http://www.tornadoweb.org).

## Installation and Setup

### Requirements

- Python3 (3.6+ recommended)
- SQLite3
- [http://fftw.org/](http://fftw.org/)

#### Ubuntu

```bash
sudo apt-get install sqlite3 fftw3 libfftw3-dev
```

**Note:** Under some Ubuntu and Debian environments you might have to
install ATLAS

```bash
sudo apt-get install libatlas3-base
```

#### macOS

macOS already provides SQLite3.
Use [Homebrew](https://brew.sh) to install fftw:

```bash
brew install fftw
```

### Installation

```bash
# After git clone, enter the directory
git clone https://github.com/aviant-tech/flight_review.git
cd flight_review
virtualenv -p python3 venv
source venv/bin/activate
pip install -r requirements.txt
```

### Setup

- By default the app will load `config_default.ini` configuration file
- You can override any setting from `config_default.ini` with a user config file
  `config_user.ini` (untracked)
- Any setting on `config_user.ini` has priority over
  `config_default.ini`
- Run `setup_db.py` to initialize the database.

**Note:** `setup_db.py` can also be used to upgrade the database tables, for
  instance when new entries are added (it automatically detects that).

## Usage

For local usage, the server can be started directly with a log file name,
without having to upload it first:

```bash
./serve.py -f <file.ulg>
```

To start the whole web application:
```bash
./serve.py --show
```

The `plot_app` directory contains a bokeh server application for plotting. It
can be run stand-alone with `bokeh serve --show plot_app` (or with `cd plot_app;
bokeh serve --show main.py`, to start without the html template).

The whole web application is run with the `serve.py` script. Run `./serve.py -h`
for further details.

# Implementation
The web site is structured around a bokeh application in `plot_app`
(`plot_app/configured_plots.py` contains all the configured plots). This
application also handles the statistics page, as it contains bokeh plots as
well. The other pages (upload, browse, ...) are implemented as tornado handlers
in `tornado_handlers/`.

`plot_app/helper.py` additionally contains a list of log topics that the plot
application can subscribe to. A topic must live in this list in order to be
plotted.

Tornado uses a single-threaded event loop. This means all operations should be
non-blocking (see also http://www.tornadoweb.org/en/stable/guide/async.html).
(This is currently not the case for sending emails).

Reading ULog files is expensive and thus should be avoided if not really
necessary. There are two mechanisms helping with that:
- Loaded ULog files are kept in RAM using an LRU cache with configurable size
  (when using the helper method). This works from different requests and
  sessions and from all source contexts.
- There's a LogsGenerated DB table, which contains extracted data from ULog
  for faster access.

## Caching
In addition to in-memory caching there is also some on-disk caching: KML files
are stored on disk. Also the parameters and airframes are cached and downloaded
every 24 hours. It is safe to delete these files (but not the cache directory).

## Notes about python imports
Bokeh uses dynamic code loading and the `plot_app/main.py` gets loaded on each
session (page load) to isolate requests. This also means we cannot use relative
imports. We have to use `sys.path.append` to include modules in `plot_app` from
the root directory (Eg `tornado_handlers.py`). Then to make sure the same module
is only loaded once, we use `import xy` instead of `import plot_app.xy`.
It's useful to look at `print('\n'.join(sys.modules.keys()))` to check this.

