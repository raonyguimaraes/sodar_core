"""REST API view tests for the projectroles app"""
import base64
import json
import pytz

from django.conf import settings
from django.forms.models import model_to_dict
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from knox.models import AuthToken

from test_plus.test import APITestCase

from projectroles import views_api
from projectroles.models import Project, Role, RoleAssignment, SODAR_CONSTANTS
from projectroles.plugins import change_plugin_status, get_backend_api
from projectroles.remote_projects import RemoteProjectAPI
from projectroles.tests.test_models import (
    ProjectMixin,
    RoleAssignmentMixin,
    RemoteSiteMixin,
    RemoteProjectMixin,
)
from projectroles.tests.test_views import (
    TestViewsBase,
    PROJECT_TYPE_CATEGORY,
    PROJECT_TYPE_PROJECT,
    PROJECT_ROLE_OWNER,
    PROJECT_ROLE_DELEGATE,
    PROJECT_ROLE_CONTRIBUTOR,
    PROJECT_ROLE_GUEST,
    REMOTE_SITE_NAME,
    REMOTE_SITE_URL,
    SITE_MODE_SOURCE,
    SITE_MODE_TARGET,
    REMOTE_SITE_DESC,
    REMOTE_SITE_SECRET,
)
from projectroles.utils import build_secret


CORE_API_MEDIA_TYPE_INVALID = 'application/vnd.bihealth.invalid'
CORE_API_VERSION_INVALID = '9.9.9'

INVALID_UUID = '11111111-1111-1111-1111-111111111111'
NEW_CATEGORY_TITLE = 'New Category'
NEW_PROJECT_TITLE = 'New Project'
UPDATED_TITLE = 'Updated Title'
UPDATED_DESC = 'Updated description'
UPDATED_README = 'Updated readme'


# Base Classes -----------------------------------------------------------------


class SODARAPIViewTestMixin:
    """
    Mixin for SODAR and SODAR Core API views with accept headers, knox token
    authorization and general helper methods.
    """

    # Default API header parameters are for external SODAR site APIs
    # Override these for testing SODAR Core API views
    media_type = settings.SODAR_API_MEDIA_TYPE
    api_version = settings.SODAR_API_DEFAULT_VERSION

    # Copied from Knox tests
    @classmethod
    def _get_basic_auth_header(cls, username, password):
        return (
            'Basic %s'
            % base64.b64encode(
                ('%s:%s' % (username, password)).encode('ascii')
            ).decode()
        )

    @classmethod
    def get_token(cls, user, full_result=False):
        """
        Get or create a knox token for a user.

        :param user: User object
        :param full_result: Return full result of AuthToken creation if True
        :return: Token string or AuthToken creation tuple
        """
        result = AuthToken.objects.create(user=user)
        return result if full_result else result[1]

    @classmethod
    def get_serialized_user(cls, user):
        """
        Return serialization for a user.

        :param user: User object
        :return: Dict
        """
        return {
            'email': user.email,
            'name': user.name,
            'sodar_uuid': str(user.sodar_uuid),
            'username': user.username,
        }

    @classmethod
    def get_drf_datetime(cls, obj_dt):
        """
        Return datetime in DRF compatible format.

        :param obj_dt: Object DateTime field
        :return: String
        """
        return timezone.localtime(
            obj_dt, pytz.timezone(settings.TIME_ZONE)
        ).isoformat()

    @classmethod
    def get_accept_header(
        cls, media_type=None, version=None,
    ):
        """
        Return version accept header based on the media type and version string.

        :param media_type: String (default = cls.media_type)
        :param version: String (default = cls.api_version)
        :return: Dict
        """
        if not media_type:
            media_type = cls.media_type

        if not version:
            version = cls.api_version

        return {'HTTP_ACCEPT': '{}; version={}'.format(media_type, version)}

    @classmethod
    def get_token_header(cls, token):
        """
        Return auth header based on token.

        :param token: Token string
        :return: Dict
        """
        return {'HTTP_AUTHORIZATION': 'token {}'.format(token)}

    def request_knox(
        self,
        url,
        method='GET',
        format='json',
        data=None,
        token=None,
        media_type=None,
        version=None,
    ):
        """
        Perform a HTTP request with Knox token auth.

        :param url: URL for the request
        :param method: Request method (string, default="GET")
        :param format: Request format (string, default="json")
        :param data: Optional data for request (dict)
        :param token: Knox token string (if None, use self.knox_token)
        :param media_type: String (default = cls.media_type)
        :param version: String (default = cls.api_version)
        :return: Response object
        """
        if not token:
            token = self.knox_token

        req_kwargs = {
            'format': format,
            **self.get_accept_header(media_type, version),
            **self.get_token_header(token),
        }

        if data:
            req_kwargs['data'] = data

        req_method = getattr(self.client, method.lower(), None)

        if not req_method:
            raise ValueError('Unsupported method "{}"'.format(method))

        return req_method(url, **req_kwargs)


class TestAPIViewsBase(
    ProjectMixin, RoleAssignmentMixin, SODARAPIViewTestMixin, APITestCase
):
    """Base API test view with knox authentication"""

    def setUp(self):
        # Force disabling of taskflow plugin if it's available
        if get_backend_api('taskflow'):
            change_plugin_status(
                name='taskflow', status=1, plugin_type='backend'  # 0 = Disabled
            )

        # Init roles
        self.role_owner = Role.objects.get_or_create(name=PROJECT_ROLE_OWNER)[0]
        self.role_delegate = Role.objects.get_or_create(
            name=PROJECT_ROLE_DELEGATE
        )[0]
        self.role_contributor = Role.objects.get_or_create(
            name=PROJECT_ROLE_CONTRIBUTOR
        )[0]
        self.role_guest = Role.objects.get_or_create(name=PROJECT_ROLE_GUEST)[0]

        # Init superuser
        self.user = self.make_user('superuser')
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()

        # Set up category and project with owner role assignments
        self.category = self._make_project(
            'TestCategory', PROJECT_TYPE_CATEGORY, None
        )
        self.cat_owner_as = self._make_assignment(
            self.category, self.user, self.role_owner
        )
        self.project = self._make_project(
            'TestProject', PROJECT_TYPE_PROJECT, self.category
        )
        self.owner_as = self._make_assignment(
            self.project, self.user, self.role_owner
        )

        # Get knox token for self.user
        self.knox_token = self.get_token(self.user)


class TestCoreAPIViewsBase(TestAPIViewsBase):
    """Override of TestAPIViewsBase to be used with SODAR Core API views"""

    media_type = views_api.CORE_API_MEDIA_TYPE
    api_version = views_api.CORE_API_DEFAULT_VERSION


# Tests ------------------------------------------------------------------------


