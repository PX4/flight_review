### Flight Review ###

This is a web application for flight log analysis. It allows users to upload
ULog flight logs, and analyze them through the browser.

It uses the [bokeh](http://bokeh.pydata.org) library for plotting and the
[Tornado Web Server](http://www.tornadoweb.org).


#### Installation and Setup ####

- clone the repository
- use python3
- `pip3 install bokeh jinja2 pyulog` (at least version 0.12.3 of bokeh is
  required)
- `sudo apt-get install sqlite3`
- configure web server settings in `plot_app/config.py`. This can be skipped for a local
  installation.
- `./setup_db.py` to initialize the database


#### Usage ####

For local usage, the server can be started directly with a log file name,
without having to upload it first:
```
./serve.py -f <file.ulg>
```

The `plot_app` directory contains a bokeh server application for plotting. It
can be run stand-alone with `bokeh serve --show plot_app` (or with `cd plot_app;
bokeh serve --show main.py`, to start without the html template).

The whole web application is run with the `serve.py` script. Run `./serve.py -h`
for further details.


#### Interactive Usage ####
The plotting can also be used interative using a Jupyter Notebook. It
requires python knowledge, but provides full control over what and how to plot
with immediate feedback.

- `pip3 install jupyter`
- Start the notebook: `jupyter notebook`
- open the `testing_notebook.ipynb` file

### TODO list ###
- plot ground truth if found in log
- Google Maps seems to have some problems (initialization, scaling and zooming
  issues). This is bokeh
- maximum upload size is currently limited to 100MB. This requires a bokeh
  setting.
- add SSL
- Not all bokeh widgets seem to be responsive to size changes
- better downsampling (use JS callback with queue & timeout (like
  InteractiveImage) and better algorithm)
- add location obfuscation option
- user management: login, per-user display templates
- download CSV option?
- ...

#### Contributing ####
Contributions are welcome! Just open a pull request with detailed description
why the changes are needed, or open an issue for bugs, feature requests, etc...

