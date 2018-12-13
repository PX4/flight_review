"""
Module for generating overview map
"""

import os

import smopy
import matplotlib.pyplot as plt

def generate_overview_img(ulog, log_id, output_path):
    ''' This map overview image is loaded by browse page

    '''

    output_filename = os.path.join(output_path, log_id+'.png')

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

        render_map = smopy.Map((min_lat, min_lon, max_lat, max_lon))
        fig, axes = plt.subplots(nrows=1, ncols=1)
        render_map.show_mpl(figsize=(8, 6), ax=axes)

        for i in range(len(lat)):
            x, y = render_map.to_pixels(lat[i], lon[i])
            axes.plot(x, y, '.r')

        axes.set_axis_off()
        plt.savefig(output_filename, bbox_inches='tight')
        plt.close(fig)

        print('Saving overview file '+ output_filename)
    except:
        # Ignore. Eg. if topic not found
        print('Error generating overview file: '+ output_filename+' - No GPS?')

