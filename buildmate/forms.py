from allauth.account.forms import SignupForm


class CustomSignupForm(SignupForm):
    """Custom signup form that removes the email field.

    Use this when you don't want to collect email addresses at signup.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove email field if present so templates rendering the form
        # (e.g. modal or page) won't show it.
        self.fields.pop('email', None)
