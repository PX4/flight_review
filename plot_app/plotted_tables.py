""" methods to generate various tables used in configured_plots.py """

from html import escape
from math import sqrt
import datetime

import numpy as np

from bokeh.layouts import column
from bokeh.models import ColumnDataSource
from bokeh.models.widgets import DataTable, TableColumn, Div

from helper import (
    get_default_parameters, get_airframe_name,
    get_total_flight_time, error_labels_table
    )

#pylint: disable=consider-using-enumerate,too-many-statements


def _get_vtol_means_per_mode(vtol_states, timestamps, data):
    """
    get the mean values separated by MC and FW mode for some
    data vector
    :return: tuple of (mean mc, mean fw)
    """
    vtol_state_index = 0
    current_vtol_state = -1
    sum_mc = 0
    counter_mc = 0
    sum_fw = 0
    counter_fw = 0
    for i in range(len(timestamps)):
        if timestamps[i] > vtol_states[vtol_state_index][0]:
            current_vtol_state = vtol_states[vtol_state_index][1]
            vtol_state_index += 1
        if current_vtol_state == 2: # FW
            sum_fw += data[i]
            counter_fw += 1
        elif current_vtol_state == 3: # MC
            sum_mc += data[i]
            counter_mc += 1
    mean_mc = None
    if counter_mc > 0: mean_mc = sum_mc / counter_mc
    mean_fw = None
    if counter_fw > 0: mean_fw = sum_fw / counter_fw
    return (mean_mc, mean_fw)


def get_heading_html(ulog, px4_ulog, db_data, link_to_3d_page,
                     additional_links=None, title_suffix=''):
    """
    Get the html (as string) for the heading information (plots title)
    :param additional_links: list of (label, link) tuples
    """
    sys_name = ''
    if 'sys_name' in ulog.msg_info_dict:
        sys_name = escape(ulog.msg_info_dict['sys_name']) + ' '

    if link_to_3d_page is not None and \
        any(elem.name == 'vehicle_global_position' for elem in ulog.data_list):
        link_to_3d = ("<a class='btn btn-outline-primary' href='"+
                      link_to_3d_page+"'>Open 3D View</a>")
    else:
        link_to_3d = ''

    added_links = ''
    if additional_links is not None:
        for label, link in additional_links:
            added_links += ("<a class='btn btn-outline-primary' href='"+
                            link+"'>"+label+"</a>")

    if title_suffix != '': title_suffix = ' - ' + title_suffix

    title_html = ("<table width='100%'><tr><td><h3>"+sys_name + px4_ulog.get_mav_type()+
                  title_suffix+"</h3></td><td align='right'>" + link_to_3d +
                  added_links+"</td></tr></table>")
    if db_data.description != '':
        title_html += "<h5>"+db_data.description+"</h5>"
    return title_html

