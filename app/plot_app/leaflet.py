""" Data extraction/conversion methods to get the flight path that is passed to
a Leaflet map via jinja arguments """

from colors import HTML_color_to_RGB
from config_tables import flight_modes_table
from helper import get_lat_lon_alt_deg

#pylint: disable=consider-using-enumerate

def ulog_to_polyline(ulog, flight_mode_changes):
    """ extract flight mode colors and position data from the log
        :return: tuple(position data list, flight modes)
    """
    def rgb_colors(flight_mode):
        """ flight mode color from a flight mode """
        if flight_mode not in flight_modes_table: flight_mode = 0

        color_str = flight_modes_table[flight_mode][1] # color in form '#ff00aa'
        # increase brightness to match colors with template
        rgb = HTML_color_to_RGB(color_str)
        for i in range(3):
            rgb[i] += 40
            if rgb[i] > 255: rgb[i] = 255

        return "#" + "".join(map(lambda x: format(x, '02x'), rgb))
    cur_data = ulog.get_dataset('vehicle_gps_position')
    pos_lat, pos_lon, _ = get_lat_lon_alt_deg(ulog, cur_data)
    pos_t = cur_data.data['timestamp']

    if 'fix_type' in cur_data.data:
        indices = cur_data.data['fix_type'] > 2  # use only data with a fix
        pos_lon = pos_lon[indices]
        pos_lat = pos_lat[indices]
        pos_t = pos_t[indices]

    pos_datas = []
    flight_modes = []
    last_t = 0
    minimum_interval_s = 0.1
    current_flight_mode_idx = 0
    for i in range(len(pos_lon)):
        curr_t = pos_t[i]
        if (curr_t - last_t) / 1e6 > minimum_interval_s:
            pos_datas.append([float(pos_lat[i]), float(pos_lon[i])])
            last_t = curr_t
            while current_flight_mode_idx < len(flight_mode_changes) - 1 and \
                    flight_mode_changes[current_flight_mode_idx][0] <= curr_t:
                current_flight_mode = flight_mode_changes[current_flight_mode_idx][1]
                current_flight_mode_idx += 1
                flight_modes.append([rgb_colors(current_flight_mode), i])
    flight_modes.append(['', len(pos_lon)])
    return (pos_datas, flight_modes)
