"""REST API view permission tests for the filesfolders app"""

import os
import uuid

from django.shortcuts import reverse

# Projectroles dependency
from projectroles.tests.test_permissions_api import TestProjectAPIPermissionBase
from projectroles.utils import build_secret

from filesfolders.models import File, Folder, HyperLink
from filesfolders.tests.test_models import (
    FileMixin,
    FolderMixin,
    HyperLinkMixin,
)


# Local constants
SECRET = '7dqq83clo2iyhg29hifbor56og6911r5'
TEST_DATA_PATH = os.path.dirname(__file__) + '/data/'
ZIP_PATH_NO_FILES = TEST_DATA_PATH + 'no_files.zip'


class TestFolderAPIPermissions(FolderMixin, TestProjectAPIPermissionBase):
    """Tests for Folder API view permissions"""

    def setUp(self):
        super().setUp()

        self.folder = self._make_folder(
            name='folder',
            project=self.project,
            folder=None,
            owner=self.as_owner.user,  # Project owner is the owner of folder
            description='',
        )

    def test_folder_list(self):
        """Test permissions for folder listing"""
        url = reverse(
            'filesfolders:api_folder_list_create',
            kwargs={'project': self.project.sodar_uuid},
        )
        good_users = [
            self.superuser,
            self.as_owner.user,
            self.as_delegate.user,
            self.as_contributor.user,
            self.as_guest.user,
        ]
        bad_users = [self.user_no_roles]
        self.assert_response_api(url, good_users, 200)
        self.assert_response_api(url, bad_users, 403)
        self.assert_response_api(url, self.anonymous, 401)
        self.assert_response_api(url, good_users, 200, knox=True)

    def test_folder_create(self):
        """Test permissions for folder creation"""
        url = reverse(
            'filesfolders:api_folder_list_create',
            kwargs={'project': self.project.sodar_uuid},
        )
        request_data = {
            'name': 'New Folder',
            'flag': 'IMPORTANT',
            'description': 'Folder\'s description',
        }

        def _cleanup():
            Folder.objects.order_by('-pk').first().delete()

        good_users = [
            self.superuser,
            self.as_owner.user,
            self.as_delegate.user,
            self.as_contributor.user,
        ]
        bad_users = [self.as_guest.user, self.user_no_roles]
        self.assert_response_api(
            url,
            good_users,
            201,
            method='POST',
            data=request_data,
            cleanup_method=_cleanup,
        )
        self.assert_response_api(
            url, bad_users, 403, method='POST', data=request_data
        )
        self.assert_response_api(
            url, self.anonymous, 401, method='POST', data=request_data
        )
        self.assert_response_api(
            url,
            good_users,
            201,
            method='POST',
            data=request_data,
            cleanup_method=_cleanup,
            knox=True,
        )

    def test_folder_retrieve(self):
        """Test permissions for folder retrieval"""
        url = reverse(
            'filesfolders:api_folder_retrieve_update_destroy',
            kwargs={'folder': self.folder.sodar_uuid},
        )

        good_users = [
            self.superuser,
            self.as_owner.user,
            self.as_delegate.user,
            self.as_contributor.user,
            self.as_guest.user,
        ]
        bad_users = [self.user_no_roles]
        self.assert_response_api(url, good_users, 200, method='GET')
        self.assert_response_api(url, bad_users, 403)
        self.assert_response_api(url, self.anonymous, 401)
        self.assert_response_api(url, good_users, 200, knox=True)

    def test_folder_update_put(self):
        """Test permissions for folder updating with PUT"""
        url = reverse(
            'filesfolders:api_folder_retrieve_update_destroy',
            kwargs={'folder': self.folder.sodar_uuid},
        )
        request_data = {
            'name': 'UPDATED Folder',
            'flag': 'FLAG',
            'description': 'UPDATED Description',
        }
        good_users = [
            self.superuser,
            self.as_owner.user,  # Owner of folder
            self.as_delegate.user,
        ]
        bad_users = [
            self.as_contributor.user,
            self.as_guest.user,
            self.user_no_roles,
        ]
        self.assert_response_api(
            url, good_users, 200, method='PUT', data=request_data
        )
        self.assert_response_api(
            url, bad_users, 403, method='PUT', data=request_data
        )
        self.assert_response_api(
            url, self.anonymous, 401, method='PUT', data=request_data
        )
        self.assert_response_api(
            url, good_users, 200, method='PUT', data=request_data, knox=True
        )

    def test_folder_update_patch(self):
        """Test permissions for folder updating with PATCH"""
        url = reverse(
            'filesfolders:api_folder_retrieve_update_destroy',
            kwargs={'folder': self.folder.sodar_uuid},
        )
        request_data = {'name': 'UPDATED Folder'}
        good_users = [
            self.superuser,
            self.as_owner.user,  # Owner of folder
            self.as_delegate.user,
        ]
        bad_users = [
            self.as_contributor.user,
            self.as_guest.user,
            self.user_no_roles,
        ]
        self.assert_response_api(
            url, good_users, 200, method='PATCH', data=request_data
        )
        self.assert_response_api(
            url, bad_users, 403, method='PATCH', data=request_data
        )
        self.assert_response_api(
            url, self.anonymous, 401, method='PATCH', data=request_data
        )
        self.assert_response_api(
            url, good_users, 200, method='PATCH', data=request_data, knox=True
        )

    def test_folder_destroy(self):
        """Test permissions for folder destroying with DELETE"""
        obj_uuid = uuid.uuid4()
        url = reverse(
            'filesfolders:api_folder_retrieve_update_destroy',
            kwargs={'folder': obj_uuid},
        )

        def _make_folder():
            folder = self._make_folder(
                name='folder',
                project=self.project,
                folder=None,
                owner=self.as_owner.user,
                description='',
            )
            folder.sodar_uuid = obj_uuid
            folder.save()

        good_users = [
            self.superuser,
            self.as_owner.user,  # Owner of folder
            self.as_delegate.user,
        ]
        bad_users = [
            self.as_contributor.user,
            self.as_guest.user,
            self.user_no_roles,
        ]
        _make_folder()
        self.assert_response_api(
            url, good_users, 204, method='DELETE', cleanup_method=_make_folder
        )
        self.assert_response_api(url, bad_users, 403, method='DELETE')
        self.assert_response_api(url, self.anonymous, 401, method='DELETE')
        self.assert_response_api(
            url,
            good_users,
            204,
            method='DELETE',
            cleanup_method=_make_folder,
            knox=True,
        )