def get_info_table_html(ulog, px4_ulog, db_data, vehicle_data, vtol_states):
    """
    Get the html (as string) for a table with additional text info,
    such as logging duration, max speed etc.
    """

    ### Setup the text for the left table with various information ###
    table_text_left = []

    # airframe
    airframe_name_tuple = get_airframe_name(ulog, True)
    if airframe_name_tuple is not None:
        airframe_name, airframe_id = airframe_name_tuple
        if len(airframe_name) == 0:
            table_text_left.append(('Airframe', airframe_id))
        else:
            table_text_left.append(('Airframe', airframe_name+' <small>('+airframe_id+')</small>'))


    # HW & SW
    sys_hardware = ''
    if 'ver_hw' in ulog.msg_info_dict:
        sys_hardware = escape(ulog.msg_info_dict['ver_hw'])
        if 'ver_hw_subtype' in ulog.msg_info_dict:
            sys_hardware += ' (' + escape(ulog.msg_info_dict['ver_hw_subtype']) + ')'
        table_text_left.append(('Hardware', sys_hardware))

    release_str = ulog.get_version_info_str()
    if release_str is None:
        release_str = ''
        release_str_suffix = ''
    else:
        release_str += ' <small>('
        release_str_suffix = ')</small>'
    branch_info = ''
    if 'ver_sw_branch' in ulog.msg_info_dict:
        branch_info = '<br> branch: '+ulog.msg_info_dict['ver_sw_branch']
    if 'ver_sw' in ulog.msg_info_dict:
        ver_sw = escape(ulog.msg_info_dict['ver_sw'])
        ver_sw_link = 'https://github.com/PX4/Firmware/commit/'+ver_sw
        table_text_left.append(('Software Version', release_str +
                                '<a href="'+ver_sw_link+'" target="_blank">'+ver_sw[:8]+'</a>'+
                                release_str_suffix+branch_info))

    if 'sys_os_name' in ulog.msg_info_dict and 'sys_os_ver_release' in ulog.msg_info_dict:
        os_name = escape(ulog.msg_info_dict['sys_os_name'])
        os_ver = ulog.get_version_info_str('sys_os_ver_release')
        if os_ver is not None:
            table_text_left.append(('OS Version', os_name + ', ' + os_ver))

    table_text_left.append(('Estimator', px4_ulog.get_estimator()))

    table_text_left.append(('', '')) # spacing

    # logging start time & date
    try:
        # get the first non-zero timestamp
        gps_data = ulog.get_dataset('vehicle_gps_position')
        indices = np.nonzero(gps_data.data['time_utc_usec'])
        if len(indices[0]) > 0:
            # we use the timestamp from the log and then convert it with JS to
            # display with local timezone.
            # In addition we add a tooltip to show the timezone from the log
            logging_start_time = int(gps_data.data['time_utc_usec'][indices[0][0]] / 1000000)

            utc_offset_min = ulog.initial_parameters.get('SDLOG_UTC_OFFSET', 0)
            utctimestamp = datetime.datetime.utcfromtimestamp(
                logging_start_time+utc_offset_min*60).replace(tzinfo=datetime.timezone.utc)

            tooltip = '''This is your local timezone.
<br />
Log timezone: {}
<br />
SDLOG_UTC_OFFSET: {}'''.format(utctimestamp.strftime('%d-%m-%Y %H:%M'), utc_offset_min)
            tooltip = 'data-toggle="tooltip" data-delay=\'{"show":0, "hide":100}\' '+ \
                'title="'+tooltip+'" '
            table_text_left.append(
                ('Logging Start '+
                 '<i '+tooltip+' class="fa fa-question" aria-hidden="true" '+
                 'style="font-size: larger; color:#666"></i>',
                 '<span style="display:none" id="logging-start-element">'+
                 str(logging_start_time)+'</span>'))
    except:
        # Ignore. Eg. if topic not found
        pass


    # logging duration
    m, s = divmod(int((ulog.last_timestamp - ulog.start_timestamp)/1e6), 60)
    h, m = divmod(m, 60)
    table_text_left.append(('Logging Duration', '{:d}:{:02d}:{:02d}'.format(h, m, s)))

    # dropouts
    dropout_durations = [dropout.duration for dropout in ulog.dropouts]
    if len(dropout_durations) > 0:
        total_duration = sum(dropout_durations) / 1000
        if total_duration > 5:
            total_duration_str = '{:.0f}'.format(total_duration)
        else:
            total_duration_str = '{:.2f}'.format(total_duration)
        table_text_left.append(('Dropouts', '{:} ({:} s)'.format(
            len(dropout_durations), total_duration_str)))

    # total vehicle flight time
    flight_time_s = get_total_flight_time(ulog)
    if flight_time_s is not None:
        m, s = divmod(int(flight_time_s), 60)
        h, m = divmod(m, 60)
        days, h = divmod(h, 24)
        flight_time_str = ''
        if days > 0: flight_time_str += '{:d} days '.format(days)
        if h > 0: flight_time_str += '{:d} hours '.format(h)
        if m > 0: flight_time_str += '{:d} minutes '.format(m)
        flight_time_str += '{:d} seconds '.format(s)
        table_text_left.append(('Vehicle Life<br/>Flight Time', flight_time_str))

    table_text_left.append(('', '')) # spacing

    # vehicle UUID (and name if provided). SITL does not have a (valid) UUID
    if 'sys_uuid' in ulog.msg_info_dict and sys_hardware != 'SITL' and \
            sys_hardware != 'PX4_SITL':
        sys_uuid = escape(ulog.msg_info_dict['sys_uuid'])
        if vehicle_data is not None and vehicle_data.name != '':
            sys_uuid = sys_uuid + ' (' + vehicle_data.name + ')'
        if len(sys_uuid) > 0:
            table_text_left.append(('Vehicle UUID', sys_uuid))


    table_text_left.append(('', '')) # spacing

    # Wind speed, rating, feedback
    if db_data.wind_speed >= 0:
        table_text_left.append(('Wind Speed', db_data.wind_speed_str()))
    if len(db_data.rating) > 0:
        table_text_left.append(('Flight Rating', db_data.rating_str()))
    if len(db_data.feedback) > 0:
        table_text_left.append(('Feedback', db_data.feedback.replace('\n', '<br/>')))
    if len(db_data.video_url) > 0:
        table_text_left.append(('Video', '<a href="'+db_data.video_url+
                                '" target="_blank">'+db_data.video_url+'</a>'))


    ### Setup the text for the right table: estimated numbers (e.g. max speed) ###
    table_text_right = []
    try:

        local_pos = ulog.get_dataset('vehicle_local_position')
        pos_x = local_pos.data['x']
        pos_y = local_pos.data['y']
        pos_z = local_pos.data['z']
        pos_xyz_valid = np.multiply(local_pos.data['xy_valid'], local_pos.data['z_valid'])
        local_vel_valid_indices = np.argwhere(np.multiply(local_pos.data['v_xy_valid'],
                                                          local_pos.data['v_z_valid']) > 0)
        vel_x = local_pos.data['vx'][local_vel_valid_indices]
        vel_y = local_pos.data['vy'][local_vel_valid_indices]
        vel_z = local_pos.data['vz'][local_vel_valid_indices]

        # total distance (take only valid indexes)
        total_dist_m = 0
        last_index = -2
        for valid_index in np.argwhere(pos_xyz_valid > 0):
            index = valid_index[0]
            if index == last_index + 1:
                dx = pos_x[index] - pos_x[last_index]
                dy = pos_y[index] - pos_y[last_index]
                dz = pos_z[index] - pos_z[last_index]
                total_dist_m += sqrt(dx*dx + dy*dy + dz*dz)
            last_index = index
        if total_dist_m < 1:
            pass # ignore
        elif total_dist_m > 1000:
            table_text_right.append(('Distance', "{:.2f} km".format(total_dist_m/1000)))
        else:
            table_text_right.append(('Distance', "{:.1f} m".format(total_dist_m)))

        if len(pos_z) > 0:
            max_alt_diff = np.amax(pos_z) - np.amin(pos_z)
            table_text_right.append(('Max Altitude Difference', "{:.0f} m".format(max_alt_diff)))

        table_text_right.append(('', '')) # spacing

        # Speed
        if len(vel_x) > 0:
            max_h_speed = np.amax(np.sqrt(np.square(vel_x) + np.square(vel_y)))
            speed_vector = np.sqrt(np.square(vel_x) + np.square(vel_y) + np.square(vel_z))
            max_speed = np.amax(speed_vector)
            if vtol_states is None:
                mean_speed = np.mean(speed_vector)
                table_text_right.append(('Average Speed', "{:.1f} km/h".format(mean_speed*3.6)))
            else:
                local_pos_timestamp = local_pos.data['timestamp'][local_vel_valid_indices]
                speed_vector = speed_vector.reshape((len(speed_vector),))
                mean_speed_mc, mean_speed_fw = _get_vtol_means_per_mode(
                    vtol_states, local_pos_timestamp, speed_vector)
                if mean_speed_mc is not None:
                    table_text_right.append(
                        ('Average Speed MC', "{:.1f} km/h".format(mean_speed_mc*3.6)))
                if mean_speed_fw is not None:
                    table_text_right.append(
                        ('Average Speed FW', "{:.1f} km/h".format(mean_speed_fw*3.6)))
            table_text_right.append(('Max Speed', "{:.1f} km/h".format(max_speed*3.6)))
            table_text_right.append(('Max Speed Horizontal', "{:.1f} km/h".format(max_h_speed*3.6)))
            table_text_right.append(('Max Speed Up', "{:.1f} km/h".format(np.amax(-vel_z)*3.6)))
            table_text_right.append(('Max Speed Down', "{:.1f} km/h".format(-np.amin(-vel_z)*3.6)))

            table_text_right.append(('', '')) # spacing

        vehicle_attitude = ulog.get_dataset('vehicle_attitude')
        roll = vehicle_attitude.data['roll']
        pitch = vehicle_attitude.data['pitch']
        if len(roll) > 0:
            # tilt = angle between [0,0,1] and [0,0,1] rotated by roll and pitch
            tilt_angle = np.arccos(np.multiply(np.cos(pitch), np.cos(roll)))*180/np.pi
            table_text_right.append(('Max Tilt Angle', "{:.1f} deg".format(np.amax(tilt_angle))))

        rollspeed = vehicle_attitude.data['rollspeed']
        pitchspeed = vehicle_attitude.data['pitchspeed']
        yawspeed = vehicle_attitude.data['yawspeed']
        if len(rollspeed) > 0:
            max_rot_speed = np.amax(np.sqrt(np.square(rollspeed) +
                                            np.square(pitchspeed) +
                                            np.square(yawspeed)))
            table_text_right.append(('Max Rotation Speed', "{:.1f} deg/s".format(
                max_rot_speed*180/np.pi)))

        table_text_right.append(('', '')) # spacing

        battery_status = ulog.get_dataset('battery_status')
        battery_current = battery_status.data['current_a']
        if len(battery_current) > 0:
            max_current = np.amax(battery_current)
            if max_current > 0.1:
                if vtol_states is None:
                    mean_current = np.mean(battery_current)
                    table_text_right.append(('Average Current', "{:.1f} A".format(mean_current)))
                else:
                    mean_current_mc, mean_current_fw = _get_vtol_means_per_mode(
                        vtol_states, battery_status.data['timestamp'], battery_current)
                    if mean_current_mc is not None:
                        table_text_right.append(
                            ('Average Current MC', "{:.1f} A".format(mean_current_mc)))
                    if mean_current_fw is not None:
                        table_text_right.append(
                            ('Average Current FW', "{:.1f} A".format(mean_current_fw)))

                table_text_right.append(('Max Current', "{:.1f} A".format(max_current)))
    except:
        pass # ignore (e.g. if topic not found)


    # generate the tables
    def generate_html_table(rows_list, tooltip=None, max_width=None):
        """
        return the html table (str) from a row list of tuples
        """
        if tooltip is None:
            tooltip = ''
        else:
            tooltip = 'data-toggle="tooltip" data-placement="left" '+ \
                'data-delay=\'{"show": 1000, "hide": 100}\' title="'+tooltip+'" '
        table = '<table '+tooltip
        if max_width is not None:
            table += ' style="max-width: '+max_width+';"'
        table += '>'
        padding_text = ''
        for label, value in rows_list:
            if label == '': # empty label means: add some row spacing
                padding_text = ' style="padding-top: 0.5em;" '
            else:
                table += ('<tr><td '+padding_text+'class="left">'+label+
                          ':</td><td'+padding_text+'>'+value+'</td></tr>')
                padding_text = ''
        return table + '</table>'

    left_table = generate_html_table(table_text_left, max_width='65%')
    right_table = generate_html_table(
        table_text_right,
        'Note: most of these values are based on estimations from the vehicle,'
        ' and thus require an accurate estimator')
    html_tables = ('<p><div style="display: flex; justify-content: space-between;">'+
                   left_table+right_table+'</div></p>')

    return html_tables


