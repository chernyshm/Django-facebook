from django.contrib.auth import backends
from django.db.models.query_utils import Q
from django.db.utils import DatabaseError
from django_facebook import settings as facebook_settings
from django_facebook.utils import get_profile_model, is_user_attribute, \
    get_user_model, try_get_profile
import operator

logger = logging.getLogger(__name__)


class FacebookBackend(backends.ModelBackend):

    '''
    Django Facebook authentication backend

    This backend hides the difference between authenticating with
    - a django 1.5 custom user model
    - profile models, which were used prior to 1.5

    **Example usage**

    >>> FacebookBackend().authenticate(facebook_id=myid)

    '''

    def authenticate(self, *args, **kwargs):
        '''
        Route to either the user or profile table depending on which type of user
        customization we are using
        (profile was used in Django < 1.5, user is the new way in 1.5 and up)
        '''
        logger.info("A01 Inside Authenticate function")
        user_attribute = is_user_attribute('facebook_id')
        if user_attribute:
            logger.info("A02 user attribute %s" % user_attribute)
            user = self.user_authenticate(*args, **kwargs)
            logger.info("A03 User authentication %s" % user)
        else:
            user = self.profile_authenticate(*args, **kwargs)
            logger.info("A04 Profile authentication %s" % user)
        return user

    def user_authenticate(self, facebook_id=None, facebook_email=None):
        '''
        Authenticate the facebook user by id OR facebook_email
        We filter using an OR to allow existing members to connect with
        their facebook ID using email.

        This decorator works with django's custom user model

        :param facebook_id:
            Optional string representing the facebook id.
        :param facebook_email:
            Optional string with the facebook email.

        :return: The signed in :class:`User`.
        '''
        logger.info("UA01 Inside User Authenticate function")
        user_model = get_user_model()
        logger.info("UA02 User model %s" % user_model)
        if facebook_id or facebook_email:
            # match by facebook id or email
            auth_conditions = []
            if facebook_id:
                logger.info("UA03 facebook id %s" % facebook_id)
                auth_conditions.append(Q(facebook_id=facebook_id))
            if facebook_email:
                logger.info("UA04 facebook email %s" % facebook_email)
                auth_conditions.append(Q(email__iexact=facebook_email))
            # or the operations
            auth_condition = reduce(operator.or_, auth_conditions)
            logger.info("UA05 Auth conditions %s" % auth_condition)

            # get the users in one query
            users = list(user_model.objects.filter(auth_condition))
            logger.info("UA06 Users from query %s" % users)

            # id matches vs email matches
            id_matches = [u for u in users if u.facebook_id == facebook_id]
            email_matches = [u for u in users if u.facebook_id != facebook_id]
            logger.info("UA07 Id matches %s" % id_matches)
            logger.info("UA08 email model %s" % email_matches)

            # error checking
            if len(id_matches) > 1:
                raise ValueError(
                    'found multiple facebook id matches. this shouldnt be allowed, check your unique constraints. users found %s' % users)

            # give the right user
            user = None
            if id_matches:
                user = id_matches[0]
                logger.info("UA09 User matches from id %s" % user)
            elif email_matches:
                user = email_matches[0]
                logger.info("UA09 User matches from email %s" % user)

            if user and facebook_settings.FACEBOOK_FORCE_PROFILE_UPDATE_ON_LOGIN:
                logger.info("UA10 Require user update")
                user.fb_update_required = True
            return user

    def profile_authenticate(self, facebook_id=None, facebook_email=None):
        '''
        Authenticate the facebook user by id OR facebook_email
        We filter using an OR to allow existing members to connect with
        their facebook ID using email.

        :param facebook_id:
            Optional string representing the facebook id

        :param facebook_email:
            Optional string with the facebook email

        :return: The signed in :class:`User`.
        '''
        logger.info("PA01 Inside profile authentication")
        if facebook_id or facebook_email:
            profile_class = get_profile_model()
            logger.info("PA02 Profile class %s" % profile_class)
            profile_query = profile_class.objects.all().order_by('user')
            profile_query = profile_query.select_related('user')
            logger.info("PA03 Profile query %s" % profile_query)
            profile = None

            # filter on email or facebook id, two queries for better
            # queryplan with large data sets
            if facebook_id:
                profiles = profile_query.filter(facebook_id=facebook_id)[:1]
                logger.info("PA04 Profiles from facebook_id %s" % profiles)
                profile = profiles[0] if profiles else None
                logger.info("PA05 Profile %s" % profile)
            if profile is None and facebook_email:
                try:
                    profiles = profile_query.filter(
                        user__email__iexact=facebook_email)[:1]
                    logger.info("PA06 Profiles from email %s" % profiles)
                    profile = profiles[0] if profiles else None
                    logger.info("PA07 Profile %s" % profile)
                except DatabaseError:
                    logger.info("PA08 Database error")
                    try:
                        user = get_user_model(
                        ).objects.get(email=facebook_email)
                        logger.info("PA09 User from model %s" % user)
                    except get_user_model().DoesNotExist:
                        logger.info("PA10 No model")
                        user = None
                    profile = try_get_profile(user) if user else None
                    logger.info("PA11 Profile %s" % profile)

            if profile:
                # populate the profile cache while we're getting it anyway
                user = profile.user
                logger.info("PA07 User from profile %s" % user)
                user._profile = profile
                if facebook_settings.FACEBOOK_FORCE_PROFILE_UPDATE_ON_LOGIN:
                    logger.info("UA10 Require user update")
                    user.fb_update_required = True
                return user