class TestFileAPIPermissions(FileMixin, TestProjectAPIPermissionBase):
    """Tests for File API view permissions"""

    def setUp(self):
        super().setUp()

        self.file_content = bytes('content'.encode('utf-8'))
        self.file = self._make_file(
            name='file.txt',
            file_name='file.txt',
            file_content=self.file_content,
            project=self.project,
            folder=None,
            owner=self.as_owner.user,
            description='',
            public_url=True,
            secret=SECRET,
        )

        self.new_file_name = 'New File'
        self.request_data = {
            'name': self.new_file_name,
            'flag': 'IMPORTANT',
            'description': 'File\'s description',
            'secret': 'foo',
            'public_url': True,
            'file': open(ZIP_PATH_NO_FILES, 'rb'),
        }

    def tearDown(self):
        self.request_data['file'].close()
        super().tearDown()

    def test_file_list(self):
        """Test permissions for file listing"""
        url = reverse(
            'filesfolders:api_file_list_create',
            kwargs={'project': self.project.sodar_uuid},
        )
        good_users = [
            self.superuser,
            self.as_owner.user,
            self.as_delegate.user,
            self.as_contributor.user,
            self.as_guest.user,
        ]
        bad_users = [self.user_no_roles]
        self.assert_response_api(url, good_users, 200)
        self.assert_response_api(url, bad_users, 403)
        self.assert_response_api(url, self.anonymous, 401)
        self.assert_response_api(url, good_users, 200, knox=True)

    def test_file_create(self):
        """Test permissions for file creation"""
        url = reverse(
            'filesfolders:api_file_list_create',
            kwargs={'project': self.project.sodar_uuid},
        )

        # NOTE: Must call this for ALL requests to seek the file
        def _cleanup():
            file = File.objects.filter(name=self.new_file_name).first()

            if file:
                file.delete()

            self.request_data['file'].seek(0)

        good_users = [
            self.superuser,
            self.as_owner.user,
            self.as_delegate.user,
            self.as_contributor.user,
        ]
        bad_users = [self.as_guest.user, self.user_no_roles]
        self.assert_response_api(
            url,
            good_users,
            201,
            method='POST',
            format='multipart',
            data=self.request_data,
            cleanup_method=_cleanup,
        )
        self.assert_response_api(
            url,
            bad_users,
            403,
            method='POST',
            format='multipart',
            data=self.request_data,
            cleanup_method=_cleanup,
        )
        self.assert_response_api(
            url,
            self.anonymous,
            401,
            method='POST',
            format='multipart',
            data=self.request_data,
            cleanup_method=_cleanup,
        )
        self.assert_response_api(
            url,
            good_users,
            201,
            method='POST',
            format='multipart',
            data=self.request_data,
            cleanup_method=_cleanup,
            knox=True,
        )

        self.request_data['file'].close()

    def test_file_retrieve(self):
        """Test permissions for file retrieval"""
        url = reverse(
            'filesfolders:api_file_retrieve_update_destroy',
            kwargs={'file': self.file.sodar_uuid},
        )

        good_users = [
            self.superuser,
            self.as_owner.user,
            self.as_delegate.user,
            self.as_contributor.user,
            self.as_guest.user,
        ]
        bad_users = [self.user_no_roles]
        self.assert_response_api(url, good_users, 200, method='GET')
        self.assert_response_api(url, bad_users, 403)
        self.assert_response_api(url, self.anonymous, 401)
        self.assert_response_api(url, good_users, 200, knox=True)

    def test_file_update_put(self):
        """Test permissions for file updating with PUT"""
        url = reverse(
            'filesfolders:api_file_retrieve_update_destroy',
            kwargs={'file': self.file.sodar_uuid},
        )
        self.request_data.update(
            {
                'name': 'UPDATED Folder',
                'flag': 'FLAG',
                'description': 'UPDATED Description',
            }
        )

        # NOTE: Must call this for ALL requests to seek the file
        def _cleanup():
            self.request_data['file'].seek(0)

        good_users = [
            self.superuser,
            self.as_owner.user,  # Owner of file
            self.as_delegate.user,
        ]
        bad_users = [
            self.as_contributor.user,
            self.as_guest.user,
            self.user_no_roles,
        ]
        self.assert_response_api(
            url,
            good_users,
            200,
            method='PUT',
            format='multipart',
            data=self.request_data,
            cleanup_method=_cleanup,
        )
        self.assert_response_api(
            url,
            bad_users,
            403,
            method='PUT',
            format='multipart',
            data=self.request_data,
            cleanup_method=_cleanup,
        )
        self.assert_response_api(
            url,
            self.anonymous,
            401,
            method='PUT',
            format='multipart',
            data=self.request_data,
            cleanup_method=_cleanup,
        )
        self.assert_response_api(
            url,
            good_users,
            200,
            method='PUT',
            format='multipart',
            data=self.request_data,
            cleanup_method=_cleanup,
            knox=True,
        )

    def test_file_update_patch(self):
        """Test permissions for file updating with PATCH"""
        url = reverse(
            'filesfolders:api_file_retrieve_update_destroy',
            kwargs={'file': self.file.sodar_uuid},
        )
        self.request_data.update({'name': 'UPDATED Folder'})

        # NOTE: Must call this for ALL requests to seek the file
        def _cleanup():
            self.request_data['file'].seek(0)

        good_users = [
            self.superuser,
            self.as_owner.user,  # Owner of file
            self.as_delegate.user,
        ]
        bad_users = [
            self.as_contributor.user,
            self.as_guest.user,
            self.user_no_roles,
        ]
        self.assert_response_api(
            url,
            good_users,
            200,
            method='PATCH',
            format='multipart',
            data=self.request_data,
            cleanup_method=_cleanup,
        )
        self.assert_response_api(
            url,
            bad_users,
            403,
            method='PATCH',
            format='multipart',
            data=self.request_data,
            cleanup_method=_cleanup,
        )
        self.assert_response_api(
            url,
            self.anonymous,
            401,
            method='PATCH',
            format='multipart',
            data=self.request_data,
            cleanup_method=_cleanup,
        )
        self.assert_response_api(
            url,
            good_users,
            200,
            method='PATCH',
            format='multipart',
            data=self.request_data,
            cleanup_method=_cleanup,
            knox=True,
        )

    def test_file_destroy(self):
        """Test permissions for file destroying with DELETE"""
        obj_uuid = uuid.uuid4()
        url = reverse(
            'filesfolders:api_file_retrieve_update_destroy',
            kwargs={'file': obj_uuid},
        )

        def _make_file():
            file = self._make_file(
                name='file2.txt',
                file_name='file2.txt',
                file_content=self.file_content,
                project=self.project,
                folder=None,
                owner=self.as_owner.user,
                description='',
                public_url=True,
                secret=build_secret(),
            )
            file.sodar_uuid = obj_uuid
            file.save()

        good_users = [
            self.superuser,
            self.as_owner.user,  # Owner of file
            self.as_delegate.user,
        ]
        bad_users = [
            self.as_contributor.user,
            self.as_guest.user,
            self.user_no_roles,
        ]
        _make_file()
        self.assert_response_api(
            url, good_users, 204, method='DELETE', cleanup_method=_make_file
        )
        self.assert_response_api(url, bad_users, 403, method='DELETE')
        self.assert_response_api(url, self.anonymous, 401, method='DELETE')
        self.assert_response_api(
            url,
            good_users,
            204,
            method='DELETE',
            cleanup_method=_make_file,
            knox=True,
        )

    def test_file_serve(self):
        """Test permissions for file serving"""
        url = reverse(
            'filesfolders:api_file_serve', kwargs={'file': self.file.sodar_uuid}
        )

        good_users = [
            self.superuser,
            self.as_owner.user,
            self.as_delegate.user,
            self.as_contributor.user,
            self.as_guest.user,
        ]
        bad_users = [self.user_no_roles]
        self.assert_response_api(url, good_users, 200, method='GET')
        self.assert_response_api(url, bad_users, 403)
        self.assert_response_api(url, self.anonymous, 401)
        self.assert_response_api(url, good_users, 200, knox=True)


