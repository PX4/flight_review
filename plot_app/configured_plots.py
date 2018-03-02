""" This contains the list of all drawn plots on the log plotting page """

from html import escape

from bokeh.layouts import widgetbox
from bokeh.models.widgets import Div, Button, CheckboxButtonGroup
from bokeh.io import curdoc

from helper import *
from config import *
from plotting import *
from plotted_tables import (
    get_logged_messages, get_changed_parameters,
    get_info_table_html, get_heading_html, get_error_labels_html,
    get_hardfault_html, get_time_series_plots
    )

#pylint: disable=cell-var-from-loop, undefined-loop-variable,
#pylint: disable=consider-using-enumerate


def generate_plots(ulog, px4_ulog, db_data, vehicle_data, link_to_3d_page, linkXAxes = False):
    """ create a list of bokeh plots (and widgets) to show """

    plots = []
    data = ulog.data_list


    # initialize flight mode changes
    flight_mode_changes = get_flight_mode_changes(ulog)

    # VTOL state changes
    vtol_states = None
    try:
        cur_dataset = ulog.get_dataset('vehicle_status')
        if np.amax(cur_dataset.data['is_vtol']) == 1:
            vtol_states = cur_dataset.list_value_changes('in_transition_mode')
            # find mode after transitions (states: 1=transition, 2=FW, 3=MC)
            for i in range(len(vtol_states)):
                if vtol_states[i][1] == 0:
                    t = vtol_states[i][0]
                    idx = np.argmax(cur_dataset.data['timestamp'] >= t) + 1
                    vtol_states[i] = (t, 2 + cur_dataset.data['is_rotary_wing'][idx])
            vtol_states.append((ulog.last_timestamp, -1))
    except (KeyError, IndexError) as error:
        vtol_states = None



    # Heading
    curdoc().template_variables['title_html'] = get_heading_html(
        ulog, px4_ulog, db_data, link_to_3d_page)

    # info text on top (logging duration, max speed, ...)
    curdoc().template_variables['info_table_html'] = \
        get_info_table_html(ulog, px4_ulog, db_data, vehicle_data, vtol_states)

    curdoc().template_variables['error_labels_html'] = get_error_labels_html()

    hardfault_html = get_hardfault_html(ulog)
    if hardfault_html is not None:
        curdoc().template_variables['hardfault_html'] = hardfault_html




# FIXME: for now, we use Google maps directly without bokeh, because it's not working reliably
    # GPS map
#    gps_plots = []
#    gps_titles = []
#    plot = plot_map(ulog, plot_config, map_type='google', api_key =
#            get_google_maps_api_key(), setpoints=False)
#    if plot is not None:
#        gps_plots.append(plot)
#        gps_titles.append('GPS Map: Satellite')
#
#    plot = plot_map(ulog, plot_config, map_type='plain', setpoints=True)
#    if plot is not None:
#        gps_plots.append(plot)
#        gps_titles.append('GPS Map: Plain')
#
#    data_plot = DataPlot2D(data, plot_config, 'vehicle_local_position',
#        x_axis_label = '[m]', y_axis_label='[m]', plot_height='large')
#    data_plot.add_graph('y', 'x', colors2[0], 'Estimated')
#    data_plot.change_dataset('vehicle_local_position_setpoint')
#    data_plot.add_graph('y', 'x', colors2[1], 'Setpoint')
#    if data_plot.finalize() is not None:
#        gps_plots.append(data_plot.bokeh_plot)
#        gps_titles.append('Local Position')
#
#    if len(gps_plots) >= 2:
#        tabs = []
#        for i in range(len(gps_plots)):
#            tabs.append(Panel(child=gps_plots[i], title=gps_titles[i]))
#        gps_plot_height=plot_config['plot_height']['large'] + 30
#        plots.append(Tabs(tabs=tabs, width=plot_width, height=gps_plot_height))
#    elif len(gps_plots) == 1:
#        plots.extend(gps_plots)


    if is_running_locally():
        # show the google maps plot via Bokeh, since the one in the html
        # template does not work locally (we disable it further down)
        map_plot = plot_map(ulog, plot_config, map_type='google', api_key=
                            get_google_maps_api_key(), setpoints=False)
        if map_plot is not None:
            plots.append(map_plot)


    # Position plot
    data_plot = DataPlot2D(data, plot_config, 'vehicle_local_position',
                           x_axis_label='[m]', y_axis_label='[m]', plot_height='large')
    data_plot.add_graph('y', 'x', colors2[0], 'Estimated',
                        check_if_all_zero=True)
    if not data_plot.had_error: # vehicle_local_position is required
        data_plot.change_dataset('vehicle_local_position_setpoint')
        data_plot.add_graph('y', 'x', colors2[1], 'Setpoint')
        # groundtruth (SITL only)
        data_plot.change_dataset('vehicle_local_position_groundtruth')
        data_plot.add_graph('y', 'x', color_gray, 'Groundtruth')
        # GPS + position setpoints
        plot_map(ulog, plot_config, map_type='plain', setpoints=True,
                 bokeh_plot=data_plot.bokeh_plot)
        if data_plot.finalize() is not None:
            plots.append(data_plot.bokeh_plot)
            if not is_running_locally(): # do not enable Google Map if running locally
                curdoc().template_variables['has_position_data'] = True

    numOfItemsBeforePlots = len(plots)
    plots += get_time_series_plots(flight_mode_changes, ulog, px4_ulog, plot_width, db_data, vehicle_data,
                         vtol_states, linkXAxes)

    # exchange all DataPlot's with the bokeh_plot and handle parameter changes

    param_changes_button = Button(label="Hide Parameter Changes", width=170)
    param_change_labels = []
    # FIXME: this should be a CustomJS callback, not on the server. However this
    # did not work for me.
    def param_changes_button_clicked():
        """ callback to show/hide parameter changes """
        for label in param_change_labels:
            if label.visible:
                param_changes_button.label = 'Show Parameter Changes'
                label.visible = False
                label.text_alpha = 0 # label.visible does not work, so we use this instead
            else:
                param_changes_button.label = 'Hide Parameter Changes'
                label.visible = True
                label.text_alpha = 1
    param_changes_button.on_click(param_changes_button_clicked)


    jinja_plot_data = []
    for i in range(len(plots)):
        if plots[i] is None:
            plots[i] = widgetbox(param_changes_button, width=int(plot_width * 0.99))
        if isinstance(plots[i], DataPlot):
            if plots[i].param_change_label is not None:
                param_change_labels.append(plots[i].param_change_label)

            plot_title = plots[i].title
            plots[i] = plots[i].bokeh_plot

            fragment = 'Nav-'+plot_title.replace(' ', '-') \
                .replace('&', '_').replace('(', '').replace(')', '')
            jinja_plot_data.append({
                'model_id': plots[i].ref['id'],
                'fragment': fragment,
                'title': plot_title
                })

    link_axes_button = CheckboxButtonGroup(labels=["Link X Axes"])
    def link_axes_cb(attr, old, new):
        if len(new) > 0: #box is checked
            new_plots = [i.bokeh_plot for i in get_time_series_plots(flight_mode_changes, ulog, px4_ulog, plot_width, db_data, vehicle_data,
                         vtol_states, linkXAxes=True)]
        else:
            new_plots = [i.bokeh_plot for i in get_time_series_plots(flight_mode_changes, ulog, px4_ulog, plot_width, db_data, vehicle_data,
                         vtol_states, linkXAxes=False)]
        curdoc().roots[0].children[numOfItemsBeforePlots:numOfItemsBeforePlots+len(new_plots)] = new_plots
    link_axes_button.on_change('active',link_axes_cb)
    plots.append(link_axes_button)

    # changed parameters
    plots.append(get_changed_parameters(ulog.initial_parameters, plot_width))



    # information about which messages are contained in the log
