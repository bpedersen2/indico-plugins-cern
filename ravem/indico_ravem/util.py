import requests
from requests.auth import HTTPDigestAuth
from requests.exceptions import HTTPError, Timeout
from urlparse import urljoin

from flask import request, session

from indico.util.i18n import _
from indico.util.user import retrieve_principal

from indico_ravem.plugin import RavemPlugin


def ravem_api_call(api_endpoint, method='GET', **kwargs):
    """Emits a call to the given RAVEM API endpoint.

    This function is meant to be used to easily generate calls to the RAVEM API.
    The RAVEM URL, username and password are automatically fetched from the
    settings of the RAVEM plugin each time.

    :param api_endpoint: str -- The RAVEM API endpoint to call.
    :param method: str -- The HTTP method to use for the call, currently, RAVEM
                   only supports `GET` or `POST`
    :param **kwargs: The field names and values used for the RAVEM API as
                     strings

    :returns: dict -- The JSON-encoded response from the RAVEM
    :raises: HTTPError if the request returns an HTTP Error (400 or 500)
    :raises: RavemAPIException if RAVEM returns an error message
    """
    if method.upper() == 'GET':
        request = requests.get
    elif method.upper() == 'POST':
        request = requests.post
    else:
        raise ValueError('Unsupported HTTP method {method}, must be GET or POST'.format(method=method))

    root_endpoint = RavemPlugin.settings.get('api_endpoint')
    username = RavemPlugin.settings.get('username')
    password = RavemPlugin.settings.get('password')
    headers = {'Accept': 'application/json'}
    timeout = RavemPlugin.settings.get('timeout') or None

    try:
        response = request(urljoin(root_endpoint, api_endpoint), auth=HTTPDigestAuth(username, password), params=kwargs,
                           verify=False, headers=headers, timeout=timeout)
    except Timeout as error:
        RavemPlugin.logger.warning("{error.request.method} {error.request.url} timed out: {error.message}"
                                   .format(error=error))
        # request timeout sometime has an inner timeout error as message instead of a string.
        raise Timeout(_("Timeout while contacting the room."))
    except Exception as error:
        RavemPlugin.logger.exception(
            "failed call: {method} {api_endpoint} with {params}: {error.message}"
            .format(method=method.upper(), api_endpoint=api_endpoint, params=kwargs, error=error)
        )
        raise

    try:
        response.raise_for_status()
    except HTTPError as error:
        RavemPlugin.logger.exception("{response.request.method} {response.url} failed with {error.message}"
                                     .format(response=response, error=error))
        raise

    json_response = response.json()
    if 'error' not in json_response and 'result' not in json_response:
        err_msg = ("{response.request.method} {response.url} returned a json without a result or error: "
                   "{json_response}").format(response=response, json_response=json_response)
        RavemPlugin.logger.exception(err_msg)
        raise RavemAPIException(err_msg, api_endpoint, response)

    return json_response


def get_room_endpoint(endpoints):
    """Returns the proper endpoint of a room.

    This will return the H323 IP endpoint, correctly formatted with the defined
    prefix if available or the room's Vidyo user name otherwise.
    """
    if endpoints['vc_endpoint_legacy_ip']:
        return '{prefix}{endpoints[vc_endpoint_legacy_ip]}'.format(prefix=RavemPlugin.settings.get('prefix'),
                                                                   endpoints=endpoints)
    else:
        return endpoints['vc_endpoint_vidyo_username']


def has_access(event_vc_room):
    """Returns whether the current session has access to the RAVEM button.

    To have access, the current user needs to be either the owner of the VC room
    or authorised to modify the event.
    If not the only way to have access is for the request to come from the
    terminal located in the room concerned.

    Note that if the room does not have equipment supported by Vidyo, the access
    will always be refused regardless of the user or the origin of the request.
    """
    link_object = event_vc_room.link_object

    if not link_object:
        return False

    room = link_object.rb_room
    vc_room = event_vc_room.vc_room
    event = event_vc_room.event
    current_user = session.avatar

    # No physical room or room is not Vidyo capable
    if not room or not room.has_equipment('Vidyo'):
        return False

    return any([
        current_user == retrieve_principal(vc_room.data.get('owner')),
        event.canModify(current_user),
        request.remote_addr == room.get_attribute_value('ip'),
    ])


class RavemException(Exception):
    pass


class RavemOperationException(RavemException):
    """Indicates an operation failed and the cause of the failure is known.

    Known causes of failure are for example if the room is already disconnected
    when trying to disconnect it.

    If this exception is raised, make sure to check the `reason` attribute.
    Functions raising this exception should document the possible reasons with
    which the exception can be raised.
    """
    def __init__(self, message, reason):
        super(RavemOperationException, self).__init__(message)
        self.message = message
        self.reason = reason


class RavemAPIException(RavemException):
    """Indicates the RAVEM API replied with an invalid response.

    In this context, by invalid response we mean a valid json response which
    does not match the excepted format of having a `error` or `result` key.
    """
    def __init__(self, message, endpoint, response):
        super(RavemAPIException, self).__init__(message)
        self.message = message
        self.endpoint = endpoint
        self.response = response