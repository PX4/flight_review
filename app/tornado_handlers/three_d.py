"""
Tornado handler for the 3D page
"""
from __future__ import print_function
import datetime
import os
import sys
import tornado.web
import numpy as np

# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../plot_app'))
from config import get_bing_maps_api_key, get_cesium_api_key
from helper import validate_log_id, get_log_filename, load_ulog_file, \
    get_flight_mode_changes, flight_modes_table

#pylint: disable=relative-beyond-top-level
from .common import get_jinja_env, CustomHTTPError, TornadoRequestHandlerBase

THREED_TEMPLATE = '3d.html'

#pylint: disable=abstract-method, unused-argument

class ThreeDHandler(TornadoRequestHandlerBase):
    """ Tornado Request Handler to render the 3D Cesium.js page """

    def get(self, *args, **kwargs):
        """ GET request callback """

        # load the log file
        log_id = self.get_argument('log')
        if not validate_log_id(log_id):
            raise tornado.web.HTTPError(400, 'Invalid Parameter')
        log_file_name = get_log_filename(log_id)
        ulog = load_ulog_file(log_file_name)

        # extract the necessary information from the log

        try:
            # required topics: none of these are optional
            gps_pos = ulog.get_dataset('vehicle_gps_position').data
            vehicle_global_position = ulog.get_dataset('vehicle_global_position').data
            attitude = ulog.get_dataset('vehicle_attitude').data
        except (KeyError, IndexError, ValueError) as error:
            raise CustomHTTPError(
                400,
                'The log does not contain all required topics<br />'
                '(vehicle_gps_position, vehicle_global_position, '
                'vehicle_attitude)') from error

        # manual control setpoint is optional
        manual_control_setpoint = None
        try:
            manual_control_setpoint = ulog.get_dataset('manual_control_setpoint').data
        except (KeyError, IndexError, ValueError) as error:
            pass


        # Get the takeoff location. We use the first position with a valid fix,
        # and assume that the vehicle is not in the air already at that point
        takeoff_index = 0
        gps_indices = np.nonzero(gps_pos['fix_type'] > 2)
        if len(gps_indices[0]) > 0:
            takeoff_index = gps_indices[0][0]
        takeoff_altitude = '{:.3f}' \
            .format(gps_pos['alt'][takeoff_index] * 1.e-3)
        takeoff_latitude = '{:.10f}'.format(gps_pos['lat'][takeoff_index] * 1.e-7)
        takeoff_longitude = '{:.10f}'.format(gps_pos['lon'][takeoff_index] * 1.e-7)


        # calculate UTC time offset (assume there's no drift over the entire log)
        utc_offset = int(gps_pos['time_utc_usec'][takeoff_index]) - \
                int(gps_pos['timestamp'][takeoff_index])

        # flight modes
        flight_mode_changes = get_flight_mode_changes(ulog)
        flight_modes_str = '[ '
        for t, mode in flight_mode_changes:
            t += utc_offset
            utctimestamp = datetime.datetime.utcfromtimestamp(t/1.e6).replace(
                tzinfo=datetime.timezone.utc)
            if mode in flight_modes_table:
                mode_name, color = flight_modes_table[mode]
            else:
                mode_name = ''
                color = '#ffffff'
            flight_modes_str += '["{:}", "{:}"], ' \
                .format(utctimestamp.isoformat(), mode_name)
        flight_modes_str += ' ]'

        # manual control setpoints (stick input)
        manual_control_setpoints_str = '[ '
        if manual_control_setpoint:
            for i in range(len(manual_control_setpoint['timestamp'])):
                manual_x = manual_control_setpoint['x'][i]
                manual_y = manual_control_setpoint['y'][i]
                manual_z = manual_control_setpoint['z'][i]
                manual_r = manual_control_setpoint['r'][i]
                t = manual_control_setpoint['timestamp'][i] + utc_offset
                utctimestamp = datetime.datetime.utcfromtimestamp(t/1.e6).replace(
                    tzinfo=datetime.timezone.utc)
                manual_control_setpoints_str += '["{:}", {:.3f}, {:.3f}, {:.3f}, {:.3f}], ' \
                    .format(utctimestamp.isoformat(), manual_x, manual_y, manual_z, manual_r)
        manual_control_setpoints_str += ' ]'


        # position
        # Note: alt_ellipsoid from gps_pos would be the better match for
        # altitude, but it's not always available. And since we add an offset
        # (to match the takeoff location with the ground altitude) it does not
        # matter as much.
        position_data = '[ '
        # TODO: use vehicle_global_position? If so, then:
        # - altitude requires an offset (to match the GPS data)
        # - it's worse for some logs where the estimation is bad -> acro flights
        #   (-> add both: user-selectable between GPS & estimated trajectory?)
        for i in range(len(gps_pos['timestamp'])):
            lon = gps_pos['lon'][i] * 1.e-7
            lat = gps_pos['lat'][i] * 1.e-7
            alt = gps_pos['alt'][i] * 1.e-3
            t = gps_pos['timestamp'][i] + utc_offset
            utctimestamp = datetime.datetime.utcfromtimestamp(t/1.e6).replace(
                tzinfo=datetime.timezone.utc)
            if i == 0:
                start_timestamp = utctimestamp
            end_timestamp = utctimestamp
            position_data += '["{:}", {:.10f}, {:.10f}, {:.3f}], ' \
                .format(utctimestamp.isoformat(), lon, lat, alt)
        position_data += ' ]'

        start_timestamp_str = '"{:}"'.format(start_timestamp.isoformat())
        boot_timestamp = datetime.datetime.utcfromtimestamp(utc_offset/1.e6).replace(
            tzinfo=datetime.timezone.utc)
        boot_timestamp_str = '"{:}"'.format(boot_timestamp.isoformat())
        end_timestamp_str = '"{:}"'.format(end_timestamp.isoformat())

        # orientation as quaternion
        attitude_data = '[ '
        for i in range(len(attitude['timestamp'])):
            att_qw = attitude['q[0]'][i]
            att_qx = attitude['q[1]'][i]
            att_qy = attitude['q[2]'][i]
            att_qz = attitude['q[3]'][i]
            t = attitude['timestamp'][i] + utc_offset
            utctimestamp = datetime.datetime.utcfromtimestamp(t/1.e6).replace(
                tzinfo=datetime.timezone.utc)
            # Cesium uses (x, y, z, w)
            attitude_data += '["{:}", {:.6f}, {:.6f}, {:.6f}, {:.6f}], ' \
                .format(utctimestamp.isoformat(), att_qx, att_qy, att_qz, att_qw)
        attitude_data += ' ]'

        # handle different vehicle types
        # the model_scale_factor should scale the different models to make them
        # equal in size (in proportion)
        mav_type = ulog.initial_parameters.get('MAV_TYPE', None)
        if mav_type == 1: # fixed wing
            model_scale_factor = 0.06
            model_uri = 'plot_app/static/cesium/SampleData/models/CesiumAir/Cesium_Air.glb'
        elif mav_type == 2: # quad
            model_scale_factor = 1
            model_uri = 'plot_app/static/cesium/models/iris/iris.glb'
        elif mav_type == 22: # delta-quad
            # TODO: use the delta-quad model
            model_scale_factor = 0.06
            model_uri = 'plot_app/static/cesium/SampleData/models/CesiumAir/Cesium_Air.glb'
        else: # TODO: handle more types
            model_scale_factor = 1
            model_uri = 'plot_app/static/cesium/models/iris/iris.glb'

        template = get_jinja_env().get_template(THREED_TEMPLATE)
        self.write(template.render(
            flight_modes=flight_modes_str,
            manual_control_setpoints=manual_control_setpoints_str,
            takeoff_altitude=takeoff_altitude,
            takeoff_longitude=takeoff_longitude,
            takeoff_latitude=takeoff_latitude,
            position_data=position_data,
            start_timestamp=start_timestamp_str,
            boot_timestamp=boot_timestamp_str,
            end_timestamp=end_timestamp_str,
            attitude_data=attitude_data,
            model_scale_factor=model_scale_factor,
            model_uri=model_uri,
            log_id=log_id,
            bing_api_key=get_bing_maps_api_key(),
            cesium_api_key=get_cesium_api_key()))

