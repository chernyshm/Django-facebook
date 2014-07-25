from django.conf import settings
from django.contrib import messages
from django.http import Http404
from django.shortcuts import render_to_response
from django.template.context import RequestContext
from django.utils.translation import ugettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_facebook import exceptions as facebook_exceptions, \
    settings as facebook_settings
from django_facebook.connect import CONNECT_ACTIONS, connect_user
from django_facebook.decorators import facebook_required_lazy
from django_facebook.utils import next_redirect, get_registration_backend, \
    to_bool, error_next_redirect, get_instance_for, try_get_profile
from open_facebook import exceptions as open_facebook_exceptions
from open_facebook.utils import send_warning
import logging

from bongolanding.utils import get_layout

logger = logging.getLogger(__name__)


@csrf_exempt
@facebook_required_lazy
def connect(request, graph):
    '''
    Exception and validation functionality around the _connect view
    Separated this out from _connect to preserve readability
    Don't bother reading this code, skip to _connect for the bit you're interested in :)
    '''
    backend = get_registration_backend()
    context = RequestContext(request)

    # validation to ensure the context processor is enabled
    if not context.get('FACEBOOK_APP_ID'):
        message = 'Please specify a Facebook app id and ensure the context processor is enabled'
        logger.info('CO01 Please specify a Facebook app id and ensure the context processor is enabled')
        raise ValueError(message)

    if 'campaign_id' in request.GET:
        request.session['share_campaign_id'] = request.GET['campaign_id']
    try:
        response = _connect(request, graph)
    except open_facebook_exceptions.FacebookUnreachable, e:
        logger.info('CO02 Probably slow FB')
        # often triggered when Facebook is slow
        warning_format = u'%s, often caused by Facebook slowdown, error %s'
        warn_message = warning_format % (type(e), e.message)
        send_warning(warn_message, e=e)
        additional_params = dict(fb_error_or_cancel=1)
        response = backend.post_error(request, additional_params)

    return response


def _connect(request, graph):
    '''
    Handles the view logic around connect user
    - (if authenticated) connect the user
    - login
    - register

    We are already covered by the facebook_required_lazy decorator
    So we know we either have a graph and permissions, or the user denied
    the oAuth dialog
    '''
    backend = get_registration_backend()
    context = RequestContext(request)
    connect_facebook = to_bool(request.REQUEST.get('connect_facebook'))

    logger.info('C01: trying to connect using Facebook')
    if graph:
        logger.info('C02: found a graph object')
        converter = get_instance_for('user_conversion', graph)
        authenticated = converter.is_authenticated()
        # Defensive programming :)
        if not authenticated:
            logger.info('C04: not authenticated')
            raise ValueError('didnt expect this flow')

        logger.info('C05: Facebook is authenticated')
        facebook_data = converter.facebook_profile_data()
        # either, login register or connect the user
        try:
            action, user = connect_user(
                request, connect_facebook=connect_facebook)
            logger.info('Django facebook performed action: %s', action)
        except facebook_exceptions.IncompleteProfileError, e:
            # show them a registration form to add additional data
            warning_format = u'Incomplete profile data encountered with error %s'
            warn_message = warning_format % unicode(e)
            logger.info(warn_message)
            send_warning(warn_message, e=e,
                         facebook_data=facebook_data)

            context['facebook_mode'] = True
            context['blocked_email'] = e.form.data['email']
            e.form.data['email'] = u''
            context['form'] = e.form
            # Style register page
            layout = get_layout(request=request)
            logger.info('C06: Got layout %s' % layout)
            context['layout'] = layout
            return render_to_response(
                backend.get_registration_template(),
                context_instance=context,
            )
        except facebook_exceptions.AlreadyConnectedError, e:
            logger.info('Already connected error')
            user_ids = [u.get_user_id() for u in e.users]
            ids_string = ','.join(map(str, user_ids))
            additional_params = dict(already_connected=ids_string)
            return backend.post_error(request, additional_params)
        if 'campaign_id' in request.GET:
            try:
                user.userprofile.extra_data['last_campaign_id'] = request.GET['campaign_id']
            except:
                pass

        response = backend.post_connect(request, user, action)

        if action is CONNECT_ACTIONS.LOGIN:
            pass
        elif action is CONNECT_ACTIONS.CONNECT:
            # connect means an existing account was attached to facebook
            logger.info("You have connected your account to %s's facebook profile" % facebook_data['name'])
            messages.info(request, _("You have connected your account "
                                     "to %s's facebook profile") % facebook_data['name'])
        elif action is CONNECT_ACTIONS.REGISTER:
            # hook for tying in specific post registration functionality
            response.set_cookie('fresh_registration', user.id)
    else:
        # the user denied the request
        logger.info("User denied request")
        additional_params = dict(fb_error_or_cancel='1')
        response = backend.post_error(request, additional_params)

    return response


def disconnect(request):
    '''
    Removes Facebook from the users profile
    And redirects to the specified next page
    '''
    if request.method == 'POST':
        logger.info("You have disconnected your Facebook profile.")
        messages.info(
            request, _("You have disconnected your Facebook profile."))
        profile = try_get_profile(request.user)
        profile.disconnect_facebook()
        profile.save()
    response = next_redirect(request)
    return response


def example(request):
    context = RequestContext(request)
    return render_to_response('django_facebook/example.html', context)
