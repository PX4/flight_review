
import sys
import os

# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plot_app'))
from plot_app.config import *

from smtplib import SMTP_SSL as SMTP       # this invokes the secure SMTP protocol (port 465, uses SSL)
# from smtplib import SMTP                  # use this for standard SMTP protocol   (port 25, no encryption)
from email.mime.text import MIMEText



def send_notification_email(email_adress, plot_url, log_description):
    """ send a notification email after uploading a plot """

    # typical values for text_subtype are plain, html, xml
    text_subtype = 'plain'

    subject="Log File uploaded"
    destination = [email_adress]

    content="""\
Hi there!

Your uploaded log file with description '{description}' is available under:
{plot_url}
"""

    try:
        msg = MIMEText(content.format(plot_url=plot_url,
            description=log_description), text_subtype)
        msg['Subject'] = subject
        sender = email_config['sender']
        msg['From'] = sender # some SMTP servers will do this automatically

        conn = SMTP(email_config['SMTPserver'])
        conn.set_debuglevel(False)
        conn.login(email_config['user_name'], email_config['password'])
        try:
            conn.sendmail(sender, destination, msg.as_string())
        finally:
            conn.quit()

    except Exception as exc:
        print("mail failed; {:}".format(str(exc)))
        return False
    return True
