"""
Tornado handler for the radio controller page
"""
from __future__ import print_function
import tornado.web

#pylint: disable=relative-beyond-top-level
from .common import get_jinja_env

RADIO_CONTROLLER_TEMPLATE = 'radio_controller.html'

#pylint: disable=abstract-method

class RadioControllerHandler(tornado.web.RequestHandler):
    """ Tornado Request Handler to render the radio controller (for testing
        only) """

    def get(self, *args, **kwargs):
        """ GET request """

        template = get_jinja_env().get_template(RADIO_CONTROLLER_TEMPLATE)
        self.write(template.render())

