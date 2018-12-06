import os 

import smopy
from IPython.display import Image

import matplotlib.pyplot as plt

def generate_overview_img(ulog, log_id, output_path):
   ''' This map overview image is loaded by browse page

   '''

   output_filename=os.path.join(output_path,log_id+'.png')

   print(output_filename)
 
   if os.path.exists(output_filename):
      return

   cur_dataset = ulog.get_dataset('vehicle_gps_position')
   t = cur_dataset.data['timestamp']
   indices = cur_dataset.data['fix_type'] > 2 # use only data with a fix
   #t = t[indices]
   lon = cur_dataset.data['lon'][indices] / 1e7 # degrees
   lat = cur_dataset.data['lat'][indices] / 1e7
   #altitude = cur_dataset.data['alt'][indices] / 1e3 # meters

   min_lat=min(lat);
   max_lat=max(lat);

   min_lon=min(lon);
   max_lon=max(lon);
  

   map = smopy.Map((min_lat,min_lon,max_lat,max_lon))
   fig, ax = plt.subplots( nrows=1, ncols=1 ) 
   map.show_mpl(figsize=(8, 6), ax=ax)

   for i in range(len(lat)):
      x, y = map.to_pixels(lat[i], lon[i])
      ax.plot(x, y,'.r');

   ax.set_axis_off()
   plt.savefig(output_filename, bbox_inches='tight')
   plt.close(fig)

   print('Saving overview file '+ output_filename)


