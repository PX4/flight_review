"""
Module for generating overview map
"""

import os
#pylint: disable=ungrouped-imports
import matplotlib
matplotlib.use('Agg')
import smopy
import matplotlib.pyplot as plt

from config import get_log_filepath, get_overview_img_filepath
from helper import load_ulog_file

MAXTILES = 16
def get_zoom(input_box, z=18):
    """
    Return acceptable zoom - we take this function from Map to get lover zoom
    """
    box_tile = smopy.get_tile_box(input_box, z)
    box = smopy.correct_box(box_tile, z)
    sx, sy = smopy.get_box_size(box)
    if sx * sy >= MAXTILES:
        z = get_zoom(input_box, z - 1)
    return z

def generate_overview_img_from_id(log_id):
    ''' This function will load file and save overview from/into configured directories
        '''
    ulog_file = os.path.join(get_log_filepath(), log_id+'.ulg')
    ulog = load_ulog_file(ulog_file)
    generate_overview_img(ulog, log_id)

def generate_overview_img(ulog, log_id):
    ''' This funciton will generate overwie for loaded ULog data
        '''
    output_filename = os.path.join(get_overview_img_filepath(), log_id+'.png')

    if os.path.exists(output_filename):
        return

    try:
        cur_dataset = ulog.get_dataset('vehicle_gps_position')
        t = cur_dataset.data['timestamp']
        indices = cur_dataset.data['fix_type'] > 2 # use only data with a fix
        lon = cur_dataset.data['lon'][indices] / 1e7 # degrees
        lat = cur_dataset.data['lat'][indices] / 1e7

        min_lat = min(lat)
        max_lat = max(lat)

        min_lon = min(lon)
        max_lon = max(lon)

        z = get_zoom((min_lat, min_lon, max_lat, max_lon)) - 2
        if z < 0:
            z = 0

        render_map = smopy.Map((min_lat, min_lon, max_lat, max_lon), z=z)
        fig, axes = plt.subplots(nrows=1, ncols=1)
        render_map.show_mpl(figsize=(8, 6), ax=axes)

        x, y = render_map.to_pixels(lat, lon)
        axes.plot(x, y, 'r')

        axes.set_axis_off()
        plt.savefig(output_filename, bbox_inches='tight')
        plt.close(fig)

        print('Saving overview file '+ output_filename)

    except:
        # Ignore. Eg. if topic not found
        print('Error generating overview file: '+ output_filename+' - No GPS?')

