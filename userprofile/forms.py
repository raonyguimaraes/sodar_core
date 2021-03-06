import json

from django import forms

# Projectroles dependency
from projectroles.app_settings import AppSettingAPI
from projectroles.forms import SODARForm
from projectroles.models import APP_SETTING_VAL_MAXLENGTH, SODAR_CONSTANTS
from projectroles.plugins import get_active_plugins


# SODAR Constants
APP_SETTING_SCOPE_USER = SODAR_CONSTANTS['APP_SETTING_SCOPE_USER']


# App settings API
app_settings = AppSettingAPI()


# User Settings Form -----------------------------------------------------------


class UserSettingsForm(SODARForm):
    """The form for configuring user settings."""

    def __init__(self, *args, **kwargs):
        #: The user to display the settings for.
        self.user = kwargs.pop('current_user')

        super().__init__(*args, **kwargs)

        # Add settings fields
        self.app_plugins = get_active_plugins(plugin_type='project_app')
        self.user_plugins = get_active_plugins(plugin_type='site_app')
        self.app_plugins = self.app_plugins + self.user_plugins

        for plugin in self.app_plugins:
            p_settings = app_settings.get_setting_defs(
                APP_SETTING_SCOPE_USER, plugin=plugin, user_modifiable=True
            )

            for s_key, s_val in p_settings.items():
                s_field = 'settings.{}.{}'.format(plugin.name, s_key)
                s_widget_attrs = s_val.get('widget_attrs') or {}
                s_widget_attrs['placeholder'] = s_val.get('placeholder')
                setting_kwargs = {
                    'required': False,
                    'label': s_val.get('label')
                    or '{}.{}'.format(plugin.name, s_key),
                    'help_text': s_val.get('description'),
                }

                if s_val['type'] == 'STRING':
                    self.fields[s_field] = forms.CharField(
                        max_length=APP_SETTING_VAL_MAXLENGTH, **setting_kwargs
                    )

                elif s_val['type'] == 'INTEGER':
                    self.fields[s_field] = forms.IntegerField(**setting_kwargs)

                elif s_val['type'] == 'BOOLEAN':
                    self.fields[s_field] = forms.BooleanField(**setting_kwargs)

                elif s_val['type'] == 'JSON':
                    # NOTE: Attrs MUST be supplied here (#404)
                    if 'class' in s_widget_attrs:
                        s_widget_attrs['class'] += ' sodar-json-input'

                    else:
                        s_widget_attrs['class'] = 'sodar-json-input'

                    self.fields[s_field] = forms.CharField(
                        widget=forms.Textarea(attrs=s_widget_attrs),
                        **setting_kwargs,
                    )

                # Modify initial value and attributes
                if s_val['type'] != 'JSON':
                    # Add optional attributes from plugin (#404)
                    # NOTE: Experimental! Use at your own risk!
                    self.fields[s_field].widget.attrs.update(s_widget_attrs)

                    self.initial[s_field] = app_settings.get_app_setting(
                        app_name=plugin.name, setting_name=s_key, user=self.user
                    )

                else:
                    self.initial[s_field] = json.dumps(
                        app_settings.get_app_setting(
                            app_name=plugin.name,
                            setting_name=s_key,
                            user=self.user,
                        )
                    )

    def clean(self):
        """Function for custom form validation and cleanup"""

        for plugin in self.app_plugins:
            p_settings = app_settings.get_setting_defs(
                APP_SETTING_SCOPE_USER, plugin=plugin, user_modifiable=True
            )

            for s_key, s_val in p_settings.items():
                s_field = 'settings.{}.{}'.format(plugin.name, s_key)
                if s_val['type'] == 'JSON':
                    try:
                        self.cleaned_data[s_field] = json.loads(
                            self.cleaned_data.get(s_field)
                        )
                    except json.JSONDecodeError as err:
                        # TODO: Shouldn't we use add_error() instead?
                        raise forms.ValidationError(
                            'Couldn\'t encode JSON\n' + str(err)
                        )

                if not app_settings.validate_setting(
                    setting_type=s_val['type'],
                    setting_value=self.cleaned_data.get(s_field),
                ):
                    self.add_error(s_field, 'Invalid value')

        return self.cleaned_data