def get_error_labels_html():
    """
    Get the html (as string) for user-selectable error labels
    """
    error_label_select = \
        '<select id="error-label" class="chosen-select" multiple="True" '\
        'style="display: none; " tabindex="-1" ' \
        'data-placeholder="Add a detected error..." " >'
    for err_id, err_label in error_labels_table.items():
        error_label_select += '<option data-id="{:d}">{:s}</option>'.format(err_id, err_label)
    error_label_select = '<p>' + error_label_select + '</select></p>'

    return error_label_select

def get_corrupt_log_html(ulog):
    """
    Get the html (as string) for corrupt logs,
    if the log is corrupt, otherwise returns None
    """
    if ulog.file_corruption:
        corrupt_log_html = """
<div class="card text-white bg-danger mb-3">
  <div class="card-header">Warning</div>
  <div class="card-body">
    <h4 class="card-title">Corrupt Log File</h4>
    <p class="card-text">
        This log contains corrupt data. Some of the shown data might be wrong
        and some data might be missing.
        <br />
        A possible cause is a corrupt file system and exchanging or reformatting
        the SD card fixes the problem.
        </p>
  </div>
</div>
"""
        return corrupt_log_html
    return None

def get_hardfault_html(ulog):
    """
    Get the html (as string) for hardfault information,
    if the log contains any, otherwise returns None
    """
    if 'hardfault_plain' in ulog.msg_info_multiple_dict:

        hardfault_html = """
<div class="card text-white bg-danger mb-3">
  <div class="card-header">Warning</div>
  <div class="card-body">
    <h4 class="card-title">Software Crash</h4>
    <p class="card-text">
        This log contains hardfault data from a software crash
        (see <a style="color:#fff; text-decoration: underline;"
        href="https://dev.px4.io/en/debug/gdb_debugging.html#debugging-hard-faults-in-nuttx">
        here</a> how to debug).
        <br/>
        The hardfault data is shown below.
        </p>
  </div>
</div>
"""

        counter = 1
        for hardfault in ulog.msg_info_multiple_dict['hardfault_plain']:
            hardfault_text = escape(''.join(hardfault)).replace('\n', '<br/>')
            hardfault_html += ('<p>Hardfault #'+str(counter)+':<br/><pre>'+
                               hardfault_text+'</pre></p>')
            counter += 1
        return hardfault_html
    return None

