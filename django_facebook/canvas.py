from django.http import QueryDict
from django_facebook import settings as facebook_settings


def generate_oauth_url(scope=facebook_settings.FACEBOOK_DEFAULT_SCOPE,
                       next=None, mobile=False, extra_data=None):
    query_dict = QueryDict('', True)
    canvas_page = facebook_settings.FACEBOOK_CANVAS_PAGE
    if next is not None:
        canvas_page = next
    elif mobile:
        canvas_page = facebook_settings.FACEBOOK_MOBILE_PAGE
    query_dict.update(dict(client_id=facebook_settings.FACEBOOK_APP_ID,
                           redirect_uri=canvas_page,
                           scope=','.join(scope)))
    if extra_data:
        query_dict.update(extra_data)
    auth_url = 'https://www.facebook.com/dialog/oauth?%s' % (
        query_dict.urlencode(), )
    return auth_url
