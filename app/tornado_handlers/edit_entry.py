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
        elif action == 'edit':
            # Get log details from database
            con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
            cur = con.cursor()
            cur.execute('SELECT Description, Rating, VideoUrl, Feedback FROM Logs WHERE Id = ?', (log_id,))
            db_tuple = cur.fetchone()
            cur.close()
            con.close()

            if db_tuple is None:
                raise tornado.web.HTTPError(404, 'Log not found')

            description, rating, video_url, feedback = db_tuple
            
            content = f"""
<h3>Edit Log {escape(log_id)}</h3>
<form method="POST" action="/edit_entry">
    <input type="hidden" name="log" value="{escape(log_id)}">
    <input type="hidden" name="token" value="{escape(token)}">
    <input type="hidden" name="action" value="edit">
    
    <div class="form-group">
        <label for="description">Description:</label>
        <textarea class="form-control" id="description" name="description" rows="3">{escape(description or '')}</textarea>
    </div>
    
    <div class="form-group">
        <label for="feedback">Feedback:</label>
        <textarea class="form-control" id="feedback" name="feedback" rows="3">{escape(feedback or '')}</textarea>
    </div>
    
    <div class="form-group">
        <label for="video_url">Video URL:</label>
        <input type="url" class="form-control" id="video_url" name="video_url" value="{escape(video_url or '')}">
    </div>
    
    <div class="form-group">
        <label for="rating">Rating:</label>
        <select class="form-control" id="rating" name="rating">
            <option value="0" {' selected' if rating == 0 else ''}>Unrated</option>
            <option value="1" {' selected' if rating == 1 else ''}>Good</option>
            <option value="2" {' selected' if rating == 2 else ''}>Warning</option>
            <option value="3" {' selected' if rating == 3 else ''}>Error</option>
        </select>
    </div>
    
    <div class="form-group">
        <button type="submit" class="btn btn-primary">Save Changes</button>
        <a href="/plot_app?log={escape(log_id)}" class="btn btn-secondary">Cancel</a>
    </div>
</form>
"""
        else:
            raise tornado.web.HTTPError(400, 'Invalid Parameter')

        template = get_jinja_env().get_template(EDIT_TEMPLATE)
        self.write(template.render(content=content))

    def post(self, *args, **kwargs):
        """Handle POST request for editing log details"""
        log_id = escape(self.get_argument('log'))
        token = escape(self.get_argument('token'))
        action = self.get_argument('action')

        if action != 'edit':
            raise tornado.web.HTTPError(400, 'Invalid Action')

        # Verify token
        con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
        cur = con.cursor()
        cur.execute('select Token from Logs where Id = ?', (log_id,))
        db_tuple = cur.fetchone()
        
        if db_tuple is None:
            cur.close()
            con.close()
            raise tornado.web.HTTPError(404, 'Log not found')
            
        if token != db_tuple[0] and token != 'public':
            cur.close()
            con.close()
            raise tornado.web.HTTPError(403, 'Invalid token')

        # Update log details
        description = self.get_argument('description', '')
        video_url = self.get_argument('video_url', '')
        rating = int(self.get_argument('rating', '0'))
        feedback = self.get_argument('feedback', '')

        cur.execute('''UPDATE Logs 
                      SET Description = ?, VideoUrl = ?, Rating = ?, Feedback = ?
                      WHERE Id = ?''', 
                   (description, video_url, rating, feedback, log_id))
        con.commit()
        cur.close()
        con.close()

        content = f"""
<h3>Log Updated</h3>
<p>Successfully updated the log details.</p>
<p><a href="/plot_app?log={escape(log_id)}">Return to log</a></p>
"""
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
        
        # Allow either matching token or public token
        if token != db_tuple[0] and token != 'public':
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
