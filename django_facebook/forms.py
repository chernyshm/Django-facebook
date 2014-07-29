"""
Forms and validation code for user registration.

"""

from django import forms
from django.utils.translation import ugettext_lazy as _

from django.contrib.auth import get_user_model

attrs_dict = {'class': 'required'}


class FacebookRegistrationFormUniqueEmail(forms.Form):

    """
    Some basic validation, adapted from django registration
    """
    email = forms.EmailField(widget=forms.TextInput(attrs=dict(attrs_dict,
                                                               maxlength=75)),
                             label=_("Email address"))

    def clean_email(self):
        """
        Check if email is unique
        """
        email = self.cleaned_data['email']
        all_users = get_user_model().objects.filter(email=email)
        if all_users:
            raise forms.ValidationError(_("That email is already linked to your client account, please use another"))
        return email
