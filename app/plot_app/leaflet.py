""" Data extraction/conversion methods to get the flight path that is passed to
a Leaflet map via jinja arguments """

from colors import HTML_color_to_RGB
from config_tables import flight_modes_table

#pylint: disable=consider-using-enumerate

def ulog_to_polyline(ulog, flight_mode_changes):
    """ extract flight mode colors and position data from the log
        :return: tuple(position data list, flight modes)
    """
    def rgb_colors(flight_mode):
        """ flight mode color from a flight mode """
        if not flight_mode in flight_modes_table: flight_mode = 0

        color_str = flight_modes_table[flight_mode][1] # color in form '#ff00aa'
        # increase brightness to match colors with template
        rgb = HTML_color_to_RGB(color_str)
        for i in range(3):
            rgb[i] += 40
            if rgb[i] > 255: rgb[i] = 255

        return "#" + "".join(map(lambda x: format(x, '02x'), rgb))
    cur_data = ulog.get_dataset('vehicle_gps_position')
    pos_lon = cur_data.data['lon']
    pos_lat = cur_data.data['lat']
    pos_alt = cur_data.data['alt']
    pos_t = cur_data.data['timestamp']

    if 'fix_type' in cur_data.data:
        indices = cur_data.data['fix_type'] > 2  # use only data with a fix
        pos_lon = pos_lon[indices]
        pos_lat = pos_lat[indices]
        pos_alt = pos_alt[indices]
        pos_t = pos_t[indices]

    # scale if it's an integer type
    lon_type = [f.type_str for f in cur_data.field_data if f.field_name == 'lon']
    if len(lon_type) > 0 and lon_type[0] == 'int32_t':
        pos_lon = pos_lon / 1e7  # to degrees
        pos_lat = pos_lat / 1e7
        pos_alt = pos_alt / 1e3  # to meters

    pos_datas = []
    flight_modes = []
    last_t = 0
    minimum_interval_s = 0.1
    current_flight_mode_idx = 0
    for i in range(len(pos_lon)):
        curr_t = pos_t[i]
        if (curr_t - last_t) / 1e6 > minimum_interval_s:
            pos_datas.append([pos_lat[i], pos_lon[i]])
            last_t = curr_t
            while current_flight_mode_idx < len(flight_mode_changes) - 1 and \
                    flight_mode_changes[current_flight_mode_idx][0] <= curr_t:
                current_flight_mode = flight_mode_changes[current_flight_mode_idx][1]
                current_flight_mode_idx += 1
                flight_modes.append([rgb_colors(current_flight_mode), i])
    flight_modes.append(['', len(pos_lon)])
    return (pos_datas, flight_modes)