class TestHyperLinkAPIPermissions(HyperLinkMixin, TestProjectAPIPermissionBase):
    """Tests for HyperLink API view permissions"""

    def setUp(self):
        super().setUp()

        self.hyperlink = self._make_hyperlink(
            name='Link',
            url='http://www.google.com/',
            project=self.project,
            folder=None,
            owner=self.as_owner.user,
            description='',
        )

    def test_hyperlink_list(self):
        """Test permissions for hyperlink listing"""
        url = reverse(
            'filesfolders:api_hyperlink_list_create',
            kwargs={'project': self.project.sodar_uuid},
        )
        good_users = [
            self.superuser,
            self.as_owner.user,
            self.as_delegate.user,
            self.as_contributor.user,
            self.as_guest.user,
        ]
        bad_users = [self.user_no_roles]
        self.assert_response_api(url, good_users, 200)
        self.assert_response_api(url, bad_users, 403)
        self.assert_response_api(url, self.anonymous, 401)
        self.assert_response_api(url, good_users, 200, knox=True)

    def test_hyperlink_create(self):
        """Test permissions for hyperlink creation"""
        url = reverse(
            'filesfolders:api_hyperlink_list_create',
            kwargs={'project': self.project.sodar_uuid},
        )
        request_data = {
            'name': 'New HyperLink',
            'flag': 'IMPORTANT',
            'description': 'HyperLink\'s description',
            'url': 'http://www.cubi.bihealth.org',
        }

        def _cleanup():
            HyperLink.objects.order_by('-pk').first().delete()

        good_users = [
            self.superuser,
            self.as_owner.user,
            self.as_delegate.user,
            self.as_contributor.user,
        ]
        bad_users = [self.as_guest.user, self.user_no_roles]
        self.assert_response_api(
            url,
            good_users,
            201,
            method='POST',
            data=request_data,
            cleanup_method=_cleanup,
        )
        self.assert_response_api(
            url, bad_users, 403, method='POST', data=request_data
        )
        self.assert_response_api(
            url, self.anonymous, 401, method='POST', data=request_data
        )
        self.assert_response_api(
            url,
            good_users,
            201,
            method='POST',
            data=request_data,
            cleanup_method=_cleanup,
            knox=True,
        )

    def test_hyperlink_retrieve(self):
        """Test permissions for hyperlink retrieval"""
        url = reverse(
            'filesfolders:api_hyperlink_retrieve_update_destroy',
            kwargs={'hyperlink': self.hyperlink.sodar_uuid},
        )

        good_users = [
            self.superuser,
            self.as_owner.user,
            self.as_delegate.user,
            self.as_contributor.user,
            self.as_guest.user,
        ]
        bad_users = [self.user_no_roles]
        self.assert_response_api(url, good_users, 200, method='GET')
        self.assert_response_api(url, bad_users, 403)
        self.assert_response_api(url, self.anonymous, 401)
        self.assert_response_api(url, good_users, 200, knox=True)

    def test_hyperlink_update_put(self):
        """Test permissions for hyperlink updating with PUT"""
        url = reverse(
            'filesfolders:api_hyperlink_retrieve_update_destroy',
            kwargs={'hyperlink': self.hyperlink.sodar_uuid},
        )
        request_data = {
            'name': 'UPDATED HyperLink',
            'flag': 'FLAG',
            'description': 'UPDATED Description',
            'url': 'http://www.bihealth.org',
        }
        good_users = [
            self.superuser,
            self.as_owner.user,  # Owner of link
            self.as_delegate.user,
        ]
        bad_users = [
            self.as_contributor.user,
            self.as_guest.user,
            self.user_no_roles,
        ]
        self.assert_response_api(
            url, good_users, 200, method='PUT', data=request_data
        )
        self.assert_response_api(
            url, bad_users, 403, method='PUT', data=request_data
        )
        self.assert_response_api(
            url, self.anonymous, 401, method='PUT', data=request_data
        )
        self.assert_response_api(
            url, good_users, 200, method='PUT', data=request_data, knox=True
        )

    def test_hyperlink_update_patch(self):
        """Test permissions for hyperlink updating with PATCH"""
        url = reverse(
            'filesfolders:api_hyperlink_retrieve_update_destroy',
            kwargs={'hyperlink': self.hyperlink.sodar_uuid},
        )
        request_data = {'name': 'UPDATED Hyperlink'}
        good_users = [
            self.superuser,
            self.as_owner.user,  # Owner of link
            self.as_delegate.user,
        ]
        bad_users = [
            self.as_contributor.user,
            self.as_guest.user,
            self.user_no_roles,
        ]
        self.assert_response_api(
            url, good_users, 200, method='PATCH', data=request_data
        )
        self.assert_response_api(
            url, bad_users, 403, method='PATCH', data=request_data
        )
        self.assert_response_api(
            url, self.anonymous, 401, method='PATCH', data=request_data
        )
        self.assert_response_api(
            url, good_users, 200, method='PATCH', data=request_data, knox=True
        )

    def test_hyperlink_destroy(self):
        """Test permissions for hyperlink destroying with DELETE"""
        obj_uuid = uuid.uuid4()
        url = reverse(
            'filesfolders:api_hyperlink_retrieve_update_destroy',
            kwargs={'hyperlink': obj_uuid},
        )

        def _make_hyperlink():
            link = self._make_hyperlink(
                name='New Link',
                url='http://www.duckduckgo.com/',
                project=self.project,
                folder=None,
                owner=self.as_owner.user,
                description='',
            )
            link.sodar_uuid = obj_uuid
            link.save()

        good_users = [
            self.superuser,
            self.as_owner.user,  # Owner of link
            self.as_delegate.user,
        ]
        bad_users = [
            self.as_contributor.user,
            self.as_guest.user,
            self.user_no_roles,
        ]
        _make_hyperlink()
        self.assert_response_api(
            url,
            good_users,
            204,
            method='DELETE',
            cleanup_method=_make_hyperlink,
        )
        self.assert_response_api(url, bad_users, 403, method='DELETE')
        self.assert_response_api(url, self.anonymous, 401, method='DELETE')
        self.assert_response_api(
            url,
            good_users,
            204,
            method='DELETE',
            cleanup_method=_make_hyperlink,
            knox=True,
        )
