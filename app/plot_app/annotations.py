""" validation and rendering of user-provided log annotations (see docs/annotations.md) """

import json
import re
from html import escape

import yaml
from bokeh import events
from bokeh.models import (BoxAnnotation, ColumnDataSource, CustomJS, HoverTool, Label, LabelSet,
                          Range1d, Span)

from config import colors8, plot_width

_STORED_VERSION = 1 # of the JSON in Logs.Annotations
_YAML_VERSION = 1 # highest 'version:' an uploaded file may declare

# caps on upload-derived data: strings truncate, counts reject (see docs/annotations.md)
_MAX_FILE_BYTES = 1024*1024
_MAX_NAME_CHARS = 64 # name, category, graph
_MAX_TEXT_CHARS = 200 # annotation, value
_MAX_CATEGORIES = 50
_MAX_INTERVALS = 1000
_MAX_TIME_SECONDS = 30*24*3600
_MAX_ROWS_PER_PLOT = 6 # the strip must not grow into the plot it annotates

_PALETTE = [color for color in colors8 if color != '#000000'] # a filled band must read as a color
_COLOR_RE = re.compile(r'^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{3,20})$')
_TIME_RE = re.compile(r'^(?:(?:(\d+):)?(\d+):)?(\d+(?:\.\d+)?)$')

# the strip is drawn in screen units, as plotting.py draws the VTOL strip
_ROW_HEIGHT_PX = 10 # of the coloured band
_ROW_SPACING_PX = 12 # from one row's bottom to the next
_PLOT_CHROME_PX = 60 # by how much a figure's height exceeds its frame, as plotting.py assumes
_VALUE_LINE_HEIGHT_PX = 11
_VALUE_CHAR_WIDTH_PX = 5.3 # of an 8pt character, near enough to keep value text off its neighbour
_MAX_VALUE_LINES = 3 # value text stacks upward, and must not climb into the plot
_RIGHT_ALIGN_AT = 0.75 # of the x axis: past here, value text must extend leftwards to fit

_LABEL_STYLE = {'text_font_size': '8pt', 'text_baseline': 'bottom',
                'background_fill_color': '#ffffff', 'background_fill_alpha': 0.7}
# a hover target must be a glyph, and a glyph needs data units: this range makes the frame 0 to 1
_HOVER_Y_RANGE = 'annotations'
# pairs and not html, so that upload-derived text is inserted by bokeh as text and not as markup
_TOOLTIPS = [('', '@row'), ('Time', '@when'), ('Note', '@note')]


def _text(value, limit):
    """ a yaml scalar as a stripped, utf-8 safe string of at most limit characters, or '' for
        anything else (str() of an aliased collection can be enormous) """
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ''
    return str(value).strip().encode('utf-8', 'replace').decode('utf-8')[:limit]