def get_changed_parameters(initial_parameters, plot_width):
    """
    get a bokeh column object with a table of the changed parameters
    :param initial_parameters: ulog.initial_parameters
    """
    param_names = []
    param_values = []
    param_defaults = []
    param_mins = []
    param_maxs = []
    param_descriptions = []
    default_params = get_default_parameters()
    for param_name in sorted(initial_parameters):
        param_value = initial_parameters[param_name]

        if param_name.startswith('RC') or param_name.startswith('CAL_'):
            continue

        try:
            if param_name in default_params:
                default_param = default_params[param_name]
                if default_param['type'] == 'FLOAT':
                    is_default = abs(float(default_param['default']) - float(param_value)) < 0.00001
                    if 'decimal' in default_param:
                        param_value = round(param_value, int(default_param['decimal']))
                else:
                    is_default = int(default_param['default']) == int(param_value)
                if not is_default:
                    param_names.append(param_name)
                    param_values.append(param_value)
                    param_defaults.append(default_param['default'])
                    param_mins.append(default_param.get('min', ''))
                    param_maxs.append(default_param.get('max', ''))
                    param_descriptions.append(default_param.get('short_desc', ''))
            else:
                # not found: add it as if it were changed
                param_names.append(param_name)
                param_values.append(param_value)
                param_defaults.append('')
                param_mins.append('')
                param_maxs.append('')
                param_descriptions.append('(unknown)')
        except Exception as error:
            print(type(error), error)
    param_data = dict(
        names=param_names,
        values=param_values,
        defaults=param_defaults,
        mins=param_mins,
        maxs=param_maxs,
        descriptions=param_descriptions)
    source = ColumnDataSource(param_data)
    columns = [
        TableColumn(field="names", title="Name",
                    width=int(plot_width*0.2), sortable=False),
        TableColumn(field="values", title="Value",
                    width=int(plot_width*0.15), sortable=False),
        TableColumn(field="defaults", title="Default",
                    width=int(plot_width*0.1), sortable=False),
        TableColumn(field="mins", title="Min",
                    width=int(plot_width*0.075), sortable=False),
        TableColumn(field="maxs", title="Max",
                    width=int(plot_width*0.075), sortable=False),
        TableColumn(field="descriptions", title="Description",
                    width=int(plot_width*0.40), sortable=False),
        ]
    data_table = DataTable(source=source, columns=columns, width=plot_width,
                           height=300, sortable=False, selectable=False)
    div = Div(text="""<b>Non-default Parameters</b> (except RC and sensor calibration)""",
              width=int(plot_width/2))
    return column(div, data_table, width=plot_width)


def get_logged_messages(logged_messages, plot_width):
    """
    get a bokeh column object with a table of the logged text messages
    :param logged_messages: ulog.logged_messages
    """
    log_times = []
    log_levels = []
    log_messages = []
    for m in logged_messages:
        m1, s1 = divmod(int(m.timestamp/1e6), 60)
        h1, m1 = divmod(m1, 60)
        log_times.append("{:d}:{:02d}:{:02d}".format(h1, m1, s1))
        log_levels.append(m.log_level_str())
        log_messages.append(m.message)
    log_data = dict(
        times=log_times,
        levels=log_levels,
        messages=log_messages)
    source = ColumnDataSource(log_data)
    columns = [
        TableColumn(field="times", title="Time",
                    width=int(plot_width*0.15), sortable=False),
        TableColumn(field="levels", title="Level",
                    width=int(plot_width*0.1), sortable=False),
        TableColumn(field="messages", title="Message",
                    width=int(plot_width*0.75), sortable=False),
        ]
    data_table = DataTable(source=source, columns=columns, width=plot_width,
                           height=300, sortable=False, selectable=False)
    div = Div(text="""<b>Logged Messages</b>""", width=int(plot_width/2))
    return column(div, data_table, width=plot_width)
