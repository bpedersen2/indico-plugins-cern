from __future__ import unicode_literals

import re
from datetime import timedelta

import icalendar
from flask import request

from indico.modules.events.requests.models.requests import RequestState
from indico.util.string import to_unicode
from indico.web.flask.util import url_for
from indico.web.http_api import HTTPAPIHook
from indico.web.http_api.responses import HTTPAPIError
from indico.web.http_api.util import get_query_parameter
from MaKaC.conference import Conference, Contribution, SubContribution, ConferenceHolder, Link, Material

from indico_audiovisual import SERVICES, SHORT_SERVICES
from indico_audiovisual.definition import AVRequest
from indico_audiovisual.util import find_requests


def parse_indico_id(indico_id):
    event_match = re.match('(\w*\d+)$', indico_id)
    session_match = re.match('(\w*\d+)s(\d+|s\d+)$', indico_id)
    contrib_match = re.match('(\w*\d+)c(\d+|s\d+t\d+)$', indico_id)
    subcontrib_match = re.match('(\w*\d+)c(\d+|s\d+t\d+)sc(\d+)$', indico_id)

    if subcontrib_match:
        event = ConferenceHolder().getById(subcontrib_match.group(1), True)
        if not event:
            return None
        contrib = event.getContributionById(subcontrib_match.group(2))
        if not contrib:
            return None
        return contrib.getSubContributionById(subcontrib_match.group(3))
    elif session_match:
        event = ConferenceHolder().getById(session_match.group(1), True)
        if not event:
            return None
        return event.getSessionById(session_match.group(2))
    elif contrib_match:
        event = ConferenceHolder().getById(contrib_match.group(1), True)
        if not event:
            return None
        return event.getContributionById(contrib_match.group(2))
    elif event_match:
        return ConferenceHolder().getById(event_match.group(1), True)
    else:
        return None


def cds_link_exists(obj):
    materials = obj.getAllMaterialList() or []
    for material in materials:
        if isinstance(material.getMainResource(), Link) and to_unicode(material.getTitle()) == 'Video in CDS':
            return True
    return False


def create_link(indico_id, cds_id):
    from indico_audiovisual.plugin import AVRequestsPlugin

    obj = parse_indico_id(indico_id)
    if obj is None:
        return False
    elif cds_link_exists(obj):
        return True

    url = AVRequestsPlugin.settings.get('recording_cds_url')
    if not url:
        return False

    material = Material()
    material.setTitle(b'Video in CDS')
    video_link = Link()
    video_link.setOwner(material)
    video_link.setName(b'Video in CDS')
    video_link.setURL(url.format(cds_id=cds_id))
    material.addResource(video_link)
    material.setMainResource(video_link)
    obj.addMaterial(material)
    return True


class RecordingLinkAPI(HTTPAPIHook):
    PREFIX = 'api'
    TYPES = ('create_cds_link',)
    RE = ''
    GUEST_ALLOWED = False
    VALID_FORMATS = ('json',)
    COMMIT = True
    HTTP_POST = True

    def _hasAccess(self, aw):
        return AVRequest.can_be_managed(aw.getUser())

    def _getParams(self):
        super(RecordingLinkAPI, self)._getParams()
        self._indico_id = get_query_parameter(self._queryParams, ['iid', 'indicoID'])
        self._cds_id = get_query_parameter(self._queryParams, ['cid', 'cdsID'])

    def api_create_cds_link(self, aw):
        if not self._indico_id or not self._cds_id:
            raise HTTPAPIError('A required argument is missing.', 400)
        success = create_link(self._indico_id, self._cds_id)
        return {'success': success}


