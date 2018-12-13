
import os
import sys

# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plot_app'))
from plot_app.config import get_log_filepath, get_overview_img_filepath
from plot_app.overview_generator import generate_overview_img
from plot_app.helper import load_ulog_file

log_directory=get_log_filepath()
for filename in os.listdir(log_directory):
    full_filepath=os.path.join(log_directory, filename)
    print(full_filepath)
    if filename.endswith(".ulg"):     
        log_id = os.path.splitext(filename)[0]      
        ulog = load_ulog_file(full_filepath)
        generate_overview_img(ulog,log_id,get_overview_img_filepath())