# TODO: need to load all topics for this (-> log loading will take longer)
#       but if we load all topics and the log contains some (external) topics
#       with buggy timestamps, it will affect the plotting.
#    data_list_sorted = sorted(ulog.data_list, key=lambda d: d.name + str(d.multi_id))
#    table_text = []
#    for d in data_list_sorted:
#        message_size = sum([ULog.get_field_size(f.type_str) for f in d.field_data])
#        num_data_points = len(d.data['timestamp'])
#        table_text.append((d.name, str(d.multi_id), str(message_size), str(num_data_points),
#           str(message_size * num_data_points)))
#    topics_info = '<table><tr><th>Name</th><th>Topic instance</th><th>Message Size</th>' \
#            '<th>Number of data points</th><th>Total bytes</th></tr>' + ''.join(
#            ['<tr><td>'+'</td><td>'.join(list(x))+'</td></tr>' for x in table_text]) + '</table>'
#    topics_div = Div(text=topics_info, width=int(plot_width*0.9))
#    plots.append(widgetbox(topics_div, width=int(plot_width*0.9)))


    # log messages
    plots.append(get_logged_messages(ulog.logged_messages, plot_width))


    # perf & top output
    top_data = ''
    perf_data = ''
    for state in ['pre', 'post']:
        if 'perf_top_'+state+'flight' in ulog.msg_info_multiple_dict:
            current_top_data = ulog.msg_info_multiple_dict['perf_top_'+state+'flight'][0]
            flight_data = escape('\n'.join(current_top_data))
            top_data += '<p>'+state.capitalize()+' Flight:<br/><pre>'+flight_data+'</pre></p>'
        if 'perf_counter_'+state+'flight' in ulog.msg_info_multiple_dict:
            current_perf_data = ulog.msg_info_multiple_dict['perf_counter_'+state+'flight'][0]
            flight_data = escape('\n'.join(current_perf_data))
            perf_data += '<p>'+state.capitalize()+' Flight:<br/><pre>'+flight_data+'</pre></p>'

    additional_data_html = ''
    if len(top_data) > 0:
        additional_data_html += '<h5>Processes</h5>'+top_data
    if len(perf_data) > 0:
        additional_data_html += '<h5>Performance Counters</h5>'+perf_data
    if len(additional_data_html) > 0:
        # hide by default & use a button to expand
        additional_data_html = '''
<button class="btn btn-secondary" data-toggle="collapse" style="min-width:0;"
 data-target="#show-additional-data">Show additional Data</button>
<div id="show-additional-data" class="collapse">
{:}
</div>
'''.format(additional_data_html)
        additional_data_div = Div(text=additional_data_html, width=int(plot_width*0.9))
        plots.append(widgetbox(additional_data_div, width=int(plot_width*0.9)))


    curdoc().template_variables['plots'] = jinja_plot_data

    return plots
