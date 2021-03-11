"""
Tornado handler to edit/delete a log upload entry
"""
from __future__ import print_function
import os
from html import escape
import sqlite3
import sys
import tornado.web

# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../plot_app'))
from config import get_db_filename, get_kml_filepath, get_overview_img_filepath
from helper import clear_ulog_cache, get_log_filename

#pylint: disable=relative-beyond-top-level
from .common import get_jinja_env

EDIT_TEMPLATE = 'edit.html'

#pylint: disable=abstract-method


class EditEntryHandler(tornado.web.RequestHandler):
    """ Edit a log entry, with confirmation (currently only delete) """

    def get(self, *args, **kwargs):
        """ GET request """
        log_id = escape(self.get_argument('log'))
        action = self.get_argument('action')
        confirmed = self.get_argument('confirm', default='0')
        token = escape(self.get_argument('token'))

        if action == 'delete':
            if confirmed == '1':
                if self.delete_log_entry(log_id, token):
                    content = """
<h3>Log File deleted</h3>
<p>
Successfully deleted the log file.
</p>
"""
                else:
                    content = """
<h3>Failed</h3>
<p>
Failed to delete the log file.
</p>
"""
            else: # request user to confirm
                # use the same url, just append 'confirm=1'
                delete_url = self.request.path+'?action=delete&log='+log_id+ \
                        '&token='+token+'&confirm=1'
                content = """
<h3>Delete Log File</h3>
<p>
Click <a href="{delete_url}">here</a> to confirm and delete the log {log_id}.
</p>
""".format(delete_url=delete_url, log_id=log_id)
        else:
            raise tornado.web.HTTPError(400, 'Invalid Parameter')

        template = get_jinja_env().get_template(EDIT_TEMPLATE)
        self.write(template.render(content=content))


    @staticmethod
    def delete_log_entry(log_id, token):
        """
        delete a log entry (DB & file), validate token first

        :return: True on success
        """
        con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
        cur = con.cursor()
        cur.execute('select Token from Logs where Id = ?', (log_id,))
        db_tuple = cur.fetchone()
        if db_tuple is None:
            return False
        if token != db_tuple[0]: # validate token
            return False

        # kml file
        kml_path = get_kml_filepath()
        kml_file_name = os.path.join(kml_path, log_id.replace('/', '.')+'.kml')
        if os.path.exists(kml_file_name):
            os.unlink(kml_file_name)

        #preview image
        preview_image_filename = os.path.join(get_overview_img_filepath(), log_id+'.png')
        if os.path.exists(preview_image_filename):
            os.unlink(preview_image_filename)

        log_file_name = get_log_filename(log_id)
        print('deleting log entry {} and file {}'.format(log_id, log_file_name))
        os.unlink(log_file_name)
        cur.execute("DELETE FROM LogsGenerated WHERE Id = ?", (log_id,))
        cur.execute("DELETE FROM Logs WHERE Id = ?", (log_id,))
        con.commit()
        cur.close()
        con.close()

        # need to clear the cache as well
        clear_ulog_cache()

        return True
