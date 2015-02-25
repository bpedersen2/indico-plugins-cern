from functools import partial

from flask_pluginengine import render_plugin_template
from wtforms.fields import IntegerField
from wtforms.fields.simple import StringField
from wtforms.fields.html5 import URLField
from wtforms.validators import DataRequired, NumberRange

from indico.core.config import Config
from indico.core.plugins import IndicoPlugin, PluginCategory
from indico.modules.vc.views import WPVCManageEvent
from indico.util.i18n import _
from indico.web.forms.base import IndicoForm
from indico.web.forms.fields import UnsafePasswordField


class SettingsForm(IndicoForm):  # pragma: no cover
    api_endpoint = URLField(_('API endpoint'), [DataRequired()], filters=[lambda x: x.rstrip('/') + '/'],
                            description=_('The endpoint for the RAVEM API'))
    username = StringField(_('Username'), [DataRequired()],
                           description=_('The username used to connect to the RAVEM API'))
    password = UnsafePasswordField(_('Password'), [DataRequired()],
                                   description=_('The password used to connect to the RAVEM API'))
    prefix = IntegerField(_('Room IP prefix'), [NumberRange(min=0)],
                                      description=_('IP prefix to connect a room to a Vidyo room.'))


class RavemPlugin(IndicoPlugin):
    """RAVEM

    Manages connections to Vidyo rooms from Indico through the RAVEM api
    """
    configurable = True
    strict_settings = True
    settings_form = SettingsForm
    default_settings = {
        'api_endpoint': 'https://ravem.cern.ch/api/services',
        'username': 'ravem',
        'password': None,
        'prefix': 21
    }
    category = PluginCategory.videoconference

    def init(self):
        super(RavemPlugin, self).init()
        if not Config.getInstance().getIsRoomBookingActive():
            from indico_ravem.util import RavemException
            raise RavemException('RoomBooking is inactive.')

        self.template_hook('vidyo-manage-event-buttons',
                           partial(self.inject_connect_button, 'vc_rooms_manage_button.html'))
        self.template_hook('vidyo-event-buttons',
                           partial(self.inject_connect_button, 'vc_rooms_list_button.html'))
        self.template_hook('vidyo-event-timetable-buttons',
                           partial(self.inject_connect_button, 'vc_rooms_list_button.html'))
        self.inject_js('ravem_js', WPVCManageEvent)

    def get_blueprints(self):
        from indico_ravem.blueprint import blueprint
        return blueprint

    def register_assets(self):
        self.register_js_bundle('ravem_js', 'js/ravem.js')

    def inject_connect_button(self, template, event_vc_room, **kwargs):
        # TODO check if can connect room
        return render_plugin_template(template, event_vc_room=event_vc_room, event=event_vc_room.event,
                                      vc_room=event_vc_room.vc_room, room=event_vc_room.link_object.getRoom())