def _time(value):
    """ an annotation time in us on the boot clock, the same value the x axis labels """
    # no sign, exponent, inf or nan matches, so the bounded sum below cannot overflow
    text = _text(value, _MAX_NAME_CHARS)
    match = _TIME_RE.match(text)
    if not match:
        raise ValueError('invalid time: {} (expected [h:]mm:ss)'.format(
            text or type(value).__name__))
    seconds = 3600*int(match[1] or 0)+60*int(match[2] or 0)+float(match[3])
    if seconds > _MAX_TIME_SECONDS:
        raise ValueError('time is beyond {} days: {}'.format(_MAX_TIME_SECONDS//86400, text))
    return int(round(seconds*1e6))


def _time_str(timestamp):
    """ inverse of _time, formatted as the x axis labels it """
    h, rest = divmod(int(timestamp//1000000), 3600)
    m, s = divmod(rest, 60)
    return '{:d}:{:02d}:{:02d}'.format(h, m, s) if h > 0 else '{:d}:{:02d}'.format(m, s)


def _when(interval):
    """ an interval's time, as both the table and the tooltip show it """
    if interval['end'] is None:
        return _time_str(interval['start'])
    return _time_str(interval['start'])+' to '+_time_str(interval['end'])


def _note(interval):
    """ an interval's free text, the annotation followed by the value """
    return ' '.join(text for text in (interval['text'], interval['value']) if text)


def _color(value, fallback):
    """ a color that is safe to put in a style attribute, or fallback if unset """
    color = _text(value, _MAX_NAME_CHARS)
    if not color:
        return fallback
    if not _COLOR_RE.match(color):
        raise ValueError('invalid color: {}'.format(color))
    return color


def _interval(interval, where):
    if not isinstance(interval, dict) or 'start' not in interval:
        raise ValueError('{}: each interval needs a "start"'.format(where))
    start = _time(interval['start'])
    end = _time(interval['end']) if interval.get('end') is not None else None
    if end is not None and end < start:
        raise ValueError('{}: interval ends before it starts'.format(where))
    return {'start': start, 'end': end,
            'text': _text(interval.get('annotation'), _MAX_TEXT_CHARS),
            'value': _text(interval.get('value'), _MAX_TEXT_CHARS)}


def _category(entry, source_name, source_color, index):
    if not isinstance(entry, dict):
        raise ValueError('{}: each annotation must be a mapping'.format(source_name))
    category = _text(entry.get('category'), _MAX_NAME_CHARS)
    if not category:
        raise ValueError('{}: an annotation is missing "category"'.format(source_name))
    where = '{}/{}'.format(source_name, category)
    graph = _text(entry.get('graph'), _MAX_NAME_CHARS)
    if not graph:
        raise ValueError('{}: missing "graph"'.format(where))
    intervals = entry.get('intervals')
    if not isinstance(intervals, list) or not intervals:
        raise ValueError('{}: "intervals" must be a non-empty list'.format(where))
    return {'category': category, 'graph': graph,
            'color': _color(entry.get('color'), source_color or _PALETTE[index%len(_PALETTE)]),
            'intervals': [_interval(interval, where) for interval in intervals]}


def _validate(document):
    """ one parsed file, normalized. The ValueError message is shown to the uploader """
    if isinstance(document, dict): # the versioned form; a bare list of sources is version 1
        version = document.get('version', _YAML_VERSION)
        if isinstance(version, bool) or not isinstance(version, int) \
                or not 1 <= version <= _YAML_VERSION:
            raise ValueError('unsupported annotations version: {} (this server reads 1 to {})'
                             .format(_text(version, _MAX_NAME_CHARS), _YAML_VERSION))
        document = document.get('sources')
    if not isinstance(document, list):
        raise ValueError('expected a list of annotation sources at the top level')
    sources = []
    for source in document:
        if not isinstance(source, dict):
            raise ValueError('each annotation source must be a mapping with a "name"')
        name = _text(source.get('name'), _MAX_NAME_CHARS)
        if not name:
            raise ValueError('an annotation source is missing "name"')
        entries = source.get('annotations')
        if not isinstance(entries, list) or not entries:
            raise ValueError('{}: "annotations" must be a non-empty list'.format(name))
        color = _color(source.get('color'), None)
        sources.append({'name': name,
                        'annotations': [_category(entry, name, color, i)
                                        for i, entry in enumerate(entries)]})
    return sources


def _merge(documents):
    """ validated files as one list, deduplicated on (source, category, graph): last wins """
    sources = {}
    for document in documents:
        for source in document:
            categories = sources.setdefault(source['name'], {})
            for category in source['annotations']:
                categories[(category['category'], category['graph'])] = category
    merged = [{'name': name, 'annotations': list(categories.values())}
              for name, categories in sources.items()]

    # counted after deduplication, so re-uploading a corrected file does not creep to the limit
    count = sum(len(source['annotations']) for source in merged)
    if count > _MAX_CATEGORIES:
        raise ValueError('too many categories: {} (limit {})'.format(count, _MAX_CATEGORIES))
    count = sum(len(category['intervals']) for _, category in _walk(merged))
    if count > _MAX_INTERVALS:
        raise ValueError('too many intervals: {} (limit {})'.format(count, _MAX_INTERVALS))
    return merged


def _walk(sources):
    """ iterate over (source name, category) """
    for source in sources:
        for category in source['annotations']:
            yield source['name'], category


def _plot_index(jinja_plots):
    """ {lowercase title or fragment: plot}, the two ways an annotation's "graph" can name one
        of the plots this log actually rendered """
    index = {}
    for plot in jinja_plots or []:
        if isinstance(plot, dict) and plot.get('title') and plot.get('fragment'):
            index[plot['title'].lower()] = index[plot['fragment'].lower()] = plot
    return index


def _label(text, color, bottom):
    """ a row's label, pinned to the left edge of the frame """
    return Label(x=4, x_units='screen', y=bottom+1, y_units='screen', text=text,
                 text_color=color, padding=1, **_LABEL_STYLE)


def _draw_all(plots, rows):
    """ group the rows by the plot they name, and draw each plot's strip """
    figures = {figure.ref['id']: figure for figure in plots if hasattr(figure, 'ref')}
    by_figure = {}
    for name, category, plot in rows:
        if plot is not None and plot['model_id'] in figures:
            by_figure.setdefault(plot['model_id'], []).append((name, category))
    for model_id, figure_rows in by_figure.items():
        _draw(figures[model_id], figure_rows)


def _source(rows):
    """ rows of values as the columns a ColumnDataSource is given """
    return ColumnDataSource({name: [row[name] for row in rows] for name in rows[0]})


def _strip_bottom(figure):
    """ where the strip starts: clear of plotting.py's VTOL strip, the only other screen box """
    strips = [box.top for box in figure.center if isinstance(box, BoxAnnotation)
              and box.top_units == 'screen' and box.top is not None]
    return max(strips)+_ROW_SPACING_PX-_ROW_HEIGHT_PX if strips else 0


def _value_rows(figure, values, bottom):
    """ a row's value text, on as many lines as it takes not to overlap itself, right aligned
        near the right edge, where bokeh would otherwise run it off the plot """
    start, end = figure.x_range.start, figure.x_range.end
    # a frequency axis reads as nan, leaving no extent to lay text out along
    extent = end-start if None not in (start, end) and end > start else 0
    line_ends = []
    rows = []
    for x, text, color in sorted(values):
        align = 'right' if extent and x > start+_RIGHT_ALIGN_AT*extent else 'left'
        width = len(text)*_VALUE_CHAR_WIDTH_PX*extent/(figure.width or plot_width)
        left = x-width if align == 'right' else x
        line = next((i for i, edge in enumerate(line_ends) if edge <= left), len(line_ends))
        line = min(line, _MAX_VALUE_LINES-1)
        line_ends[line:line+1] = [left+width]
        rows.append({'x': x, 'y': bottom+1+line*_VALUE_LINE_HEIGHT_PX,
                     'text': text, 'color': color, 'align': align})
    return rows


def _draw(figure, rows):
    """ draw one plot's rows: a labelled strip per category, a dashed line per instant """
    bottom = _strip_bottom(figure)
    frame = max((figure.height or 0)-_PLOT_CHROME_PX, _PLOT_CHROME_PX)
    bands, marks, texts = [], [], []
    for name, category in rows[:_MAX_ROWS_PER_PLOT]:
        color = category['color']
        row = '{}: {}'.format(name, category['category'])
        values = []
        for interval in category['intervals']:
            where = {'row': row, 'when': _when(interval), 'note': _note(interval)}
            if interval['end'] is None: # an instant: a zero-width box draws nothing
                figure.add_layout(Span(location=interval['start'], dimension='height',
                                       line_color=color, line_dash='dashed', line_alpha=0.8))
                marks.append({'x': interval['start'], 'y': (bottom+_ROW_HEIGHT_PX/2)/frame,
                              'color': color, **where})
                if interval['value']:
                    values.append((interval['start'], interval['value'], color))
            else:
                figure.add_layout(BoxAnnotation(
                    left=interval['start'], right=interval['end'], bottom=bottom,
                    top=bottom+_ROW_HEIGHT_PX, bottom_units='screen', top_units='screen',
                    fill_color=color, fill_alpha=0.55, line_color=None,
                    movable='none', resizable='none'))
                bands.append({'left': interval['start'], 'right': interval['end'],
                              'bottom': bottom/frame, 'top': (bottom+_ROW_SPACING_PX)/frame,
                              **where})
        figure.add_layout(_label(row, color, bottom))
        texts += _value_rows(figure, values, bottom)
        bottom += _ROW_SPACING_PX
    _hover(figure, bands, marks)
    if texts:
        _reveal(figure, texts)


def _hover(figure, bands, marks):
    """ hover targets: a HoverTool takes neither a BoxAnnotation nor a Span, so a band gets an
        invisible glyph of its own, and an instant a marker, easier to point at than a line """
    renderers = []
    if bands:
        renderers.append(figure.quad(
            left='left', right='right', bottom='bottom', top='top', y_range_name=_HOVER_Y_RANGE,
            source=_source(bands), fill_alpha=0, line_alpha=0))
    if marks:
        renderers.append(figure.scatter(
            x='x', y='y', y_range_name=_HOVER_Y_RANGE, source=_source(marks),
            marker='inverted_triangle', size=7, fill_color='color', line_color=None))
    if renderers:
        figure.extra_y_ranges = dict(figure.extra_y_ranges, **{_HOVER_Y_RANGE: Range1d(0, 1)})
        figure.add_tools(HoverTool(renderers=renderers, tooltips=_TOOLTIPS))


def _reveal(figure, texts):
    """ value text, hidden until the mouse enters the plot, as plotting.py hides flight modes """
    labels = LabelSet(x='x', y='y', y_units='screen', text='text', text_color='color',
                      text_align='align', source=_source(texts), visible=False, **_LABEL_STYLE)
    figure.add_layout(labels)
    callback = CustomJS(args={'labels': labels},
                        code='labels.visible = cb_obj.event_name == "mouseenter";')
    figure.js_on_event(events.MouseEnter, callback)
    figure.js_on_event(events.MouseLeave, callback)


def _section(body):
    """ a card above the plots, as plotted_tables builds the corrupt-log and hardfault warnings """
    return ('<div class="card mb-3"><div class="card-header">Annotations</div>'
            '{}</div>'.format(body))


def _table_html(rows):
    """ the annotations section shown above the plots, or '' if there is nothing to show """
    html = []
    for name, category, plot in rows:
        for interval in category['intervals']:
            when = escape(_when(interval))
            if plot is not None:
                # main.js adds the Nav-* anchors once bokeh has rendered, navigate() waits
                when = '<a href="javascript:navigate(\'{}\');">{}</a>'.format(
                    escape(plot['fragment'], quote=True), when)
            html.append('<tr><td>{}</td><td>{}</td><td>{}</td><td class="text-muted">{}</td></tr>'
                        .format(escape(name), escape(category['category']), when,
                                escape(_note(interval))))
    if not html:
        return ''
    # the table scrolls rather than pushing the plots down; bootstrap has no max-height utility
    return _section('<div class="card-body p-0" style="max-height: 200px; overflow: auto;">'
                    '<table class="table table-sm mb-0"><thead><tr><th>Annotation</th>'
                    '<th>Category</th><th>Time</th><th>Note</th></tr></thead><tbody>{}</tbody>'
                    '</table></div>'.format(''.join(html)))


def from_upload(parts):
    """ the uploaded annotation files as JSON to store, or '' if there are none, raising
        ValueError with a message for the uploader if one does not validate """
    documents = []
    try:
        for part in parts:
            if part.get_size() > _MAX_FILE_BYTES:
                raise ValueError('file is too large')
            if part.get_size() > 0: # an empty file input still posts a part
                documents.append(_validate(yaml.safe_load(part.get_payload().decode('utf-8'))))
        if not documents:
            return ''
        return json.dumps({'v': _STORED_VERSION, 'sources': _merge(documents)})
    except ValueError:
        raise # already phrased for the uploader
    except RecursionError as error: # yaml parses nested flow collections recursively
        raise ValueError('file is too deeply nested') from error
    except Exception as error:
        raise ValueError(_text(error, _MAX_TEXT_CHARS) or type(error).__name__) from error


def render(stored, plots, jinja_plots):
    """ draw a log's annotations onto plots (in place) and return the table html, or a notice
        if the stored value cannot be used (never raises: the plots matter more) """
    if not stored:
        return ''
    try:
        document = json.loads(stored)
        if document['v'] != _STORED_VERSION:
            raise ValueError('stored version {} is not {}'.format(document['v'], _STORED_VERSION))
        index = _plot_index(jinja_plots)
        rows = [(name, category, index.get(category['graph'].lower()))
                for name, category in _walk(document['sources'])]
        html = _table_html(rows) # before drawing, so a bad row leaves the plots untouched
        _draw_all(plots, rows)
        return html
    except Exception as error:
        print('annotations: not rendering annotations:', error)
        return _section('<div class="card-body">This log has annotations, but they could not be '
                        'shown. See the server log for details.</div>')