class TestProjectListAPIView(TestCoreAPIViewsBase):
    """Tests for ProjectListAPIView"""

    def test_get(self):
        """Test ProjectListAPIView get() as project owner"""
        url = reverse('projectroles:api_project_list')
        response = self.request_knox(url)

        # Assert response
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(len(response_data), 2)
        expected = [
            {
                'title': self.category.title,
                'type': self.category.type,
                'parent': None,
                'description': self.category.description,
                'readme': '',
                'submit_status': self.category.submit_status,
                'roles': {
                    str(self.cat_owner_as.sodar_uuid): {
                        'user': {
                            'username': self.user.username,
                            'name': self.user.name,
                            'email': self.user.email,
                            'sodar_uuid': str(self.user.sodar_uuid),
                        },
                        'role': PROJECT_ROLE_OWNER,
                    }
                },
                'sodar_uuid': str(self.category.sodar_uuid),
            },
            {
                'title': self.project.title,
                'type': self.project.type,
                'parent': str(self.category.sodar_uuid),
                'description': self.project.description,
                'readme': '',
                'submit_status': self.project.submit_status,
                'roles': {
                    str(self.owner_as.sodar_uuid): {
                        'user': {
                            'username': self.user.username,
                            'name': self.user.name,
                            'email': self.user.email,
                            'sodar_uuid': str(self.user.sodar_uuid),
                        },
                        'role': PROJECT_ROLE_OWNER,
                    }
                },
                'sodar_uuid': str(self.project.sodar_uuid),
            },
        ]
        self.assertEqual(response_data, expected)

    def test_get_no_roles(self):
        """Test ProjectListAPIView get() without roles"""
        user_no_roles = self.make_user('user_no_roles')
        url = reverse('projectroles:api_project_list')
        response = self.request_knox(url, token=self.get_token(user_no_roles))

        # Assert response
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(len(response_data), 0)

    def test_get_limited_roles(self):
        """Test ProjectListAPIView get() with only one role"""
        user_no_roles = self.make_user('user_no_roles')
        self._make_assignment(
            self.project, user_no_roles, self.role_contributor
        )
        url = reverse('projectroles:api_project_list')
        response = self.request_knox(url, token=self.get_token(user_no_roles))

        # Assert response
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(len(response_data), 1)


class TestProjectRetrieveAPIView(TestCoreAPIViewsBase):
    """Tests for ProjectRetrieveAPIView"""

    def test_get_category(self):
        """Test ProjectRetrieveAPIView get() with a category"""
        url = reverse(
            'projectroles:api_project_retrieve',
            kwargs={'project': self.category.sodar_uuid},
        )
        response = self.request_knox(url)

        # Assert response
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        expected = {
            'title': self.category.title,
            'type': self.category.type,
            'parent': None,
            'description': self.category.description,
            'readme': '',
            'submit_status': self.category.submit_status,
            'roles': {
                str(self.cat_owner_as.sodar_uuid): {
                    'user': {
                        'username': self.user.username,
                        'name': self.user.name,
                        'email': self.user.email,
                        'sodar_uuid': str(self.user.sodar_uuid),
                    },
                    'role': PROJECT_ROLE_OWNER,
                }
            },
            'sodar_uuid': str(self.category.sodar_uuid),
        }
        self.assertEqual(response_data, expected)

    def test_get_project(self):
        """Test ProjectRetrieveAPIView get() with a project"""
        url = reverse(
            'projectroles:api_project_retrieve',
            kwargs={'project': self.project.sodar_uuid},
        )
        response = self.request_knox(url)

        # Assert response
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        expected = {
            'title': self.project.title,
            'type': self.project.type,
            'parent': str(self.category.sodar_uuid),
            'description': self.project.description,
            'readme': '',
            'submit_status': self.project.submit_status,
            'roles': {
                str(self.owner_as.sodar_uuid): {
                    'user': {
                        'username': self.user.username,
                        'name': self.user.name,
                        'email': self.user.email,
                        'sodar_uuid': str(self.user.sodar_uuid),
                    },
                    'role': PROJECT_ROLE_OWNER,
                }
            },
            'sodar_uuid': str(self.project.sodar_uuid),
        }
        self.assertEqual(response_data, expected)


