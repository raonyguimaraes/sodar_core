"""Tests for views in the userprofile Django app"""

from django.core.urlresolvers import reverse
from django.test import RequestFactory

from test_plus.test import TestCase

from projectroles.tests.test_models import EXAMPLE_APP_NAME, ProjectSettingMixin
from projectroles.user_settings import get_user_setting


class TestViewsBase(TestCase):
    """Base class for view testing"""

    def setUp(self):
        self.req_factory = RequestFactory()

        # Init superuser
        self.user = self.make_user('superuser')
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()


# View tests -------------------------------------------------------------------


class TestUserDetailView(TestViewsBase):
    """Tests for the user profile detail view"""

    def test_render(self):
        """Test to ensure the user profile detail view renders correctly"""
        with self.login(self.user):
            response = self.client.get(reverse('userprofile:detail'))
        self.assertEqual(response.status_code, 200)

        self.assertIsNotNone(response.context['user_settings'])


class TestUserSettingsForm(ProjectSettingMixin, TestViewsBase):
    """Tests for the user settings form."""

    # NOTE: This assumes an example app is available
    def setUp(self):
        # Init user & role
        self.user = self.make_user('owner')

        # Init test setting
        self.setting_str = self._make_setting(
            app_name=EXAMPLE_APP_NAME,
            name='str_setting',
            setting_type='STRING',
            value='test',
            user=self.user,
        )

        # Init integer setting
        self.setting_int = self._make_setting(
            app_name=EXAMPLE_APP_NAME,
            name='int_setting',
            setting_type='INTEGER',
            value=170,
            user=self.user,
        )

        # Init boolean setting
        self.setting_bool = self._make_setting(
            app_name=EXAMPLE_APP_NAME,
            name='bool_setting',
            setting_type='BOOLEAN',
            value=True,
            user=self.user,
        )

    def testGet(self):
        with self.login(self.user):
            response = self.client.get(reverse('userprofile:update-settings'))
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context['form'])
        self.assertIsNotNone(
            response.context['form'].fields.get(
                'settings.%s.str_setting' % EXAMPLE_APP_NAME
            )
        )
        self.assertIsNotNone(
            response.context['form'].fields.get(
                'settings.%s.int_setting' % EXAMPLE_APP_NAME
            )
        )
        self.assertIsNotNone(
            response.context['form'].fields.get(
                'settings.%s.bool_setting' % EXAMPLE_APP_NAME
            )
        )

    def testPost(self):
        self.assertEqual(
            get_user_setting(self.user, EXAMPLE_APP_NAME, 'str_setting'), 'test'
        )
        self.assertEqual(
            get_user_setting(self.user, EXAMPLE_APP_NAME, 'int_setting'), 170
        )
        self.assertEqual(
            get_user_setting(self.user, EXAMPLE_APP_NAME, 'bool_setting'), True
        )

        values = {
            'settings.%s.str_setting' % EXAMPLE_APP_NAME: 'another-text',
            'settings.%s.int_setting' % EXAMPLE_APP_NAME: '123',
            'settings.%s.bool_setting' % EXAMPLE_APP_NAME: False,
        }

        with self.login(self.user):
            response = self.client.post(
                reverse('userprofile:update-settings'), values
            )

        # Assert redirect
        with self.login(self.user):
            self.assertRedirects(response, reverse('userprofile:detail'))

        # Assert settings state after update
        self.assertEqual(
            get_user_setting(self.user, EXAMPLE_APP_NAME, 'str_setting'),
            'another-text',
        )
        self.assertEqual(
            get_user_setting(self.user, EXAMPLE_APP_NAME, 'int_setting'), 123
        )
        self.assertEqual(
            get_user_setting(self.user, EXAMPLE_APP_NAME, 'bool_setting'), False
        )