class AVExportHook(HTTPAPIHook):
    TYPES = (AVRequest.name,)
    RE = ''
    DEFAULT_DETAIL = 'default'
    MAX_RECORDS = {'default': 100}
    GUEST_ALLOWED = False
    VALID_FORMATS = ('json', 'jsonp', 'xml', 'ics')

    def _getParams(self):
        super(AVExportHook, self)._getParams()
        self._services = set(request.args.getlist('service'))
        self._alarm = get_query_parameter(self._queryParams, ['alarms'], None, True)

    def _hasAccess(self, aw):
        return AVRequest.can_be_managed(aw.getUser())

    @property
    def serializer_args(self):
        return {'ical_serializer': _ical_serialize_av}

    def export_webcast_recording(self, aw):
        results = find_requests(talks=True, from_dt=self._fromDT, to_dt=self._toDT, services=self._services,
                                states=(RequestState.accepted, RequestState.pending))
        for req, contrib, _ in results:
            yield _serialize_obj(req, contrib, self._alarm)


def _serialize_obj(req, obj, alarm):
    # Util to serialize an event, contribution or subcontribution
    # in the context of a webcast/recording request
    url = title = unique_id = None
    date_source = obj
    if isinstance(obj, Conference):
        url = url_for('event.conferenceDisplay', obj, _external=True)
        title = to_unicode(obj.getTitle())
        unique_id = 'e{}'.format(obj.id)
    elif isinstance(obj, Contribution):
        url = url_for('event.contributionDisplay', obj, _external=True)
        title = '{} - {}'.format(to_unicode(obj.getConference().getTitle()),
                                 to_unicode(obj.getTitle()))
        unique_id = 'e{}c{}'.format(obj.getConference().id, obj.id)
    elif isinstance(obj, SubContribution):
        url = url_for('event.subContributionDisplay', obj, _external=True)
        title = '{} - {} - {}'.format(to_unicode(obj.getConference().getTitle()),
                                      to_unicode(obj.getContribution().getTitle()),
                                      to_unicode(obj.getTitle()))
        unique_id = 'e{}c{}-{}'.format(obj.getConference().id, obj.getContribution().id, obj.id)
        date_source = obj.getContribution()

    audience = None
    if 'webcast' in req.data['services']:
        audience = req.data['webcast_audience'] or 'No restriction'

    data = {
        'status': 'P' if req.state == RequestState.pending else 'A',
        'services': req.data['services'],
        'event_id': req.event_id,
        'startDate': date_source.getStartDate(),
        'endDate': date_source.getEndDate(),
        'title': title,
        'location': to_unicode(obj.getLocation().getName() if obj.getLocation() else None),
        'room': to_unicode(obj.getRoom().getName() if obj.getRoom() else None),
        'url': url,
        'audience': audience,
        '_ical_id': 'indico-audiovisual-{}@cern.ch'.format(unique_id)
    }
    if alarm:
        data['_ical_alarm'] = alarm
    return data


def _ical_summary(record):
    return '{}:{} - {}'.format('+'.join(map(SHORT_SERVICES.get, record['services'])),
                               record['status'],
                               record['title'])


def _ical_serialize_av(cal, record, now):
    event = icalendar.Event()
    event.add('uid', record['_ical_id'])
    event.add('dtstamp', now)
    event.add('dtstart', record['startDate'])
    event.add('dtend', record['endDate'])
    event.add('url', record['url'])
    event.add('categories', 'Webcast/Recording')
    event.add('summary', _ical_summary(record))
    location = ': '.join(filter(None, (record['location'], record['room'])))
    event.add('location', location)
    description = ['URL: {}'.format(record['url']),
                   'Services: {}'.format(', '.join(map(unicode, map(SERVICES.get, record['services']))))]
    if record['audience']:
        description.append('Audience: {}'.format(record['audience']))
    event.add('description', '\n'.join(description))
    if '_ical_alarm' in record:
        event.add_component(_ical_serialize_av_alarm(record))
    cal.add_component(event)


def _ical_serialize_av_alarm(record):
    alarm = icalendar.Alarm()
    alarm.add('trigger', timedelta(minutes=-int(record['_ical_alarm'])))
    alarm.add('action', 'DISPLAY')
    alarm.add('summary', _ical_summary(record))
    alarm.add('description', str(record['url']))
    return alarm
