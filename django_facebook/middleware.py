# -*- coding: utf-8 -*-

from urlparse import urlparse

from django.contrib.auth import logout

from open_facebook.api import FacebookAuthorization, OpenFacebook

from django_facebook import settings
from django_facebook.canvas import generate_oauth_url
from django_facebook.connect import connect_user
from django_facebook.exceptions import MissingPermissionsError
from django_facebook.utils import ScriptRedirect, try_get_profile
from bongoregistration.models import FacebookUserProfile
from django.contrib import messages

import logging


logger = logging.getLogger(__name__)


class FacebookCanvasMiddleWare(object):

    def process_request(self, request):
        """
        This middleware authenticates the facebook user when
        he/she is accessing the app from facebook (not an internal page)
        The flow is show below:

        if referer is facebook:
            it's a canvas app and the first hit on the app
            If error:
                attempt to reauthenticate using authorization dialog
            if signed_request not sent or does not have the user_id and the access_token:
                user has not authorized app
                redirect to authorization dialog
            else:
                check permissions
                if user is authenticated (in django):
                    check if current facebook user is the same that is authenticated
                    if not: logout authenticated user
                if user is not authenticated:
                    connect_user (django_facebook.connect module)
                changed method to GET. Facebook always sends a POST first.
        else:
            It's an internal page.
            No signed_request is sent.
            Return
        """
        logger.info("PR01 process_request in django-facebook middleware")

        # This call cannot be global'ized or Django will return an empty response
        # after the first one
        redirect_login_oauth = ScriptRedirect(redirect_to=generate_oauth_url(mobile=request.mobile),
                                              show_body=False)
        # check referer to see if this is the first access
        # or it's part of navigation in app
        # facebook always sends a POST reuqest
        referer = request.META.get('HTTP_REFERER', None)
        if referer:
            logger.info("PR02 referrer %s" % referer)
            urlparsed = urlparse(referer)
            is_facebook = urlparsed.netloc.endswith('facebook.com')
            # facebook redirect
            if is_facebook and urlparsed.path.endswith('/l.php'):
                logger.info("PR03 is_facebook = True, but ends with /l.php")
                return
            if not is_facebook:
                return
            # when there is an error, we attempt to allow user to
            # reauthenticate
            if 'error' in request.GET:
                logger.info("PR05 errors in request.GET")
                return redirect_login_oauth
        else:
            return

        # get signed_request
        signed_request = request.POST.get('signed_request', None)
        try:
            # get signed_request
            parsed_signed_request = FacebookAuthorization.parse_signed_data(
                signed_request)
            access_token = parsed_signed_request['oauth_token']
            facebook_id = long(parsed_signed_request['user_id'])
            logger.info("PR07 facebook_id = %s" % facebook_id)
        except:
            logger.info("PR08 app is not authorized by user")
            # redirect to authorization dialog
            # if app not authorized by user
            return redirect_login_oauth
        # check for permissions
        try:
            graph = self.check_permissions(access_token)
            logger.info("PR09 got graph")
        except MissingPermissionsError:
            logger.info("PR010 no graph")
            return redirect_login_oauth
        # check if user authenticated and if it's the same
        if request.user.is_authenticated():
            logger.info("PR11 use is authenticated, user_id = %s" % request.user.id)
            if not self.check_django_facebook_user(request, facebook_id, access_token):
                logger.info("PR12 check django facebook user failed")
                return
        request.facebook = graph
        if not request.user.is_authenticated():
            logger.info("PR13 user is not authenticated")
            _action, _user = connect_user(request, access_token, graph)
        # override http method, since this actually is a GET
        if request.method == 'POST':
            logger.info("PR14 overwrite POST to GET")
            request.method = 'GET'
        return

    def check_permissions(self, access_token):
        logger.info("CHP01 check permissions access_token = %s" % access_token)
        graph = OpenFacebook(access_token)
        permissions = set(graph.permissions())
        scope_list = set(settings.FACEBOOK_DEFAULT_SCOPE)
        missing_perms = scope_list - permissions
        if missing_perms:
            permissions_string = ', '.join(missing_perms)
            error_format = 'Permissions Missing: %s'
            logger.info("CHP02 missed permissions: %s" % permissions_string)
            raise MissingPermissionsError(error_format % permissions_string)

        logger.info("CHP03 permissions OK")
        return graph

    def check_django_facebook_user(self, request, facebook_id, access_token):
        logger.info("CDFU01 Checking django facebook user...")
        try:
            current_user = try_get_profile(request.user)
            logger.info("CDFU02 got user profile %s" % current_user)
        except:
            logger.info("CDFU03 failed to get user profile")
            if request.user.is_authenticated():
                logger.info("CDFU04 user is authenticated user_id = %s" % request.user.id)
                if FacebookUserProfile.objects.filter(facebook_id=facebook_id).exists():
                    logger.info("CDFU05 FacebookUserProfile exists facebook_id = %s" % facebook_id)
                    messages.info(request, 'There is already an account on this site using that login')
                    request.session['facebook_share_not_allowed'] = True
                    return False
                else:
                    logger.info("CDFU06 create new FacebookUserProfile for user_id = %s" % request.user.id)
                    current_user = FacebookUserProfile.objects.create(user=request.user)
                    current_user.facebook_id = facebook_id
                    current_facebook_id = facebook_id
            else:
                logger.info("CDFU07 user is not authenticated")
                current_facebook_id = None
        else:
            current_facebook_id = current_user.facebook_id
            logger.info("CDFU08 current user is user with facebook_id = %s" % current_facebook_id)
        if not current_facebook_id or current_facebook_id != facebook_id:
            logger.info("CDFU09 Wrong or no facebook_id")
            logout(request)
            # clear possible caches
            if hasattr(request, 'facebook'):
                del request.facebook
                logger.info("CDFU10 Clear request facebook")
            if request.session.get('graph', None):
                del request.session['graph']
                logger.info("CDFU11 Clear graph in session")
        else:
            # save last access_token to make sure we always have the most
            # recent one
            current_user.access_token = access_token
            current_user.save()
            logger.info("CDFU12 Save last access_token")