class TestProjectCreateAPIView(TestCoreAPIViewsBase):
    """Tests for ProjectCreateAPIView"""

    def test_create_category(self):
        """Test creating a root category"""

        # Assert preconditions
        self.assertEqual(Project.objects.count(), 2)

        url = reverse('projectroles:api_project_create')
        post_data = {
            'title': NEW_CATEGORY_TITLE,
            'type': PROJECT_TYPE_CATEGORY,
            'parent': '',
            'description': 'description',
            'readme': 'readme',
            'owner': str(self.user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 201, msg=response.content)
        self.assertEqual(Project.objects.count(), 3)

        # Assert object content
        new_category = Project.objects.get(title=NEW_CATEGORY_TITLE)
        model_dict = model_to_dict(new_category)
        model_dict['readme'] = model_dict['readme'].raw
        expected = {
            'id': new_category.pk,
            'title': new_category.title,
            'type': new_category.type,
            'parent': None,
            'description': new_category.description,
            'readme': new_category.readme.raw,
            'submit_status': SODAR_CONSTANTS['SUBMIT_STATUS_OK'],
            'sodar_uuid': new_category.sodar_uuid,
        }
        self.assertEqual(model_dict, expected)

        # Assert role assignment
        self.assertEqual(
            RoleAssignment.objects.filter(
                project=new_category, user=self.user, role=self.role_owner
            ).count(),
            1,
        )

        # Assert API response
        expected = {
            'title': NEW_CATEGORY_TITLE,
            'type': PROJECT_TYPE_CATEGORY,
            'parent': None,
            'description': new_category.description,
            'readme': new_category.readme.raw,
            'sodar_uuid': str(new_category.sodar_uuid),
        }
        self.assertEqual(json.loads(response.content), expected)

    def test_create_category_nested(self):
        """Test creating a category under an existing category"""

        # Assert preconditions
        self.assertEqual(Project.objects.count(), 2)

        url = reverse('projectroles:api_project_create')
        post_data = {
            'title': NEW_CATEGORY_TITLE,
            'type': PROJECT_TYPE_CATEGORY,
            'parent': str(self.category.sodar_uuid),
            'description': 'description',
            'readme': 'readme',
            'owner': str(self.user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 201, msg=response.content)
        self.assertEqual(Project.objects.count(), 3)

        # Assert object content
        new_category = Project.objects.get(title=NEW_CATEGORY_TITLE)
        model_dict = model_to_dict(new_category)
        model_dict['readme'] = model_dict['readme'].raw
        expected = {
            'id': new_category.pk,
            'title': new_category.title,
            'type': new_category.type,
            'parent': self.category.pk,
            'description': new_category.description,
            'readme': new_category.readme.raw,
            'submit_status': SODAR_CONSTANTS['SUBMIT_STATUS_OK'],
            'sodar_uuid': new_category.sodar_uuid,
        }
        self.assertEqual(model_dict, expected)

        # Assert role assignment
        self.assertEqual(
            RoleAssignment.objects.filter(
                project=new_category, user=self.user, role=self.role_owner
            ).count(),
            1,
        )

        # Assert API response
        expected = {
            'title': NEW_CATEGORY_TITLE,
            'type': PROJECT_TYPE_CATEGORY,
            'parent': str(self.category.sodar_uuid),
            'description': new_category.description,
            'readme': new_category.readme.raw,
            'sodar_uuid': str(new_category.sodar_uuid),
        }
        self.assertEqual(json.loads(response.content), expected)

    def test_create_project(self):
        """Test creating a project under an existing category"""

        # Assert preconditions
        self.assertEqual(Project.objects.count(), 2)

        url = reverse('projectroles:api_project_create')
        post_data = {
            'title': NEW_PROJECT_TITLE,
            'type': PROJECT_TYPE_PROJECT,
            'parent': str(self.category.sodar_uuid),
            'description': 'description',
            'readme': 'readme',
            'owner': str(self.user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 201, msg=response.content)
        self.assertEqual(Project.objects.count(), 3)

        # Assert object content
        new_project = Project.objects.get(title=NEW_PROJECT_TITLE)
        model_dict = model_to_dict(new_project)
        model_dict['readme'] = model_dict['readme'].raw
        expected = {
            'id': new_project.pk,
            'title': new_project.title,
            'type': new_project.type,
            'parent': self.category.pk,
            'description': new_project.description,
            'readme': new_project.readme.raw,
            'submit_status': SODAR_CONSTANTS['SUBMIT_STATUS_OK'],
            'sodar_uuid': new_project.sodar_uuid,
        }
        self.assertEqual(model_dict, expected)

        # Assert role assignment
        self.assertEqual(
            RoleAssignment.objects.filter(
                project=new_project, user=self.user, role=self.role_owner
            ).count(),
            1,
        )

        # Assert API response
        expected = {
            'title': NEW_PROJECT_TITLE,
            'type': PROJECT_TYPE_PROJECT,
            'parent': str(self.category.sodar_uuid),
            'description': new_project.description,
            'readme': new_project.readme.raw,
            'sodar_uuid': str(new_project.sodar_uuid),
        }
        self.assertEqual(json.loads(response.content), expected)

    def test_create_project_root(self):
        """Test creating a project in root (should fail)"""

        # Assert preconditions
        self.assertEqual(Project.objects.count(), 2)

        url = reverse('projectroles:api_project_create')
        post_data = {
            'title': NEW_PROJECT_TITLE,
            'type': PROJECT_TYPE_PROJECT,
            'parent': None,
            'description': 'description',
            'readme': 'readme',
            'owner': str(self.user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Project.objects.count(), 2)

    @override_settings(PROJECTROLES_DISABLE_CATEGORIES=True)
    def test_create_project_disable_categories(self):
        """Test creating a project in root with disabled categories"""

        # Assert preconditions
        self.assertEqual(Project.objects.count(), 2)

        url = reverse('projectroles:api_project_create')
        post_data = {
            'title': NEW_PROJECT_TITLE,
            'type': PROJECT_TYPE_PROJECT,
            'parent': '',
            'description': 'description',
            'readme': 'readme',
            'owner': str(self.user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 201, msg=response.content)
        self.assertEqual(Project.objects.count(), 3)

    def test_create_project_duplicate_title(self):
        """Test creating a project with a title already in category (should fail)"""

        # Assert preconditions
        self.assertEqual(Project.objects.count(), 2)

        url = reverse('projectroles:api_project_create')
        post_data = {
            'title': self.project.title,
            'type': PROJECT_TYPE_PROJECT,
            'parent': str(self.category.sodar_uuid),
            'description': 'description',
            'readme': 'readme',
            'owner': str(self.user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Project.objects.count(), 2)

    def test_create_project_unknown_user(self):
        """Test creating a project with a non-existent user (should fail)"""

        # Assert preconditions
        self.assertEqual(Project.objects.count(), 2)

        url = reverse('projectroles:api_project_create')
        post_data = {
            'title': NEW_PROJECT_TITLE,
            'type': PROJECT_TYPE_PROJECT,
            'parent': str(self.category.sodar_uuid),
            'description': 'description',
            'readme': 'readme',
            'owner': INVALID_UUID,
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Project.objects.count(), 2)

    def test_create_project_unknown_parent(self):
        """Test creating a project with a non-existent parent category (should fail)"""

        # Assert preconditions
        self.assertEqual(Project.objects.count(), 2)

        url = reverse('projectroles:api_project_create')
        post_data = {
            'title': NEW_PROJECT_TITLE,
            'type': PROJECT_TYPE_PROJECT,
            'parent': INVALID_UUID,
            'description': 'description',
            'readme': 'readme',
            'owner': str(self.user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Project.objects.count(), 2)

    def test_create_project_invalid_parent(self):
        """Test creating a project with a project as parent (should fail)"""

        # Assert preconditions
        self.assertEqual(Project.objects.count(), 2)

        url = reverse('projectroles:api_project_create')
        post_data = {
            'title': NEW_PROJECT_TITLE,
            'type': PROJECT_TYPE_PROJECT,
            'parent': str(self.project.sodar_uuid),
            'description': 'description',
            'readme': 'readme',
            'owner': str(self.user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Project.objects.count(), 2)

    @override_settings(PROJECTROLES_SITE_MODE=SITE_MODE_TARGET)
    def test_create_project_target_enabled(self):
        """Test creating a project as TARGET with target creation allowed"""

        # Assert preconditions
        self.assertEqual(Project.objects.count(), 2)

        url = reverse('projectroles:api_project_create')
        post_data = {
            'title': NEW_PROJECT_TITLE,
            'type': PROJECT_TYPE_PROJECT,
            'parent': str(self.category.sodar_uuid),
            'description': 'description',
            'readme': 'readme',
            'owner': str(self.user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 201, msg=response.content)
        self.assertEqual(Project.objects.count(), 3)

    @override_settings(
        PROJECTROLES_SITE_MODE=SITE_MODE_TARGET,
        PROJECTROLES_TARGET_CREATE=False,
    )
    def test_create_project_target_disabled(self):
        """Test creating a project as TARGET with target creation disallowed (should fail)"""

        # Assert preconditions
        self.assertEqual(Project.objects.count(), 2)

        url = reverse('projectroles:api_project_create')
        post_data = {
            'title': NEW_PROJECT_TITLE,
            'type': PROJECT_TYPE_PROJECT,
            'parent': str(self.category.sodar_uuid),
            'description': 'description',
            'readme': 'readme',
            'owner': str(self.user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 400, msg=response.content)
        self.assertEqual(Project.objects.count(), 2)


class TestProjectUpdateAPIView(
    RemoteSiteMixin, RemoteProjectMixin, TestCoreAPIViewsBase
):
    """Tests for ProjectUpdateAPIView"""

    def test_put_category(self):
        """Test put() for category updating"""

        # Assert preconditions
        self.assertEqual(Project.objects.count(), 2)

        url = reverse(
            'projectroles:api_project_update',
            kwargs={'project': self.category.sodar_uuid},
        )
        put_data = {
            'title': UPDATED_TITLE,
            'type': PROJECT_TYPE_CATEGORY,
            'parent': '',
            'description': UPDATED_DESC,
            'readme': UPDATED_README,
            'owner': str(self.user.sodar_uuid),
        }
        response = self.request_knox(url, method='PUT', data=put_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 200, msg=response.content)
        self.assertEqual(Project.objects.count(), 2)

        # Assert object content
        self.category.refresh_from_db()
        model_dict = model_to_dict(self.category)
        model_dict['readme'] = model_dict['readme'].raw
        expected = {
            'id': self.category.pk,
            'title': UPDATED_TITLE,
            'type': PROJECT_TYPE_CATEGORY,
            'parent': None,
            'description': UPDATED_DESC,
            'readme': UPDATED_README,
            'submit_status': SODAR_CONSTANTS['SUBMIT_STATUS_OK'],
            'sodar_uuid': self.category.sodar_uuid,
        }
        self.assertEqual(model_dict, expected)

        # Assert API response
        expected = {
            'title': UPDATED_TITLE,
            'type': PROJECT_TYPE_CATEGORY,
            'parent': None,
            'submit_status': SODAR_CONSTANTS['SUBMIT_STATUS_OK'],
            'description': UPDATED_DESC,
            'readme': UPDATED_README,
            'roles': {
                str(self.category.get_owner().sodar_uuid): {
                    'role': PROJECT_ROLE_OWNER,
                    'user': self.get_serialized_user(self.user),
                }
            },
            'sodar_uuid': str(self.category.sodar_uuid),
        }
        self.assertEqual(json.loads(response.content), expected)

    def test_put_project(self):
        """Test put() for project updating"""

        # Assert preconditions
        self.assertEqual(Project.objects.count(), 2)

        url = reverse(
            'projectroles:api_project_update',
            kwargs={'project': self.project.sodar_uuid},
        )
        put_data = {
            'title': UPDATED_TITLE,
            'type': PROJECT_TYPE_PROJECT,
            'parent': str(self.category.sodar_uuid),
            'description': UPDATED_DESC,
            'readme': UPDATED_README,
            'owner': str(self.user.sodar_uuid),
        }
        response = self.request_knox(url, method='PUT', data=put_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 200, msg=response.content)
        self.assertEqual(Project.objects.count(), 2)

        # Assert object content
        self.project.refresh_from_db()
        model_dict = model_to_dict(self.project)
        model_dict['readme'] = model_dict['readme'].raw
        expected = {
            'id': self.project.pk,
            'title': UPDATED_TITLE,
            'type': PROJECT_TYPE_PROJECT,
            'parent': self.category.pk,
            'description': UPDATED_DESC,
            'readme': UPDATED_README,
            'submit_status': SODAR_CONSTANTS['SUBMIT_STATUS_OK'],
            'sodar_uuid': self.project.sodar_uuid,
        }
        self.assertEqual(model_dict, expected)

        # Assert API response
        expected = {
            'title': UPDATED_TITLE,
            'type': PROJECT_TYPE_PROJECT,
            'parent': str(self.category.sodar_uuid),
            'submit_status': SODAR_CONSTANTS['SUBMIT_STATUS_OK'],
            'description': UPDATED_DESC,
            'readme': UPDATED_README,
            'roles': {
                str(self.project.get_owner().sodar_uuid): {
                    'role': PROJECT_ROLE_OWNER,
                    'user': self.get_serialized_user(self.user),
                }
            },
            'sodar_uuid': str(self.project.sodar_uuid),
        }
        self.assertEqual(json.loads(response.content), expected)

    def test_patch_category(self):
        """Test patch() for updating category metadata"""

        # Assert preconditions
        self.assertEqual(Project.objects.count(), 2)

        url = reverse(
            'projectroles:api_project_update',
            kwargs={'project': self.category.sodar_uuid},
        )
        patch_data = {
            'title': UPDATED_TITLE,
            'description': UPDATED_DESC,
            'readme': UPDATED_README,
        }
        response = self.request_knox(url, method='PATCH', data=patch_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 200, msg=response.content)
        self.assertEqual(Project.objects.count(), 2)

        # Assert object content
        self.category.refresh_from_db()
        model_dict = model_to_dict(self.category)
        model_dict['readme'] = model_dict['readme'].raw
        expected = {
            'id': self.category.pk,
            'title': UPDATED_TITLE,
            'type': PROJECT_TYPE_CATEGORY,
            'parent': None,
            'description': UPDATED_DESC,
            'readme': UPDATED_README,
            'submit_status': SODAR_CONSTANTS['SUBMIT_STATUS_OK'],
            'sodar_uuid': self.category.sodar_uuid,
        }
        self.assertEqual(model_dict, expected)

        # Assert role assignment
        self.assertEqual(self.category.get_owner().user, self.user)

        # Assert API response
        expected = {
            'title': UPDATED_TITLE,
            'type': PROJECT_TYPE_CATEGORY,
            'parent': None,
            'submit_status': SODAR_CONSTANTS['SUBMIT_STATUS_OK'],
            'description': UPDATED_DESC,
            'readme': UPDATED_README,
            'roles': {
                str(self.category.get_owner().sodar_uuid): {
                    'role': PROJECT_ROLE_OWNER,
                    'user': self.get_serialized_user(self.user),
                }
            },
            'sodar_uuid': str(self.category.sodar_uuid),
        }
        self.assertEqual(json.loads(response.content), expected)

    def test_patch_project(self):
        """Test patch() for updating project metadata"""

        # Assert preconditions
        self.assertEqual(Project.objects.count(), 2)

        url = reverse(
            'projectroles:api_project_update',
            kwargs={'project': self.project.sodar_uuid},
        )
        patch_data = {
            'title': UPDATED_TITLE,
            'description': UPDATED_DESC,
            'readme': UPDATED_README,
        }
        response = self.request_knox(url, method='PATCH', data=patch_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 200, msg=response.content)
        self.assertEqual(Project.objects.count(), 2)

        # Assert object content
        self.project.refresh_from_db()
        model_dict = model_to_dict(self.project)
        model_dict['readme'] = model_dict['readme'].raw
        expected = {
            'id': self.project.pk,
            'title': UPDATED_TITLE,
            'type': PROJECT_TYPE_PROJECT,
            'parent': self.category.pk,
            'description': UPDATED_DESC,
            'readme': UPDATED_README,
            'submit_status': SODAR_CONSTANTS['SUBMIT_STATUS_OK'],
            'sodar_uuid': self.project.sodar_uuid,
        }
        self.assertEqual(model_dict, expected)

        # Assert role assignment
        self.assertEqual(self.project.get_owner().user, self.user)

        # Assert API response
        expected = {
            'title': UPDATED_TITLE,
            'type': PROJECT_TYPE_PROJECT,
            'parent': str(self.category.sodar_uuid),
            'submit_status': SODAR_CONSTANTS['SUBMIT_STATUS_OK'],
            'description': UPDATED_DESC,
            'readme': UPDATED_README,
            'roles': {
                str(self.project.get_owner().sodar_uuid): {
                    'role': PROJECT_ROLE_OWNER,
                    'user': self.get_serialized_user(self.user),
                }
            },
            'sodar_uuid': str(self.project.sodar_uuid),
        }
        self.assertEqual(json.loads(response.content), expected)

    def test_patch_project_owner(self):
        """Test patch() for updating project owner (should fail)"""
        new_owner = self.make_user('new_owner')

        url = reverse(
            'projectroles:api_project_update',
            kwargs={'project': self.project.sodar_uuid},
        )
        patch_data = {'owner': str(new_owner.sodar_uuid)}
        response = self.request_knox(url, method='PATCH', data=patch_data)

        # Assert response
        self.assertEqual(response.status_code, 400, msg=response.content)

    def test_patch_project_move(self):
        """Test patch() for moving project under a different category"""

        new_category = self._make_project(
            'NewCategory', PROJECT_TYPE_CATEGORY, None
        )
        self._make_assignment(new_category, self.user, self.role_owner)
        url = reverse(
            'projectroles:api_project_update',
            kwargs={'project': self.project.sodar_uuid},
        )
        patch_data = {'parent': str(new_category.sodar_uuid)}
        response = self.request_knox(url, method='PATCH', data=patch_data)

        # Assert response
        self.assertEqual(response.status_code, 200, msg=response.content)

        # Assert object content
        self.project.refresh_from_db()
        model_dict = model_to_dict(self.project)
        self.assertEqual(model_dict['parent'], new_category.pk)

        # Assert role assignment
        self.assertEqual(self.project.get_owner().user, self.user)

        # Assert API response
        self.assertEqual(
            json.loads(response.content)['parent'], str(new_category.sodar_uuid)
        )

    def test_patch_project_move_unallowed(self):
        """Test patch() for moving project without permissions (should fail)"""

        new_category = self._make_project(
            'NewCategory', PROJECT_TYPE_CATEGORY, None
        )
        new_owner = self.make_user('new_owner')
        self._make_assignment(new_category, new_owner, self.role_owner)
        url = reverse(
            'projectroles:api_project_update',
            kwargs={'project': self.project.sodar_uuid},
        )
        patch_data = {'parent': str(new_category.sodar_uuid)}
        # Disable superuser status from self.user and perform request
        self.user.is_superuser = False
        self.user.save()
        response = self.request_knox(url, method='PATCH', data=patch_data)

        # Assert response
        self.assertEqual(response.status_code, 403, msg=response.content)

    def test_patch_project_move_root(self):
        """Test patch() for moving project without permissions (should fail)"""

        new_category = self._make_project(
            'NewCategory', PROJECT_TYPE_CATEGORY, None
        )
        new_owner = self.make_user('new_owner')
        self._make_assignment(new_category, new_owner, self.role_owner)
        url = reverse(
            'projectroles:api_project_update',
            kwargs={'project': self.project.sodar_uuid},
        )
        patch_data = {'parent': ''}
        response = self.request_knox(url, method='PATCH', data=patch_data)

        # Assert response
        self.assertEqual(response.status_code, 200, msg=response.content)

    def test_patch_project_move_root_unallowed(self):
        """Test patch() for moving project to root without permissions (should fail)"""

        new_category = self._make_project(
            'NewCategory', PROJECT_TYPE_CATEGORY, None
        )
        new_owner = self.make_user('new_owner')
        self._make_assignment(new_category, new_owner, self.role_owner)
        url = reverse(
            'projectroles:api_project_update',
            kwargs={'project': self.project.sodar_uuid},
        )
        patch_data = {'parent': ''}
        # Disable superuser status from self.user and perform request
        self.user.is_superuser = False
        self.user.save()
        response = self.request_knox(url, method='PATCH', data=patch_data)

        # Assert response
        self.assertEqual(response.status_code, 403, msg=response.content)

    def test_patch_project_move_child(self):
        """Test patch() for moving a category inside its child (should fail)"""

        new_category = self._make_project(
            'NewCategory', PROJECT_TYPE_CATEGORY, self.category
        )
        self._make_assignment(new_category, self.user, self.role_owner)
        url = reverse(
            'projectroles:api_project_update',
            kwargs={'project': self.category.sodar_uuid},
        )
        patch_data = {'parent': str(new_category.sodar_uuid)}
        response = self.request_knox(url, method='PATCH', data=patch_data)

        # Assert response
        self.assertEqual(response.status_code, 400, msg=response.content)

    def test_patch_project_type_change(self):
        """Test patch() with a changed project type (should fail)"""
        url = reverse(
            'projectroles:api_project_update',
            kwargs={'project': self.project.sodar_uuid},
        )
        patch_data = {'type': PROJECT_TYPE_CATEGORY}
        response = self.request_knox(url, method='PATCH', data=patch_data)

        # Assert response
        self.assertEqual(response.status_code, 400, msg=response.content)

    @override_settings(PROJECTROLES_SITE_MODE=SITE_MODE_TARGET)
    def test_patch_project_remote(self):
        """Test patch() for updating remote project metadata (should fail)"""

        # Create source site and remote project
        source_site = self._make_site(
            name=REMOTE_SITE_NAME,
            url=REMOTE_SITE_URL,
            mode=SITE_MODE_SOURCE,
            description=REMOTE_SITE_DESC,
            secret=REMOTE_SITE_SECRET,
        )
        self._make_remote_project(
            project_uuid=self.project.sodar_uuid,
            project=self.project,
            site=source_site,
            level=SODAR_CONSTANTS['REMOTE_LEVEL_READ_ROLES'],
        )

        url = reverse(
            'projectroles:api_project_update',
            kwargs={'project': self.project.sodar_uuid},
        )
        patch_data = {
            'title': UPDATED_TITLE,
            'description': UPDATED_DESC,
            'readme': UPDATED_README,
        }
        response = self.request_knox(url, method='PATCH', data=patch_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 400, msg=response.content)


class TestRoleAssignmentCreateAPIView(
    RemoteSiteMixin, RemoteProjectMixin, TestCoreAPIViewsBase
):
    """Tests for RoleAssignmentCreateAPIView"""

    def setUp(self):
        super().setUp()
        self.assign_user = self.make_user('assign_user')

    def test_create_contributor(self):
        """Test creating a contributor role for user"""

        # Assert preconditions
        self.assertEqual(
            RoleAssignment.objects.filter(project=self.project).count(), 1
        )

        url = reverse(
            'projectroles:api_role_create',
            kwargs={'project': self.project.sodar_uuid},
        )
        post_data = {
            'role': PROJECT_ROLE_CONTRIBUTOR,
            'user': str(self.assign_user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and role status
        self.assertEqual(response.status_code, 201, msg=response.content)
        self.assertEqual(
            RoleAssignment.objects.filter(project=self.project).count(), 2
        )

        # Assert object
        role_as = RoleAssignment.objects.filter(
            project=self.project,
            role=self.role_contributor,
            user=self.assign_user,
        ).first()
        self.assertIsNotNone(role_as)

        # Assert API response
        expected = {
            'project': str(self.project.sodar_uuid),
            'role': PROJECT_ROLE_CONTRIBUTOR,
            'user': str(self.assign_user.sodar_uuid),
            'sodar_uuid': str(role_as.sodar_uuid),
        }
        self.assertEqual(json.loads(response.content), expected)

    def test_create_owner(self):
        """Test creating an owner role (should fail)"""

        url = reverse(
            'projectroles:api_role_create',
            kwargs={'project': self.project.sodar_uuid},
        )
        post_data = {
            'role': PROJECT_ROLE_OWNER,
            'user': str(self.assign_user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response
        self.assertEqual(response.status_code, 400, msg=response.content)

    def test_create_delegate(self):
        """Test creating a delegate role for user as owner"""

        # Disable superuser status from self.user
        self.user.is_superuser = False
        self.user.save()

        # Assert preconditions
        self.assertEqual(
            RoleAssignment.objects.filter(project=self.project).count(), 1
        )

        url = reverse(
            'projectroles:api_role_create',
            kwargs={'project': self.project.sodar_uuid},
        )
        post_data = {
            'role': PROJECT_ROLE_DELEGATE,
            'user': str(self.assign_user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 201, msg=response.content)
        self.assertEqual(
            RoleAssignment.objects.filter(project=self.project).count(), 2
        )

        # Assert object
        role_as = RoleAssignment.objects.filter(
            project=self.project, role=self.role_delegate, user=self.assign_user
        ).first()
        self.assertIsNotNone(role_as)

    def test_create_delegate_unauthorized(self):
        """Test creating a delegate role without authorization (should fail)"""

        # Create new user and grant delegate role
        new_user = self.make_user('new_user')
        self._make_assignment(self.project, new_user, self.role_contributor)
        new_user_token = self.get_token(new_user)

        url = reverse(
            'projectroles:api_role_create',
            kwargs={'project': self.project.sodar_uuid},
        )
        post_data = {
            'role': PROJECT_ROLE_DELEGATE,
            'user': str(self.assign_user.sodar_uuid),
        }
        response = self.request_knox(
            url, method='POST', data=post_data, token=new_user_token
        )

        # Assert response
        self.assertEqual(response.status_code, 403, msg=response.content)

    def test_create_delegate_limit(self):
        """Test creating a delegate role with limit reached (should fail)"""

        # Create new user and grant delegate role
        new_user = self.make_user('new_user')
        self._make_assignment(self.project, new_user, self.role_delegate)

        url = reverse(
            'projectroles:api_role_create',
            kwargs={'project': self.project.sodar_uuid},
        )
        post_data = {
            'role': PROJECT_ROLE_DELEGATE,
            'user': str(self.assign_user.sodar_uuid),
        }

        # NOTE: Post as owner
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response
        self.assertEqual(response.status_code, 400, msg=response.content)

    def test_create_delegate_category(self):
        """Test creating a non-owner role for category"""

        url = reverse(
            'projectroles:api_role_create',
            kwargs={'project': self.category.sodar_uuid},
        )
        post_data = {
            'role': PROJECT_ROLE_DELEGATE,
            'user': str(self.assign_user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response
        self.assertEqual(response.status_code, 201, msg=response.content)

    def test_create_role_existing(self):
        """Test creating a role for user already in the project"""

        # Assert preconditions
        self.assertEqual(
            RoleAssignment.objects.filter(project=self.project).count(), 1
        )

        url = reverse(
            'projectroles:api_role_create',
            kwargs={'project': self.project.sodar_uuid},
        )
        post_data = {
            'role': PROJECT_ROLE_CONTRIBUTOR,
            'user': str(self.assign_user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and role status
        self.assertEqual(response.status_code, 201, msg=response.content)
        self.assertEqual(
            RoleAssignment.objects.filter(project=self.project).count(), 2
        )

        # Post again
        post_data = {
            'role': PROJECT_ROLE_GUEST,
            'user': str(self.assign_user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 400, msg=response.content)
        self.assertEqual(
            RoleAssignment.objects.filter(project=self.project).count(), 2
        )

    @override_settings(PROJECTROLES_SITE_MODE=SITE_MODE_TARGET)
    def test_create_remote(self):
        """Test creating a role for a remote project (should fail)"""

        # Create source site and remote project
        source_site = self._make_site(
            name=REMOTE_SITE_NAME,
            url=REMOTE_SITE_URL,
            mode=SITE_MODE_SOURCE,
            description=REMOTE_SITE_DESC,
            secret=REMOTE_SITE_SECRET,
        )
        self._make_remote_project(
            project_uuid=self.project.sodar_uuid,
            project=self.project,
            site=source_site,
            level=SODAR_CONSTANTS['REMOTE_LEVEL_READ_ROLES'],
        )

        # Assert preconditions
        self.assertEqual(
            RoleAssignment.objects.filter(project=self.project).count(), 1
        )

        url = reverse(
            'projectroles:api_role_create',
            kwargs={'project': self.project.sodar_uuid},
        )
        post_data = {
            'role': PROJECT_ROLE_CONTRIBUTOR,
            'user': str(self.assign_user.sodar_uuid),
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and role status
        self.assertEqual(response.status_code, 400, msg=response.content)
        self.assertEqual(
            RoleAssignment.objects.filter(project=self.project).count(), 1
        )


class TestRoleAssignmentUpdateAPIView(
    RemoteSiteMixin, RemoteProjectMixin, TestCoreAPIViewsBase
):
    """Tests for RoleAssignmentUpdateAPIView"""

    def setUp(self):
        super().setUp()
        self.assign_user = self.make_user('assign_user')
        self.update_as = self._make_assignment(
            self.project, self.assign_user, self.role_contributor
        )

    def test_put_role(self):
        """Test put() for role assignment updating"""

        # Assert preconditions
        self.assertEqual(RoleAssignment.objects.count(), 3)

        url = reverse(
            'projectroles:api_role_update',
            kwargs={'roleassignment': self.update_as.sodar_uuid},
        )
        put_data = {
            'role': PROJECT_ROLE_GUEST,
            'user': str(self.assign_user.sodar_uuid),
        }
        response = self.request_knox(url, method='PUT', data=put_data)

        # Assert response and role status
        self.assertEqual(response.status_code, 200, msg=response.content)
        self.assertEqual(RoleAssignment.objects.count(), 3)

        # Assert object content
        self.update_as.refresh_from_db()
        model_dict = model_to_dict(self.update_as)
        expected = {
            'id': self.update_as.pk,
            'project': self.project.pk,
            'role': self.role_guest.pk,
            'user': self.assign_user.pk,
            'sodar_uuid': self.update_as.sodar_uuid,
        }
        self.assertEqual(model_dict, expected)

        # Assert API response
        expected = {
            'project': str(self.project.sodar_uuid),
            'role': PROJECT_ROLE_GUEST,
            'user': str(self.assign_user.sodar_uuid),
            'sodar_uuid': str(self.update_as.sodar_uuid),
        }
        self.assertEqual(json.loads(response.content), expected)

    def test_put_delegate(self):
        """Test put() for delegate role assignment"""
        url = reverse(
            'projectroles:api_role_update',
            kwargs={'roleassignment': self.update_as.sodar_uuid},
        )
        put_data = {
            'role': PROJECT_ROLE_DELEGATE,
            'user': str(self.assign_user.sodar_uuid),
        }
        response = self.request_knox(url, method='PUT', data=put_data)

        # Assert response
        self.assertEqual(response.status_code, 200, msg=response.content)

        # Assert object content
        self.update_as.refresh_from_db()
        model_dict = model_to_dict(self.update_as)
        expected = {
            'id': self.update_as.pk,
            'project': self.project.pk,
            'role': self.role_delegate.pk,
            'user': self.assign_user.pk,
            'sodar_uuid': self.update_as.sodar_uuid,
        }
        self.assertEqual(model_dict, expected)

        # Assert API response
        expected = {
            'project': str(self.project.sodar_uuid),
            'role': PROJECT_ROLE_DELEGATE,
            'user': str(self.assign_user.sodar_uuid),
            'sodar_uuid': str(self.update_as.sodar_uuid),
        }
        self.assertEqual(json.loads(response.content), expected)

    def test_put_owner(self):
        """Test put() for owner role assignment (should fail)"""
        url = reverse(
            'projectroles:api_role_update',
            kwargs={'roleassignment': self.update_as.sodar_uuid},
        )
        put_data = {
            'role': PROJECT_ROLE_OWNER,
            'user': str(self.assign_user.sodar_uuid),
        }
        response = self.request_knox(url, method='PUT', data=put_data)

        # Assert response
        self.assertEqual(response.status_code, 400, msg=response.content)

    def test_put_change_user(self):
        """Test put() with a different user (should fail)"""
        new_user = self.make_user('new_user')

        url = reverse(
            'projectroles:api_role_update',
            kwargs={'roleassignment': self.update_as.sodar_uuid},
        )
        put_data = {
            'role': PROJECT_ROLE_GUEST,
            'user': str(new_user.sodar_uuid),
        }
        response = self.request_knox(url, method='PUT', data=put_data)

        # Assert response
        self.assertEqual(response.status_code, 400, msg=response.content)

    def test_patch_role(self):
        """Test patch() for role assignment updating"""

        # Assert preconditions
        self.assertEqual(RoleAssignment.objects.count(), 3)

        url = reverse(
            'projectroles:api_role_update',
            kwargs={'roleassignment': self.update_as.sodar_uuid},
        )
        patch_data = {'role': PROJECT_ROLE_GUEST}
        response = self.request_knox(url, method='PATCH', data=patch_data)

        # Assert response and role status
        self.assertEqual(response.status_code, 200, msg=response.content)
        self.assertEqual(RoleAssignment.objects.count(), 3)

        # Assert object content
        self.update_as.refresh_from_db()
        model_dict = model_to_dict(self.update_as)
        expected = {
            'id': self.update_as.pk,
            'project': self.project.pk,
            'role': self.role_guest.pk,
            'user': self.assign_user.pk,
            'sodar_uuid': self.update_as.sodar_uuid,
        }
        self.assertEqual(model_dict, expected)

        # Assert API response
        expected = {
            'project': str(self.project.sodar_uuid),
            'role': PROJECT_ROLE_GUEST,
            'user': str(self.assign_user.sodar_uuid),
            'sodar_uuid': str(self.update_as.sodar_uuid),
        }
        self.assertEqual(json.loads(response.content), expected)

    def test_patch_change_user(self):
        """Test patch() with a different user (should fail)"""
        new_user = self.make_user('new_user')

        url = reverse(
            'projectroles:api_role_update',
            kwargs={'roleassignment': self.update_as.sodar_uuid},
        )
        patch_data = {'user': str(new_user.sodar_uuid)}
        response = self.request_knox(url, method='PATCH', data=patch_data)

        # Assert response
        self.assertEqual(response.status_code, 400, msg=response.content)

    @override_settings(PROJECTROLES_SITE_MODE=SITE_MODE_TARGET)
    def test_patch_role_remote(self):
        """Test patch() for updating a role in a remote project (should fail)"""

        # Create source site and remote project
        source_site = self._make_site(
            name=REMOTE_SITE_NAME,
            url=REMOTE_SITE_URL,
            mode=SITE_MODE_SOURCE,
            description=REMOTE_SITE_DESC,
            secret=REMOTE_SITE_SECRET,
        )
        self._make_remote_project(
            project_uuid=self.project.sodar_uuid,
            project=self.project,
            site=source_site,
            level=SODAR_CONSTANTS['REMOTE_LEVEL_READ_ROLES'],
        )

        url = reverse(
            'projectroles:api_role_update',
            kwargs={'roleassignment': self.update_as.sodar_uuid},
        )
        patch_data = {'role': PROJECT_ROLE_GUEST}
        response = self.request_knox(url, method='PATCH', data=patch_data)

        # Assert response and role status
        self.assertEqual(response.status_code, 400, msg=response.content)


class TestRoleAssignmentDestroyAPIView(
    RemoteSiteMixin, RemoteProjectMixin, TestCoreAPIViewsBase
):
    """Tests for RoleAssignmentDestroyAPIView"""

    def setUp(self):
        super().setUp()
        self.assign_user = self.make_user('assign_user')

        self.update_as = self._make_assignment(
            self.project, self.assign_user, self.role_contributor
        )

    def test_delete_role(self):
        """Test delete for role assignment deletion"""

        # Assert preconditions
        self.assertEqual(RoleAssignment.objects.count(), 3)

        url = reverse(
            'projectroles:api_role_destroy',
            kwargs={'roleassignment': self.update_as.sodar_uuid},
        )
        response = self.request_knox(url, method='DELETE')

        # Assert response and role status
        self.assertEqual(response.status_code, 204, msg=response.content)
        self.assertEqual(RoleAssignment.objects.count(), 2)
        self.assertEqual(
            RoleAssignment.objects.filter(
                project=self.project, user=self.assign_user
            ).count(),
            0,
        )

    def test_delete_delegate_unauthorized(self):
        """Test delete for delegate deletion without perms (should fail)"""
        new_user = self.make_user('new_user')
        delegate_as = self._make_assignment(
            self.project, new_user, self.role_delegate
        )

        # Assert preconditions
        self.assertEqual(RoleAssignment.objects.count(), 4)

        url = reverse(
            'projectroles:api_role_destroy',
            kwargs={'roleassignment': delegate_as.sodar_uuid},
        )
        # NOTE: Perform record as contributor user
        token = self.get_token(self.assign_user)
        response = self.request_knox(url, method='DELETE', token=token)

        # Assert response and role status
        self.assertEqual(response.status_code, 403, msg=response.content)
        self.assertEqual(RoleAssignment.objects.count(), 4)

    def test_delete_owner(self):
        """Test delete for owner deletion (should fail)"""

        # Assert preconditions
        self.assertEqual(RoleAssignment.objects.count(), 3)

        url = reverse(
            'projectroles:api_role_destroy',
            kwargs={'roleassignment': self.owner_as.sodar_uuid},
        )
        response = self.request_knox(url, method='DELETE')

        # Assert response and project status
        self.assertEqual(response.status_code, 400, msg=response.content)
        self.assertEqual(RoleAssignment.objects.count(), 3)

    @override_settings(PROJECTROLES_SITE_MODE=SITE_MODE_TARGET)
    def test_delete_remote(self):
        """Test delete for a remote project (should fail)"""

        # Create source site and remote project
        source_site = self._make_site(
            name=REMOTE_SITE_NAME,
            url=REMOTE_SITE_URL,
            mode=SITE_MODE_SOURCE,
            description=REMOTE_SITE_DESC,
            secret=REMOTE_SITE_SECRET,
        )
        self._make_remote_project(
            project_uuid=self.project.sodar_uuid,
            project=self.project,
            site=source_site,
            level=SODAR_CONSTANTS['REMOTE_LEVEL_READ_ROLES'],
        )

        # Assert preconditions
        self.assertEqual(RoleAssignment.objects.count(), 3)

        url = reverse(
            'projectroles:api_role_destroy',
            kwargs={'roleassignment': self.update_as.sodar_uuid},
        )
        response = self.request_knox(url, method='DELETE')

        # Assert response and role status
        self.assertEqual(response.status_code, 400, msg=response.content)
        self.assertEqual(RoleAssignment.objects.count(), 3)


class TestRoleAssignmentOwnerTransferAPIView(
    RemoteSiteMixin, RemoteProjectMixin, TestCoreAPIViewsBase
):
    """Tests for RoleAssignmentOwnerTransferAPIView"""

    def setUp(self):
        super().setUp()
        self.assign_user = self.make_user('assign_user')

    def test_transfer_owner(self):
        """Test transferring ownership for a project"""

        # Assign role to new user
        self._make_assignment(
            self.project, self.assign_user, self.role_contributor
        )

        # Assert preconditions
        self.assertEqual(self.project.get_owner().user, self.user)

        url = reverse(
            'projectroles:api_role_owner_transfer',
            kwargs={'project': self.project.sodar_uuid},
        )
        post_data = {
            'new_owner': self.assign_user.username,
            'old_owner_role': self.role_contributor.name,
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 200, msg=response.content)
        self.assertEqual(self.project.get_owner().user, self.assign_user)

    def test_transfer_owner_category(self):
        """Test transferring ownership for a category"""

        # Assign role to new user
        self._make_assignment(
            self.category, self.assign_user, self.role_contributor
        )

        # Assert preconditions
        self.assertEqual(self.category.get_owner().user, self.user)

        url = reverse(
            'projectroles:api_role_owner_transfer',
            kwargs={'project': self.category.sodar_uuid},
        )
        post_data = {
            'new_owner': self.assign_user.username,
            'old_owner_role': self.role_contributor.name,
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 200, msg=response.content)
        self.assertEqual(self.category.get_owner().user, self.assign_user)

    def test_transfer_owner_no_roles(self):
        """Test transferring ownership to user with no existing roles (should fail)"""

        # NOTE: No role given to user

        url = reverse(
            'projectroles:api_role_owner_transfer',
            kwargs={'project': self.project.sodar_uuid},
        )
        post_data = {
            'new_owner': self.assign_user.username,
            'old_owner_role': self.role_contributor.name,
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 400, msg=response.content)

    @override_settings(PROJECTROLES_SITE_MODE=SITE_MODE_TARGET)
    def test_transfer_remote(self):
        """Test transferring ownership for a remote project (should fail)"""

        # Create source site and remote project
        source_site = self._make_site(
            name=REMOTE_SITE_NAME,
            url=REMOTE_SITE_URL,
            mode=SITE_MODE_SOURCE,
            description=REMOTE_SITE_DESC,
            secret=REMOTE_SITE_SECRET,
        )
        self._make_remote_project(
            project_uuid=self.project.sodar_uuid,
            project=self.project,
            site=source_site,
            level=SODAR_CONSTANTS['REMOTE_LEVEL_READ_ROLES'],
        )

        # Assign role to new user
        self._make_assignment(
            self.project, self.assign_user, self.role_contributor
        )

        # Assert preconditions
        self.assertEqual(self.project.get_owner().user, self.user)

        url = reverse(
            'projectroles:api_role_owner_transfer',
            kwargs={'project': self.project.sodar_uuid},
        )
        post_data = {
            'new_owner': self.assign_user.username,
            'old_owner_role': self.role_contributor.name,
        }
        response = self.request_knox(url, method='POST', data=post_data)

        # Assert response and project status
        self.assertEqual(response.status_code, 400, msg=response.content)
        self.assertEqual(self.project.get_owner().user, self.user)


class TestUserListAPIView(TestCoreAPIViewsBase):
    """Tests for UserListAPIView"""

    def setUp(self):
        super().setUp()
        # Create additional users
        self.domain_user = self.make_user('domain_user@domain')

    def test_get(self):
        """Test UserListAPIView get() as a regular user"""
        url = reverse('projectroles:api_user_list')
        response = self.request_knox(
            url, token=self.get_token(self.domain_user)
        )

        # Assert response
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(len(response_data), 1)  # System users not returned
        expected = [
            {
                'username': self.domain_user.username,
                'name': self.domain_user.name,
                'email': self.domain_user.email,
                'sodar_uuid': str(self.domain_user.sodar_uuid),
            }
        ]
        self.assertEqual(response_data, expected)

    def test_get_superuser(self):
        """Test UserListAPIView get() as a superuser"""
        url = reverse('projectroles:api_user_list')
        response = self.request_knox(url)  # Default token is for superuser

        # Assert response
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertEqual(len(response_data), 2)
        expected = [
            {
                'username': self.user.username,
                'name': self.user.name,
                'email': self.user.email,
                'sodar_uuid': str(self.user.sodar_uuid),
            },
            {
                'username': self.domain_user.username,
                'name': self.domain_user.name,
                'email': self.domain_user.email,
                'sodar_uuid': str(self.domain_user.sodar_uuid),
            },
        ]
        self.assertEqual(response_data, expected)


class TestAPIVersioning(TestCoreAPIViewsBase):
    """Tests for REST API view versioning using ProjectRetrieveAPIView"""

    def setUp(self):
        super().setUp()

        self.url = reverse(
            'projectroles:api_project_retrieve',
            kwargs={'project': self.project.sodar_uuid},
        )

    def test_api_versioning(self):
        """Test SODAR API Access with correct version headers"""
        response = self.request_knox(
            self.url,
            media_type=views_api.CORE_API_MEDIA_TYPE,
            version=views_api.CORE_API_DEFAULT_VERSION,
        )
        self.assertEqual(response.status_code, 200)

    def test_api_versioning_invalid_version(self):
        """Test SODAR API Access with unsupported version (should fail)"""
        response = self.request_knox(
            self.url,
            media_type=views_api.CORE_API_MEDIA_TYPE,
            version=CORE_API_VERSION_INVALID,
        )
        self.assertEqual(response.status_code, 406)

    def test_api_versioning_invalid_media_type(self):
        """Test SODAR API Access with unsupported media type (should fail)"""
        response = self.request_knox(
            self.url,
            media_type=CORE_API_MEDIA_TYPE_INVALID,
            version=views_api.CORE_API_MEDIA_TYPE,
        )
        self.assertEqual(response.status_code, 406)


# TODO: To be updated once the legacy API view is redone for SODAR Core v0.9
class TestRemoteProjectGetAPIView(
    ProjectMixin,
    RoleAssignmentMixin,
    RemoteSiteMixin,
    RemoteProjectMixin,
    SODARAPIViewTestMixin,
    TestViewsBase,
):
    """Tests for remote project getting API view"""

    media_type = views_api.CORE_API_MEDIA_TYPE
    api_version = views_api.CORE_API_DEFAULT_VERSION

    def setUp(self):
        super().setUp()

        # Set up projects
        self.category = self._make_project(
            'TestCategory', PROJECT_TYPE_CATEGORY, None
        )
        self.cat_owner_as = self._make_assignment(
            self.category, self.user, self.role_owner
        )
        self.project = self._make_project(
            'TestProject', PROJECT_TYPE_PROJECT, self.category
        )
        self.project_owner_as = self._make_assignment(
            self.project, self.user, self.role_owner
        )

        # Create target site
        self.target_site = self._make_site(
            name=REMOTE_SITE_NAME,
            url=REMOTE_SITE_URL,
            mode=SITE_MODE_TARGET,
            description=REMOTE_SITE_DESC,
            secret=REMOTE_SITE_SECRET,
        )

        # Create remote project
        self.remote_project = self._make_remote_project(
            site=self.target_site,
            project_uuid=self.project.sodar_uuid,
            project=self.project,
            level=SODAR_CONSTANTS['REMOTE_LEVEL_READ_INFO'],
        )

        self.remote_api = RemoteProjectAPI()

    def test_get(self):
        """Test retrieving project data to the target site"""

        response = self.client.get(
            reverse(
                'projectroles:api_remote_get',
                kwargs={'secret': REMOTE_SITE_SECRET},
            )
        )

        self.assertEqual(response.status_code, 200)

        expected = self.remote_api.get_target_data(self.target_site)
        response_dict = json.loads(response.content.decode('utf-8'))

        self.assertEqual(response_dict, expected)

    def test_get_invalid_secret(self):
        """Test retrieving project data with an invalid secret (should fail)"""

        response = self.client.get(
            reverse(
                'projectroles:api_remote_get', kwargs={'secret': build_secret()}
            )
        )

        self.assertEqual(response.status_code, 401)
