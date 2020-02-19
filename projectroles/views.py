"""UI views for the samplesheets app"""

import json
import re
import requests
import urllib.request

from django.apps import apps
from django.conf import settings
from django.core.urlresolvers import resolve
from django.contrib import auth
from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import (
    TemplateView,
    DetailView,
    UpdateView,
    CreateView,
    DeleteView,
    View,
)
from django.views.generic.edit import ModelFormMixin, FormView
from django.views.generic.detail import ContextMixin

from rules.contrib.views import PermissionRequiredMixin, redirect_to_login

from projectroles.app_settings import AppSettingAPI
from projectroles.email import (
    send_role_change_mail,
    send_invite_mail,
    send_accept_note,
    send_expiry_note,
    get_invite_subject,
    get_invite_body,
    get_invite_message,
    get_email_footer,
    get_role_change_body,
    get_role_change_subject,
)
from projectroles.forms import (
    ProjectForm,
    RoleAssignmentForm,
    ProjectInviteForm,
    RemoteSiteForm,
    RoleAssignmentOwnerTransferForm,
)
from projectroles.models import (
    Project,
    Role,
    RoleAssignment,
    ProjectInvite,
    RemoteSite,
    RemoteProject,
    SODAR_CONSTANTS,
    PROJECT_TAG_STARRED,
    SODARUser,
)
from projectroles.plugins import get_active_plugins, get_backend_api
from projectroles.project_tags import get_tag_state, remove_tag
from projectroles.remote_projects import RemoteProjectAPI
from projectroles.utils import get_expiry_date, get_display_name
from timeline.models import ProjectEvent

# Settings
SEND_EMAIL = settings.PROJECTROLES_SEND_EMAIL

# SODAR constants
PROJECT_TYPE_PROJECT = SODAR_CONSTANTS['PROJECT_TYPE_PROJECT']
PROJECT_TYPE_CATEGORY = SODAR_CONSTANTS['PROJECT_TYPE_CATEGORY']
PROJECT_ROLE_OWNER = SODAR_CONSTANTS['PROJECT_ROLE_OWNER']
PROJECT_ROLE_DELEGATE = SODAR_CONSTANTS['PROJECT_ROLE_DELEGATE']
SUBMIT_STATUS_OK = SODAR_CONSTANTS['SUBMIT_STATUS_OK']
SUBMIT_STATUS_PENDING = SODAR_CONSTANTS['SUBMIT_STATUS_PENDING']
SUBMIT_STATUS_PENDING_TASKFLOW = SODAR_CONSTANTS[
    'SUBMIT_STATUS_PENDING_TASKFLOW'
]
SITE_MODE_TARGET = SODAR_CONSTANTS['SITE_MODE_TARGET']
SITE_MODE_SOURCE = SODAR_CONSTANTS['SITE_MODE_SOURCE']
SITE_MODE_PEER = SODAR_CONSTANTS['SITE_MODE_PEER']
REMOTE_LEVEL_NONE = SODAR_CONSTANTS['REMOTE_LEVEL_NONE']
REMOTE_LEVEL_VIEW_AVAIL = SODAR_CONSTANTS['REMOTE_LEVEL_VIEW_AVAIL']
REMOTE_LEVEL_READ_INFO = SODAR_CONSTANTS['REMOTE_LEVEL_READ_INFO']
REMOTE_LEVEL_READ_ROLES = SODAR_CONSTANTS['REMOTE_LEVEL_READ_ROLES']
APP_SETTING_SCOPE_PROJECT = SODAR_CONSTANTS['APP_SETTING_SCOPE_PROJECT']

# Local constants
APP_NAME = 'projectroles'
SEARCH_REGEX = re.compile(r'^[a-zA-Z0-9.:\-_\s\t]+$')
ALLOWED_CATEGORY_URLS = ['detail', 'create', 'update', 'ajax_star']
KIOSK_MODE = getattr(settings, 'PROJECTROLES_KIOSK_MODE', False)


# API constants for internal SODAR Core apps


# Access Django user model
User = auth.get_user_model()

# App settings API
app_settings = AppSettingAPI()


# General mixins ---------------------------------------------------------------


class ProjectAccessMixin:
    """Mixin for providing access to a Project object from request kwargs"""

    #: The model class to use for projects.  You can override this to replace it
    #: with a proxy model, for example.
    project_class = Project

    def get_project(self, request=None, kwargs=None):
        """
        Return SODAR Project object based or None if not found, based on
        the current request and view kwargs. If arguments are not provided,
        uses self.request and/or self.kwargs.

        :param request: Request object (optional)
        :param kwargs: View kwargs (optional)
        :return: Object of project_class or None if not found
        """
        if not request:
            request = self.request

        if not kwargs:
            kwargs = self.kwargs

        # First check for a kwarg named 'project'
        if 'project' in kwargs:
            return self.project_class.objects.filter(
                sodar_uuid=kwargs['project']
            ).first()

        # Other object types
        model = None
        uuid_kwarg = None

        for k, v in kwargs.items():
            if re.match(r'[0-9a-f-]+', v):
                try:
                    app_name = resolve(request.path).app_name

                    if app_name.find('.') != -1:
                        app_name = app_name.split('.')[0]

                    model = apps.get_model(app_name, k)
                    uuid_kwarg = k
                    break

                except LookupError:
                    pass

        if not model:
            return None

        try:
            obj = model.objects.get(sodar_uuid=kwargs[uuid_kwarg])

            if hasattr(obj, 'project'):
                return obj.project

            # Some objects may have a get_project() func instead of foreignkey
            elif hasattr(obj, 'get_project') and callable(
                getattr(obj, 'get_project', None)
            ):
                return obj.get_project()

        except model.DoesNotExist:
            return None


class LoggedInPermissionMixin(PermissionRequiredMixin):
    """Mixin for handling redirection for both unlogged users and authenticated
    users without permissions"""

    def has_permission(self):
        """Override has_permission() for this mixin also to work with admin
        users without a permission object"""
        if KIOSK_MODE:
            return True

        try:
            return super().has_permission()

        except AttributeError:
            if self.request.user.is_superuser:
                return True

        return False

    def handle_no_permission(self):
        """Override handle_no_permission to redirect user"""
        if self.request.user.is_authenticated():
            messages.error(
                self.request, 'User not authorized for requested action'
            )
            return redirect(reverse('home'))

        else:
            return redirect_to_login(self.request.get_full_path())


class ProjectPermissionMixin(PermissionRequiredMixin, ProjectAccessMixin):
    """Mixin for providing a Project object and queryset for permission
    checking"""

    def get_permission_object(self):
        return self.get_project()

    def has_permission(self):
        """Overrides for project permission access"""
        project = self.get_project()

        # Disable project app access for categories
        if project and project.type == PROJECT_TYPE_CATEGORY:
            request_url = resolve(self.request.get_full_path())

            if (
                request_url.app_name != APP_NAME
                or request_url.url_name not in ALLOWED_CATEGORY_URLS
            ):
                return False

        # Disable access for non-owner/delegate if remote project is revoked
        if project and project.is_revoked():
            role_as = RoleAssignment.objects.filter(
                project=project, user=self.request.user
            ).first()

            if role_as and role_as.role.name not in [
                PROJECT_ROLE_OWNER,
                PROJECT_ROLE_DELEGATE,
            ]:
                return False

        return super().has_permission()

    def get_queryset(self, *args, **kwargs):
        """Override ``get_queryset()`` to filter down to the currently selected
        object."""
        qs = super().get_queryset(*args, **kwargs)

        if qs.model == ProjectAccessMixin.project_class:
            return qs

        elif hasattr(qs.model, 'get_project_filter_key'):
            return qs.filter(
                **{qs.model.get_project_filter_key(): self.get_project()}
            )

        elif hasattr(qs.model, 'project') or hasattr(qs.model, 'get_project'):
            return qs.filter(project=self.get_project())

        else:
            raise AttributeError(
                'Model does not have "project" member, get_project() function '
                'or "get_project_filter_key()" function'
            )


class ProjectModifyPermissionMixin(
    LoggedInPermissionMixin, ProjectPermissionMixin
):
    """Mixin for handling access to project modifying views, denying access even
    for local superusers if the project is remote and thus immutable"""

    def has_permission(self):
        """Override has_permission() to check remote project status"""
        perm = super().has_permission()
        project = self.get_project()
        return False if project.is_remote() else perm

    def handle_no_permission(self):
        """Override handle_no_permission to redirect user"""
        if self.request.user.is_authenticated():
            messages.error(
                self.request,
                'Modifications are not allowed for remote {}'.format(
                    get_display_name(PROJECT_TYPE_PROJECT, plural=True)
                ),
            )
            return redirect(reverse('home'))

        else:
            return redirect_to_login(self.request.get_full_path())


class RolePermissionMixin(ProjectModifyPermissionMixin):
    """Mixin to ensure permissions for RoleAssignment according to user role in
    project"""

    def has_permission(self):
        """Override has_permission to check perms depending on role"""
        if not super().has_permission():
            return False

        try:
            obj = RoleAssignment.objects.get(
                sodar_uuid=self.kwargs['roleassignment']
            )

            if obj.role.name == PROJECT_ROLE_OWNER:
                return False

            elif obj.role.name == PROJECT_ROLE_DELEGATE:
                return self.request.user.has_perm(
                    'projectroles.update_project_delegate',
                    self.get_permission_object(),
                )

            else:
                return self.request.user.has_perm(
                    'projectroles.update_project_members',
                    self.get_permission_object(),
                )

        except RoleAssignment.DoesNotExist:
            return False

    def get_permission_object(self):
        """Override get_permission_object for checking Project permission"""
        return self.get_project()


class HTTPRefererMixin:
    """Mixin for updating a correct referer url in session cookie regardless of
    page reload"""

    def get(self, request, *args, **kwargs):
        if 'HTTP_REFERER' in request.META:
            referer = request.META['HTTP_REFERER']

            if (
                'real_referer' not in request.session
                or referer != request.build_absolute_uri()
            ):
                request.session['real_referer'] = referer

        return super().get(request, *args, **kwargs)


class PluginContextMixin(ContextMixin):
    """Mixin for adding plugin list to context data"""

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['app_plugins'] = get_active_plugins(
            plugin_type='project_app', custom_order=True
        )
        return context


class ProjectContextMixin(
    HTTPRefererMixin, PluginContextMixin, ProjectAccessMixin
):
    """Mixin for adding context data to Project base view and other views
    extending it. Includes HTTPRefererMixin for correct referer URL"""

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        # Project
        if hasattr(self, 'object') and isinstance(self.object, Project):
            context['project'] = self.get_object()

        elif hasattr(self, 'object') and hasattr(self.object, 'project'):
            context['project'] = self.object.project

        else:
            context['project'] = self.get_project()

        # Project tagging/starring
        if 'project' in context and not KIOSK_MODE:
            context['project_starred'] = get_tag_state(
                context['project'], self.request.user, PROJECT_TAG_STARRED
            )

        return context


class APIPermissionMixin(PermissionRequiredMixin):
    """Mixin for handling permission response for API functions"""

    def handle_no_permission(self):
        """Override handle_no_permission to provide 403"""
        return HttpResponseForbidden()


class CurrentUserFormMixin:
    """Mixin for passing current user to form as current_user"""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'current_user': self.request.user})
        return kwargs


class LoginRequiredMixin(AccessMixin):
    """Customized variant of the one from ``django.contrib.auth.mixins``.
    Allows disabling by overriding function ``is_login_required``.
    """

    def dispatch(self, request, *args, **kwargs):
        if self.is_login_required() and not request.user.is_authenticated:
            return self.handle_no_permission()

        return super().dispatch(request, *args, **kwargs)

    def is_login_required(self):
        return False if KIOSK_MODE else True


# Base Project Views -----------------------------------------------------------


class HomeView(LoginRequiredMixin, PluginContextMixin, TemplateView):
    """Home view"""

    template_name = 'projectroles/home.html'


class ProjectDetailView(
    LoginRequiredMixin,
    LoggedInPermissionMixin,
    ProjectPermissionMixin,
    ProjectContextMixin,
    DetailView,
):
    """Project details view"""

    permission_required = 'projectroles.view_project'
    model = Project
    slug_url_kwarg = 'project'
    slug_field = 'sodar_uuid'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        if self.request.user.is_superuser:
            context['role'] = None

        else:
            try:
                role_as = RoleAssignment.objects.get(
                    user=self.request.user, project=self.object
                )

                context['role'] = role_as.role

            except RoleAssignment.DoesNotExist:
                context['role'] = None

        if settings.PROJECTROLES_SITE_MODE == SITE_MODE_SOURCE:
            # TODO: See issue #197
            context['target_projects'] = RemoteProject.objects.filter(
                project_uuid=self.object.sodar_uuid, site__mode=SITE_MODE_TARGET
            ).order_by('site__name')
        elif settings.PROJECTROLES_SITE_MODE == SITE_MODE_TARGET:
            # TODO: See issue #197
            context['peer_projects'] = RemoteProject.objects.filter(
                project_uuid=self.object.sodar_uuid, site__mode=SITE_MODE_PEER
            ).order_by('site__name')

        return context


class ProjectSearchView(LoginRequiredMixin, TemplateView):
    """View for displaying results of search within projects"""

    template_name = 'projectroles/search.html'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        plugins = get_active_plugins(plugin_type='project_app')

        search_input = self.request.GET.get('s').strip()
        context['search_input'] = search_input

        search_split = search_input.split(' ')
        search_term = search_split[0].strip()
        search_type = None
        search_keywords = {}

        for i in range(1, len(search_split)):
            s = search_split[i].strip()

            if ':' in s:
                kw = s.split(':')[0].lower().strip()
                val = s.split(':')[1].lower().strip()

                if kw == 'type':
                    search_type = val

                else:
                    search_keywords[kw] = val

            elif s != '':
                search_term += ' ' + s

        context['search_term'] = search_term
        context['search_type'] = search_type
        context['search_keywords'] = search_keywords

        # Get project results
        if not search_type or search_type == 'project':
            context['project_results'] = [
                p
                for p in Project.objects.find(
                    search_term, project_type='PROJECT'
                )
                if self.request.user.has_perm('projectroles.view_project', p)
            ]

        # Get app results
        if search_type:
            search_apps = sorted(
                [
                    p
                    for p in plugins
                    if (p.search_enable and search_type in p.search_types)
                ],
                key=lambda x: x.plugin_ordering,
            )

        else:
            search_apps = sorted(
                [p for p in plugins if p.search_enable],
                key=lambda x: x.plugin_ordering,
            )

        context['app_search_data'] = []

        for plugin in search_apps:
            context['app_search_data'].append(
                {
                    'plugin': plugin,
                    'results': plugin.search(
                        search_term,
                        self.request.user,
                        search_type,
                        search_keywords,
                    ),
                }
            )

        return context

    def get(self, request, *args, **kwargs):
        if not getattr(settings, 'PROJECTROLES_ENABLE_SEARCH', False):
            messages.error(request, 'Search not enabled')
            return redirect('home')

        context = self.get_context_data(*args, **kwargs)

        # Check input, redirect if unwanted characters are found
        if not bool(re.match(SEARCH_REGEX, context['search_input'])):
            messages.error(request, 'Please check your search input')
            return redirect('home')

        return super().render_to_response(context)


# Project Editing Views --------------------------------------------------------


class ProjectModifyMixin(ModelFormMixin):
    """Mixin for Project creation/updating"""

    @staticmethod
    def _get_old_project_data(project):
        return {
            'title': project.title,
            'description': project.description,
            'readme': project.readme.raw,
            'owner': project.get_owner().user,
        }

    @staticmethod
    def _get_project_update_data(old_data, project, owner, project_settings):
        extra_data = {}
        upd_fields = []

        if old_data['title'] != project.title:
            extra_data['title'] = project.title
            upd_fields.append('title')

        if old_data['owner'] != owner:
            extra_data['owner'] = owner.username
            upd_fields.append('owner')

        if old_data['description'] != project.description:
            extra_data['description'] = project.description
            upd_fields.append('description')

        if old_data['readme'] != project.readme.raw:
            extra_data['readme'] = project.readme.raw
            upd_fields.append('readme')

        # Settings
        for k, v in project_settings.items():
            a_name = k.split('.')[1]
            s_name = k.split('.')[2]
            s_def = app_settings.get_setting_def(s_name, app_name=a_name)
            old_v = app_settings.get_app_setting(a_name, s_name, project)

            if s_def['type'] == 'JSON':
                v = json.loads(v)

            if old_v != v:
                extra_data[k] = v
                upd_fields.append(k)

        return extra_data, upd_fields

    def _submit_with_taskflow(
        self, project, owner, project_settings, form_action, tl_event
    ):
        """Submit project modification flow via SODAR Taskflow"""
        taskflow = get_backend_api('taskflow')

        if tl_event:
            tl_event.set_status('SUBMIT')

        flow_data = {
            'project_title': project.title,
            'project_description': project.description,
            'parent_uuid': str(project.parent.sodar_uuid)
            if project.parent
            else 0,
            'owner_username': owner.username,
            'owner_uuid': str(owner.sodar_uuid),
            'owner_role_pk': Role.objects.get(name=PROJECT_ROLE_OWNER).pk,
            'settings': project_settings,
        }

        if form_action == 'update':
            old_owner = project.get_owner().user
            flow_data['old_owner_uuid'] = str(old_owner.sodar_uuid)
            flow_data['old_owner_username'] = old_owner.username
            flow_data['project_readme'] = project.readme.raw

        try:
            taskflow.submit(
                project_uuid=str(project.sodar_uuid),
                flow_name='project_{}'.format(form_action),
                flow_data=flow_data,
                request=self.request,
            )

        except (
            requests.exceptions.ConnectionError,
            taskflow.FlowSubmitException,
        ) as ex:
            # NOTE: No need to update status as project will be deleted
            if form_action == 'create':
                project.delete()

            elif tl_event:  # Update
                tl_event.set_status('FAILED', str(ex))

            messages.error(self.request, str(ex))

            if form_action == 'create' and project.parent:
                redirect_url = reverse(
                    'projectroles:detail',
                    kwargs={'project': project.parent.sodar_uuid},
                )

            elif form_action == 'create':  # No parent
                redirect_url = reverse('home')

            else:  # Update
                redirect_url = reverse(
                    'projectroles:detail',
                    kwargs={'project': project.sodar_uuid},
                )

            return HttpResponseRedirect(redirect_url)

    def _handle_local_save(self, project, owner, project_settings):
        """Handle local saving of project data if SODAR Taskflow is not
        enabled"""

        # Modify owner role if it does exist
        try:
            assignment = RoleAssignment.objects.get(
                project=project, role__name=PROJECT_ROLE_OWNER
            )
            assignment.user = owner
            assignment.save()

        # Else create a new one
        except RoleAssignment.DoesNotExist:
            assignment = RoleAssignment(
                project=project,
                user=owner,
                role=Role.objects.get(name=PROJECT_ROLE_OWNER),
            )
            assignment.save()

        # Modify settings
        for k, v in project_settings.items():
            app_settings.set_app_setting(
                app_name=k.split('.')[1],
                setting_name=k.split('.')[2],
                value=v,
                project=project,
                validate=False,
            )  # Already validated in form

    def form_valid(self, form):
        """Handle project updating if form is valid"""
        taskflow = get_backend_api('taskflow')
        timeline = get_backend_api('timeline_backend')

        use_taskflow = (
            True
            if taskflow
            and form.cleaned_data.get('type') == PROJECT_TYPE_PROJECT
            else False
        )

        tl_event = None
        form_action = 'update' if self.object else 'create'
        old_data = {}

        app_plugins = [p for p in get_active_plugins() if p.app_settings]

        if self.object:
            project = self.get_object()
            old_data = self._get_old_project_data(project)  # Store old data
            project.title = form.cleaned_data.get('title')
            project.description = form.cleaned_data.get('description')
            project.type = form.cleaned_data.get('type')
            project.readme = form.cleaned_data.get('readme')

        else:
            project = Project(
                title=form.cleaned_data.get('title'),
                description=form.cleaned_data.get('description'),
                type=form.cleaned_data.get('type'),
                parent=form.cleaned_data.get('parent'),
                readme=form.cleaned_data.get('readme'),
            )

        if form_action == 'create':
            project.submit_status = (
                SUBMIT_STATUS_PENDING_TASKFLOW
                if use_taskflow
                else SUBMIT_STATUS_PENDING
            )
            project.save()  # Always save locally if creating (to get uuid)

        else:
            project.submit_status = SUBMIT_STATUS_OK

        # Save project with changes if updating without taskflow
        if form_action == 'update' and not use_taskflow:
            project.save()

        owner = form.cleaned_data.get('owner')
        type_str = project.type.capitalize()

        # Get settings
        project_settings = {}

        for plugin in app_plugins:
            p_settings = app_settings.get_setting_defs(
                APP_SETTING_SCOPE_PROJECT, plugin=plugin
            )

            for s_key, s_val in p_settings.items():
                s_name = 'settings.{}.{}'.format(plugin.name, s_key)

                if s_val['type'] == 'JSON':
                    project_settings[s_name] = json.dumps(
                        form.cleaned_data.get(s_name)
                    )

                else:
                    project_settings[s_name] = form.cleaned_data.get(s_name)

        if timeline:
            if form_action == 'create':
                tl_desc = (
                    'create ' + type_str.lower() + ' with {owner} as owner'
                )
                extra_data = {
                    'title': project.title,
                    'owner': owner.username,
                    'description': project.description,
                    'readme': project.readme.raw,
                }

                # Add settings to extra data
                for k, v in project_settings.items():
                    a_name = k.split('.')[1]
                    s_name = k.split('.')[2]
                    s_def = app_settings.get_setting_def(
                        s_name, app_name=a_name
                    )

                    if s_def['type'] == 'JSON':
                        v = json.loads(v)

                    extra_data[k] = v

            else:  # Update
                tl_desc = 'update ' + type_str.lower()
                extra_data, upd_fields = self._get_project_update_data(
                    old_data, project, owner, project_settings
                )

                if len(upd_fields) > 0:
                    tl_desc += ' (' + ', '.join(x for x in upd_fields) + ')'

            tl_event = timeline.add_event(
                project=project,
                app_name=APP_NAME,
                user=self.request.user,
                event_name='project_{}'.format(form_action),
                description=tl_desc,
                extra_data=extra_data,
            )

            if form_action == 'create':
                tl_event.add_object(owner, 'owner', owner.username)

        # Submit with Taskflow
        if use_taskflow:
            response = self._submit_with_taskflow(
                project, owner, project_settings, form_action, tl_event
            )

            if response:
                return response  # Exception encountered with Taskflow

        # Local save without Taskflow
        else:
            self._handle_local_save(project, owner, project_settings)

        # Post submit/save
        if form_action == 'create':
            project.submit_status = SUBMIT_STATUS_OK
            project.save()

        if SEND_EMAIL and (not self.object or old_data['owner'] != owner):
            # send mail
            send_role_change_mail(
                form_action,
                project,
                owner,
                RoleAssignment.objects.get_assignment(owner, project).role,
                self.request,
            )

        if tl_event:
            tl_event.set_status('OK')

        messages.success(self.request, '{} {}d.'.format(type_str, form_action))
        return HttpResponseRedirect(
            reverse(
                'projectroles:detail', kwargs={'project': project.sodar_uuid}
            )
        )


class ProjectCreateView(
    LoginRequiredMixin,
    LoggedInPermissionMixin,
    ProjectPermissionMixin,
    ProjectModifyMixin,
    ProjectContextMixin,
    HTTPRefererMixin,
    CurrentUserFormMixin,
    CreateView,
):
    """Project creation view"""

    permission_required = 'projectroles.create_project'
    model = Project
    form_class = ProjectForm

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        if 'project' in self.kwargs:
            context['parent'] = Project.objects.get(
                sodar_uuid=self.kwargs['project']
            )

        return context

    def get_form_kwargs(self):
        """Pass URL arguments to form"""
        kwargs = super().get_form_kwargs()
        kwargs.update(self.kwargs)
        return kwargs

    def get(self, request, *args, **kwargs):
        """Override get() to limit project creation under other projects"""

        # If site is in target mode and target creation is not allowed, redirect
        if (
            settings.PROJECTROLES_SITE_MODE == SITE_MODE_TARGET
            and not settings.PROJECTROLES_TARGET_CREATE
        ):
            messages.error(
                request,
                'Creating local {} not allowed'.format(
                    get_display_name(PROJECT_TYPE_PROJECT, plural=True)
                ),
            )
            return HttpResponseRedirect(reverse('home'))

        if 'project' in self.kwargs:
            project = Project.objects.get(sodar_uuid=self.kwargs['project'])

            if project.type != PROJECT_TYPE_CATEGORY:
                messages.error(
                    self.request,
                    'Creating nested {} is not allowed'.format(
                        get_display_name(PROJECT_TYPE_PROJECT, plural=True)
                    ),
                )
                return HttpResponseRedirect(
                    reverse(
                        'projectroles:detail',
                        kwargs={'project': project.sodar_uuid},
                    )
                )

        return super().get(request, *args, **kwargs)


class ProjectUpdateView(
    LoginRequiredMixin,
    ProjectModifyPermissionMixin,
    ProjectContextMixin,
    ProjectModifyMixin,
    CurrentUserFormMixin,
    UpdateView,
):
    """Project updating view"""

    permission_required = 'projectroles.update_project'
    model = Project
    form_class = ProjectForm
    slug_url_kwarg = 'project'
    slug_field = 'sodar_uuid'


# RoleAssignment Views ---------------------------------------------------------


class ProjectRoleView(
    LoginRequiredMixin,
    LoggedInPermissionMixin,
    ProjectPermissionMixin,
    ProjectContextMixin,
    TemplateView,
):
    """View for displaying project roles"""

    permission_required = 'projectroles.view_project_roles'
    template_name = 'projectroles/project_roles.html'
    model = Project

    def get_context_data(self, *args, **kwargs):
        project = self.get_project()
        context = super().get_context_data(*args, **kwargs)
        context['owner'] = project.get_owner()
        context['delegates'] = project.get_delegates()
        context['members'] = project.get_members()

        if project.is_remote():
            context[
                'remote_roles_url'
            ] = project.get_source_site().url + reverse(
                'projectroles:roles', kwargs={'project': project.sodar_uuid}
            )

        return context


class RoleAssignmentModifyMixin(ModelFormMixin):
    """Mixin for RoleAssignment creation and updating"""

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        change_type = self.request.resolver_match.url_name.split('_')[1]
        project = self.get_project()

        if change_type != 'delete':
            context['preview_subject'] = get_role_change_subject(
                change_type, project
            )
            context['preview_body'] = get_role_change_body(
                change_type=change_type,
                project=project,
                user_name='{user_name}',
                issuer=self.request.user,
                role_name='{role_name}',
                project_url=self.request.build_absolute_uri(
                    reverse(
                        'projectroles:detail',
                        kwargs={'project': project.sodar_uuid},
                    )
                ),
            ).replace('\n', '\\n')

        return context

    def form_valid(self, form):
        timeline = get_backend_api('timeline_backend')
        taskflow = get_backend_api('taskflow')

        form_action = 'update' if self.object else 'create'
        tl_event = None
        project = self.get_context_data()['project']
        user = form.cleaned_data.get('user')
        role = form.cleaned_data.get('role')
        use_taskflow = taskflow.use_taskflow(project) if taskflow else False

        # Init Timeline event
        if timeline:
            tl_desc = '{} role {}"{}" for {{{}}}'.format(
                form_action,
                'to ' if form_action == 'update' else '',
                role.name,
                'user',
            )

            tl_event = timeline.add_event(
                project=project,
                app_name=APP_NAME,
                user=self.request.user,
                event_name='role_{}'.format(form_action),
                description=tl_desc,
            )
            tl_event.add_object(user, 'user', user.username)

        # Submit with taskflow
        if use_taskflow:
            if tl_event:
                tl_event.set_status('SUBMIT')

            flow_data = {
                'username': user.username,
                'user_uuid': str(user.sodar_uuid),
                'role_pk': role.pk,
            }

            try:
                taskflow.submit(
                    project_uuid=project.sodar_uuid,
                    flow_name='role_update',
                    flow_data=flow_data,
                    request=self.request,
                )

            except taskflow.FlowSubmitException as ex:
                if tl_event:
                    tl_event.set_status('FAILED', str(ex))

                messages.error(self.request, str(ex))
                return redirect(
                    reverse(
                        'projectroles:roles',
                        kwargs={'project': project.sodar_uuid},
                    )
                )

            # Get object
            self.object = RoleAssignment.objects.get(project=project, user=user)

        # Local save without Taskflow
        else:
            if form_action == 'create':
                self.object = RoleAssignment(
                    project=project, user=user, role=role
                )

            else:
                self.object = RoleAssignment.objects.get(
                    project=project, user=user
                )
                self.object.role = role

            self.object.save()

        if SEND_EMAIL:
            send_role_change_mail(
                form_action, project, user, role, self.request
            )

        if tl_event:
            tl_event.set_status('OK')

        messages.success(
            self.request,
            'Membership {} for {} with the role of {}.'.format(
                'added' if form_action == 'create' else 'updated',
                self.object.user.username,
                self.object.role.name,
            ),
        )
        return redirect(
            reverse(
                'projectroles:roles',
                kwargs={'project': self.object.project.sodar_uuid},
            )
        )


class RoleAssignmentCreateView(
    LoginRequiredMixin,
    ProjectModifyPermissionMixin,
    ProjectContextMixin,
    CurrentUserFormMixin,
    RoleAssignmentModifyMixin,
    CreateView,
):
    """RoleAssignment creation view"""

    permission_required = 'projectroles.update_project_members'
    model = RoleAssignment
    form_class = RoleAssignmentForm

    def get_form_kwargs(self):
        """Pass URL arguments and current user to form"""
        kwargs = super().get_form_kwargs()
        kwargs.update(self.kwargs)
        return kwargs


class RoleAssignmentUpdateView(
    LoginRequiredMixin,
    RolePermissionMixin,
    ProjectContextMixin,
    RoleAssignmentModifyMixin,
    CurrentUserFormMixin,
    UpdateView,
):
    """RoleAssignment updating view"""

    permission_required = 'projectroles.update_project_members'
    model = RoleAssignment
    form_class = RoleAssignmentForm
    slug_url_kwarg = 'roleassignment'
    slug_field = 'sodar_uuid'


class RoleAssignmentDeleteView(
    LoginRequiredMixin,
    RolePermissionMixin,
    ProjectModifyPermissionMixin,
    ProjectContextMixin,
    CurrentUserFormMixin,
    DeleteView,
):
    """RoleAssignment deletion view"""

    permission_required = 'projectroles.update_project_members'
    model = RoleAssignment
    slug_url_kwarg = 'roleassignment'
    slug_field = 'sodar_uuid'

    def post(self, *args, **kwargs):
        timeline = get_backend_api('timeline_backend')
        taskflow = get_backend_api('taskflow')

        tl_event = None
        self.object = RoleAssignment.objects.get(
            sodar_uuid=kwargs['roleassignment']
        )
        project = self.object.project
        user = self.object.user
        role = self.object.role
        use_taskflow = taskflow.use_taskflow(project) if taskflow else False

        # Init Timeline event
        if timeline:
            tl_event = timeline.add_event(
                project=project,
                app_name=APP_NAME,
                user=self.request.user,
                event_name='role_delete',
                description='delete role "{}" from {{{}}}'.format(
                    role.name, 'user'
                ),
            )
            tl_event.add_object(user, 'user', user.username)

        # Submit with taskflow
        if use_taskflow:
            if tl_event:
                tl_event.set_status('SUBMIT')

            flow_data = {
                'username': user.username,
                'user_uuid': str(user.sodar_uuid),
                'role_pk': role.pk,
            }

            try:
                taskflow.submit(
                    project_uuid=project.sodar_uuid,
                    flow_name='role_delete',
                    flow_data=flow_data,
                    request=self.request,
                )
                self.object = None

            except taskflow.FlowSubmitException as ex:
                if tl_event:
                    tl_event.set_status('FAILED', str(ex))

                messages.error(self.request, str(ex))
                return HttpResponseRedirect(
                    redirect(
                        reverse(
                            'projectroles:roles',
                            kwargs={'project': project.sodar_uuid},
                        )
                    )
                )

        # Local save without Taskflow
        else:
            self.object.delete()

        if SEND_EMAIL:
            send_role_change_mail('delete', project, user, None, self.request)

        # Remove project star from user if it exists
        remove_tag(project=project, user=user)

        if tl_event:
            tl_event.set_status('OK')

        messages.success(
            self.request, 'Membership of {} removed.'.format(user.username)
        )

        return HttpResponseRedirect(
            reverse(
                'projectroles:roles', kwargs={'project': project.sodar_uuid}
            )
        )


class RoleAssignmentOwnerTransferView(
    LoginRequiredMixin,
    ProjectModifyPermissionMixin,
    CurrentUserFormMixin,
    ProjectContextMixin,
    FormView,
):
    permission_required = 'projectroles.update_project_owner'
    template_name = 'projectroles/roleassignment_owner_transfer.html'
    form_class = RoleAssignmentOwnerTransferForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        project = self.get_project()
        owner_as = RoleAssignment.objects.filter(
            project=project, role__name=PROJECT_ROLE_OWNER
        )[0]
        kwargs.update({'project': project, 'current_owner': owner_as.user})
        return kwargs

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        owner_as = RoleAssignment.objects.filter(
            project=self.get_project(), role__name=PROJECT_ROLE_OWNER
        )[0]
        context.update({'current_owner': owner_as.user})
        return context

    def form_valid(self, form):
        project = form.project
        prev_owner = form.current_owner
        prev_owner_ra = RoleAssignment.objects.get_assignment(
            prev_owner, project
        )

        new_owner = form.cleaned_data['new_owner']
        ex_owner_role = form.cleaned_data['ex_owner_role']

        timeline_event = self.create_timeline_event(
            prev_owner, new_owner, project
        )

        if self.transfer_ownership(
            timeline_event, project, prev_owner_ra, new_owner, ex_owner_role
        ):

            if SEND_EMAIL:
                send_role_change_mail(
                    'update', project, prev_owner, ex_owner_role, self.request
                )
                send_role_change_mail(
                    'update',
                    project,
                    new_owner,
                    Role.objects.get(name=PROJECT_ROLE_OWNER),
                    self.request,
                )
                messages.success(
                    self.request,
                    'Successfully transferred ownership  from {} to {}. A '
                    'notification email has been send to both users.'.format(
                        prev_owner.username, new_owner.username
                    ),
                )
            else:
                messages.success(
                    self.request,
                    'Successfully transferred ownership  from {} to {}.'.format(
                        prev_owner.username, new_owner.username
                    ),
                )

            if timeline_event:
                timeline_event.set_status('OK')

        return HttpResponseRedirect(
            reverse(
                'projectroles:roles', kwargs={'project': project.sodar_uuid}
            )
        )

    def create_timeline_event(
        self, prev_owner: SODARUser, new_owner: SODARUser, project: Project
    ) -> ProjectEvent:
        timeline = get_backend_api('timeline_backend')
        # Init Timeline event
        if not timeline:
            return None

        tl_desc = (
            'transfer ownership from {{prev_owner}} to '
            '{{new_owner}}'.format(prev_owner.username, new_owner.username)
        )

        tl_event = timeline.add_event(
            project=project,
            app_name=APP_NAME,
            user=self.request.user,
            event_name='role_transfer_owner',
            description=tl_desc,
            extra_data={
                'prev_owner': prev_owner.username,
                'new_owner': new_owner.username,
            },
        )
        tl_event.add_object(prev_owner, 'prev_owner', prev_owner.username)
        tl_event.add_object(new_owner, 'new_owner', new_owner.username)
        return tl_event

    def transfer_ownership(
        self,
        timeline_event: ProjectEvent,
        project: Project,
        prev_owner: RoleAssignment,
        new_owner: SODARUser,
        prev_owner_role: Role,
    ) -> bool:

        prev_owner.role = prev_owner_role
        prev_owner.save()

        # make it an owner
        ra = RoleAssignment.objects.get_assignment(new_owner, project)
        ra.role = Role.objects.get(name=PROJECT_ROLE_OWNER)
        ra.save()
        return True


# ProjectInvite Views ----------------------------------------------------------


class ProjectInviteMixin:
    """General utilities for mixins"""

    @classmethod
    def _handle_invite(cls, invite, request, resend=False):
        """
        Handle invite creation, email sending/resending and logging to timeline
        :param invite: ProjectInvite object
        :param request: Django request object
        :param resend: Send or resend (bool)
        """
        timeline = get_backend_api('timeline_backend')
        send_str = 'resend' if resend else 'send'
        status_type = 'OK'
        status_desc = None

        if SEND_EMAIL:
            sent_mail = send_invite_mail(invite, request)

            if sent_mail == 0:
                status_type = 'FAILED'
                status_desc = 'Email sending failed'

        else:
            status_type = 'FAILED'
            status_desc = 'PROJECTROLES_SEND_EMAIL not True'

        if status_type != 'OK' and not resend:
            status_desc += ', invite not created'

        # Add event in Timeline
        if timeline:
            timeline.add_event(
                project=invite.project,
                app_name=APP_NAME,
                user=request.user,
                event_name='invite_{}'.format(send_str),
                description='{} project invite with role "{}" to {}'.format(
                    send_str, invite.role.name, invite.email
                ),
                status_type=status_type,
                status_desc=status_desc,
            )

        if status_type == 'OK':
            messages.success(
                request,
                'Invite for "{}" role in {} sent to {}, expires on {}'.format(
                    invite.role.name,
                    invite.project.title,
                    invite.email,
                    timezone.localtime(invite.date_expire).strftime(
                        '%Y-%m-%d %H:%M'
                    ),
                ),
            )

        elif not resend:  # NOTE: Delete invite if send fails
            invite.delete()
            messages.error(request, status_desc)


class ProjectInviteView(
    LoginRequiredMixin,
    ProjectContextMixin,
    ProjectModifyPermissionMixin,
    TemplateView,
):
    """View for displaying and modifying project invites"""

    permission_required = 'projectroles.invite_users'
    template_name = 'projectroles/project_invites.html'
    model = ProjectInvite

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        context['invites'] = ProjectInvite.objects.filter(
            project=context['project'],
            active=True,
            date_expire__gt=timezone.now(),
        )

        return context


class ProjectInviteCreateView(
    LoginRequiredMixin,
    ProjectContextMixin,
    ProjectModifyPermissionMixin,
    ProjectInviteMixin,
    CurrentUserFormMixin,
    CreateView,
):
    """ProjectInvite creation view"""

    model = ProjectInvite
    form_class = ProjectInviteForm
    permission_required = 'projectroles.invite_users'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        project = self.get_permission_object()

        context['preview_subject'] = get_invite_subject(project)
        context['preview_body'] = get_invite_body(
            project=project,
            issuer=self.request.user,
            role_name='{role_name}',
            invite_url='http://XXXXXXXXXXXXXXXXXXXXXXX',
            date_expire_str='YYYY-MM-DD HH:MM',
        ).replace('\n', '\\n')
        context['preview_message'] = get_invite_message('{message}').replace(
            '\n', '\\n'
        )
        context['preview_footer'] = get_email_footer().replace('\n', '\\n')

        return context

    def get_form_kwargs(self):
        """Pass current user (and possibly mail address and role pk) to form"""
        kwargs = super().get_form_kwargs()
        kwargs.update({'project': self.get_permission_object().sodar_uuid})

        mail = self.request.GET.get('forwarded-email', None)
        role = self.request.GET.get('forwarded-role', None)

        kwargs.update({'mail': mail})
        kwargs.update({'role': role})

        return kwargs

    def form_valid(self, form):
        self.object = form.save()

        # Send mail and add to timeline
        self._handle_invite(invite=self.object, request=self.request)

        return redirect(
            reverse(
                'projectroles:invites',
                kwargs={'project': self.object.project.sodar_uuid},
            )
        )


class ProjectInviteAcceptView(LoginRequiredMixin, View):
    """View to handle accepting a project invite"""

    def get(self, *args, **kwargs):
        timeline = get_backend_api('timeline_backend')
        taskflow = get_backend_api('taskflow')
        tl_event = None

        def revoke_invite(invite, failed=True, fail_desc=''):
            """Set invite.active to False and save the invite"""
            invite.active = False
            invite.save()

            if failed and timeline:
                # Add event in Timeline
                timeline.add_event(
                    project=invite.project,
                    app_name=APP_NAME,
                    user=self.request.user,
                    event_name='invite_accept',
                    description='accept project invite',
                    status_type='FAILED',
                    status_desc=fail_desc,
                )

        # Get invite and ensure it actually exists
        try:
            invite = ProjectInvite.objects.get(secret=kwargs['secret'])

        except ProjectInvite.DoesNotExist:
            messages.error(self.request, 'Error: Invite does not exist!')
            return redirect(reverse('home'))

        # Check user does not already have a role
        try:
            RoleAssignment.objects.get(
                user=self.request.user, project=invite.project
            )
            messages.warning(
                self.request,
                'You already have roles set in this {}.'.format(
                    get_display_name(PROJECT_TYPE_PROJECT)
                ),
            )
            revoke_invite(
                invite,
                failed=True,
                fail_desc='User already has roles in {}'.format(
                    get_display_name(PROJECT_TYPE_PROJECT)
                ),
            )
            return redirect(
                reverse(
                    'projectroles:detail',
                    kwargs={'project': invite.project.sodar_uuid},
                )
            )

        except RoleAssignment.DoesNotExist:
            pass

        # Check expiration date
        if invite.date_expire < timezone.now():
            messages.error(
                self.request,
                'Error: Your invite has expired! '
                'Please contact the person who invited you: {} ({})'.format(
                    invite.issuer.name, invite.issuer.email
                ),
            )

            # Send notification of expiry to issuer
            if SEND_EMAIL:
                send_expiry_note(invite, self.request)

            revoke_invite(invite, failed=True, fail_desc='Invite expired')
            return redirect(reverse('home'))

        # If we get this far, create RoleAssignment..

        # Add event in Timeline
        if timeline:
            tl_event = timeline.add_event(
                project=invite.project,
                app_name=APP_NAME,
                user=self.request.user,
                event_name='invite_accept',
                description='accept project invite with role of "{}"'.format(
                    invite.role.name
                ),
            )

        # Submit with taskflow
        if taskflow:
            if tl_event:
                tl_event.set_status('SUBMIT')

            flow_data = {
                'username': self.request.user.username,
                'user_uuid': str(self.request.user.sodar_uuid),
                'role_pk': invite.role.pk,
            }

            try:
                taskflow.submit(
                    project_uuid=str(invite.project.sodar_uuid),
                    flow_name='role_update',
                    flow_data=flow_data,
                    request=self.request,
                )

            except taskflow.FlowSubmitException as ex:
                if tl_event:
                    tl_event.set_status('FAILED', str(ex))

                messages.error(self.request, str(ex))
                return redirect(reverse('home'))

            # Get object
            role_as = RoleAssignment.objects.get(
                project=invite.project, user=self.request.user
            )

            tl_event.set_status('OK')

        # Local save without Taskflow
        else:
            role_as = RoleAssignment(
                user=self.request.user, project=invite.project, role=invite.role
            )
            role_as.save()

            if tl_event:
                tl_event.set_status('OK')

        # ..notify the issuer by email..
        if SEND_EMAIL:
            send_accept_note(invite, self.request)

        # ..deactivate the invite..
        revoke_invite(invite, failed=False)

        # ..and finally redirect user to the project front page
        messages.success(
            self.request,
            'Welcome to {} "{}"! You have been assigned the role of '
            '{}.'.format(
                get_display_name(PROJECT_TYPE_PROJECT),
                invite.project.title,
                invite.role.name,
            ),
        )
        return redirect(
            reverse(
                'projectroles:detail',
                kwargs={'project': invite.project.sodar_uuid},
            )
        )


class ProjectInviteResendView(
    LoginRequiredMixin, ProjectModifyPermissionMixin, ProjectInviteMixin, View
):
    """View to handle resending a project invite"""

    permission_required = 'projectroles.invite_users'

    def get(self, *args, **kwargs):
        try:
            invite = ProjectInvite.objects.get(
                sodar_uuid=self.kwargs['projectinvite'], active=True
            )

        except ProjectInvite.DoesNotExist:
            messages.error(self.request, 'Error: Invite not found!')
            return redirect(
                reverse(
                    'projectroles:invites',
                    kwargs={'project': self.get_project()},
                )
            )

        # Reset invite expiration date
        invite.date_expire = get_expiry_date()
        invite.save()

        # Resend mail and add to timeline
        self._handle_invite(invite=invite, request=self.request, resend=True)

        return redirect(
            reverse(
                'projectroles:invites',
                kwargs={'project': invite.project.sodar_uuid},
            )
        )


class ProjectInviteRevokeView(
    LoginRequiredMixin,
    ProjectModifyPermissionMixin,
    ProjectContextMixin,
    TemplateView,
):
    """Batch delete/move confirm view"""

    template_name = 'projectroles/invite_revoke_confirm.html'
    permission_required = 'projectroles.invite_users'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['project'] = self.get_project()

        if 'projectinvite' in self.kwargs:
            try:
                context['invite'] = ProjectInvite.objects.get(
                    sodar_uuid=self.kwargs['projectinvite']
                )

            except ProjectInvite.DoesNotExist:
                pass

        return context

    def post(self, request, **kwargs):
        """Override post() to handle POST from confirmation template"""
        timeline = get_backend_api('timeline_backend')
        invite = None
        project = self.get_project()

        try:
            invite = ProjectInvite.objects.get(
                sodar_uuid=kwargs['projectinvite']
            )

            invite.active = False
            invite.save()
            messages.success(self.request, 'Invite revoked.')

        except ProjectInvite.DoesNotExist:
            messages.error(self.request, 'Error: Unable to revoke invite!')

        # Add event in Timeline
        if timeline and invite:
            timeline.add_event(
                project=project,
                app_name=APP_NAME,
                user=self.request.user,
                event_name='invite_revoke',
                description='revoke invite sent to "{}"'.format(
                    invite.email if invite else 'N/A'
                ),
                status_type='OK' if invite else 'FAILED',
            )

        return redirect(
            reverse(
                'projectroles:invites', kwargs={'project': project.sodar_uuid}
            )
        )


# Remote site and project views ------------------------------------------------


class RemoteSiteListView(
    LoginRequiredMixin, LoggedInPermissionMixin, TemplateView
):
    """Main view for displaying remote site list"""

    permission_required = 'projectroles.update_remote'
    template_name = 'projectroles/remote_sites.html'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        site_mode = (
            SITE_MODE_TARGET
            if settings.PROJECTROLES_SITE_MODE == SITE_MODE_SOURCE
            else SITE_MODE_SOURCE
        )

        sites = RemoteSite.objects.filter(mode=site_mode).order_by('name')

        if (
            sites.count() > 0
            and settings.PROJECTROLES_SITE_MODE == SITE_MODE_TARGET
        ):
            sites = sites[:1]

        context['sites'] = sites
        return context

    # TODO: Remove this once implementing #76
    def get(self, request, *args, **kwargs):
        if getattr(settings, 'PROJECTROLES_DISABLE_CATEGORIES', False):
            messages.warning(
                request,
                '{} {} and nesting disabled, '
                'remote {} sync disabled'.format(
                    get_display_name(PROJECT_TYPE_PROJECT, title=True),
                    get_display_name(PROJECT_TYPE_CATEGORY, plural=True),
                    get_display_name(PROJECT_TYPE_PROJECT),
                ),
            )
            return redirect('home')

        return super().get(request, *args, **kwargs)


class RemoteSiteModifyMixin(ModelFormMixin):
    def form_valid(self, form):
        if self.object:
            form_action = 'updated'

        elif settings.PROJECTROLES_SITE_MODE == 'TARGET':
            form_action = 'set'

        else:
            form_action = 'created'

        self.object = form.save()

        messages.success(
            self.request,
            '{} site "{}" {}'.format(
                self.object.mode.capitalize(), self.object.name, form_action
            ),
        )
        return HttpResponseRedirect(reverse('projectroles:remote_sites'))


class RemoteSiteCreateView(
    LoginRequiredMixin,
    LoggedInPermissionMixin,
    RemoteSiteModifyMixin,
    HTTPRefererMixin,
    CurrentUserFormMixin,
    CreateView,
):
    """RemoteSite creation view"""

    model = RemoteSite
    form_class = RemoteSiteForm
    permission_required = 'projectroles.update_remote'

    def get(self, request, *args, **kwargs):
        """Override get() to disallow rendering this view if current site is
        in TARGET mode and a source site already exists"""
        if (
            settings.PROJECTROLES_SITE_MODE == SITE_MODE_TARGET
            and RemoteSite.objects.filter(mode=SITE_MODE_SOURCE).count() > 0
        ):
            messages.error(request, 'Source site has already been set')
            return HttpResponseRedirect(reverse('projectroles:remote_sites'))

        return super().get(request, args, kwargs)


class RemoteSiteUpdateView(
    LoginRequiredMixin,
    LoggedInPermissionMixin,
    RemoteSiteModifyMixin,
    HTTPRefererMixin,
    CurrentUserFormMixin,
    UpdateView,
):
    """RemoteSite updating view"""

    model = RemoteSite
    form_class = RemoteSiteForm
    permission_required = 'projectroles.update_remote'
    slug_url_kwarg = 'remotesite'
    slug_field = 'sodar_uuid'


class RemoteSiteDeleteView(
    LoginRequiredMixin,
    LoggedInPermissionMixin,
    RemoteSiteModifyMixin,
    HTTPRefererMixin,
    CurrentUserFormMixin,
    DeleteView,
):
    """RemoteSite deletion view"""

    model = RemoteSite
    form_class = RemoteSiteForm
    permission_required = 'projectroles.update_remote'
    slug_url_kwarg = 'remotesite'
    slug_field = 'sodar_uuid'

    def get_success_url(self):
        messages.success(
            self.request,
            '{} site "{}" deleted'.format(
                self.object.mode.capitalize(), self.object.name
            ),
        )

        return reverse('projectroles:remote_sites')


class RemoteProjectListView(
    LoginRequiredMixin, LoggedInPermissionMixin, TemplateView
):
    """Main view for displaying a remote site's project list"""

    permission_required = 'projectroles.update_remote'
    template_name = 'projectroles/remote_projects.html'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        site = RemoteSite.objects.get(sodar_uuid=self.kwargs['remotesite'])
        context['site'] = site

        # Projects in SOURCE mode: all local projects of type PROJECT
        if settings.PROJECTROLES_SITE_MODE == SITE_MODE_SOURCE:
            projects = Project.objects.filter(type=PROJECT_TYPE_PROJECT)

        # Projects in TARGET mode: retrieve from source
        else:  # SITE_MODE_TARGET
            remote_uuids = [p.project_uuid for p in site.projects.all()]
            projects = Project.objects.filter(
                type=PROJECT_TYPE_PROJECT, sodar_uuid__in=remote_uuids
            )

        if projects:
            context['projects'] = sorted(
                [p for p in projects], key=lambda x: x.get_full_title()
            )

        return context


class RemoteProjectsBatchUpdateView(
    LoginRequiredMixin, LoggedInPermissionMixin, TemplateView
):
    """Manually created form view for updating project access in batch for a
    remote target site"""

    permission_required = 'projectroles.update_remote'
    template_name = 'projectroles/remoteproject_update.html'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        # Current site
        try:
            context['site'] = RemoteSite.objects.get(
                sodar_uuid=kwargs['remotesite']
            )

        except RemoteSite.DoesNotExist:
            pass

        return context

    def post(self, request, *args, **kwargs):
        context = self.get_context_data(*args, **kwargs)
        site = context['site']
        post_data = request.POST
        confirmed = True if 'update-confirmed' in post_data else False
        timeline = get_backend_api('timeline_backend')

        redirect_url = reverse(
            'projectroles:remote_projects',
            kwargs={'remotesite': site.sodar_uuid},
        )

        # Ensure site is in SOURCE mode
        if settings.PROJECTROLES_SITE_MODE != SITE_MODE_SOURCE:
            messages.error(
                request,
                'Site in TARGET mode, cannot update {} access'.format(
                    get_display_name(PROJECT_TYPE_PROJECT)
                ),
            )
            return HttpResponseRedirect(redirect_url)

        access_fields = {
            k: v for k, v in post_data.items() if k.startswith('remote_access')
        }

        ######################
        # Confirmation needed
        ######################

        if not confirmed:
            # Pass on (only) changed projects to confirmation form
            modifying_access = []

            for k, v in access_fields.items():
                remote_obj = None
                project_uuid = k.split('_')[2]

                try:
                    remote_obj = RemoteProject.objects.get(
                        site=site, project_uuid=project_uuid
                    )

                except RemoteProject.DoesNotExist:
                    pass

                if (not remote_obj and v != REMOTE_LEVEL_NONE) or (
                    remote_obj and remote_obj.level != v
                ):
                    modifying_access.append(
                        {
                            'project': Project.objects.get(
                                sodar_uuid=project_uuid
                            ),
                            'old_level': REMOTE_LEVEL_NONE
                            if not remote_obj
                            else remote_obj.level,
                            'new_level': v,
                        }
                    )

            if not modifying_access:
                messages.warning(
                    request,
                    'No changes to {} access detected'.format(
                        get_display_name(PROJECT_TYPE_PROJECT)
                    ),
                )
                return HttpResponseRedirect(redirect_url)

            context['modifying_access'] = modifying_access

            return super().render_to_response(context)

        ############
        # Confirmed
        ############

        for k, v in access_fields.items():
            project_uuid = k.split('_')[2]
            project = Project.objects.filter(sodar_uuid=project_uuid).first()

            # Update or create a RemoteProject object
            try:
                rp = RemoteProject.objects.get(
                    site=site, project_uuid=project_uuid
                )
                rp.level = v

            except RemoteProject.DoesNotExist:
                rp = RemoteProject(
                    site=site,
                    project_uuid=project_uuid,
                    project=project,
                    level=v,
                )

            rp.save()

            if timeline and project:
                tl_desc = 'update remote access for site {{{}}} to {}'.format(
                    'site',
                    v,
                    SODAR_CONSTANTS['REMOTE_ACCESS_LEVELS'][v].lower(),
                )

                tl_event = timeline.add_event(
                    project=project,
                    app_name=APP_NAME,
                    user=request.user,
                    event_name='update_remote',
                    description=tl_desc,
                    classified=True,
                    status_type='OK',
                )

                tl_event.add_object(site, 'site', site.name)

        # All OK
        messages.success(
            request,
            'Access level updated for {} {} in site "{}"'.format(
                len(access_fields.items()),
                get_display_name(
                    PROJECT_TYPE_PROJECT, count=len(access_fields.items())
                ),
                context['site'].name,
            ),
        )
        return HttpResponseRedirect(redirect_url)


class RemoteProjectsSyncView(
    LoginRequiredMixin, LoggedInPermissionMixin, TemplateView
):
    """Synchronize remote projects from a source site"""

    permission_required = 'projectroles.update_remote'
    template_name = 'projectroles/remoteproject_sync.html'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        # Current site
        try:
            context['site'] = RemoteSite.objects.get(
                sodar_uuid=kwargs['remotesite']
            )

        except RemoteSite.DoesNotExist:
            pass

        return context

    def get(self, request, *args, **kwargs):
        """Override get() for a confirmation view"""
        from projectroles.views_api import (
            CORE_API_MEDIA_TYPE,
            CORE_API_DEFAULT_VERSION,
        )

        remote_api = RemoteProjectAPI()
        redirect_url = reverse('projectroles:remote_sites')

        if settings.PROJECTROLES_SITE_MODE == SITE_MODE_SOURCE:
            messages.error(
                request, 'Site in SOURCE mode, remote sync not allowed'
            )
            return HttpResponseRedirect(redirect_url)

        context = self.get_context_data(*args, **kwargs)
        site = context['site']

        api_url = site.get_url() + reverse(
            'projectroles:api_remote_get', kwargs={'secret': site.secret}
        )

        try:
            api_req = urllib.request.Request(api_url)
            api_req.add_header(
                'accept',
                '{}; version={}'.format(
                    CORE_API_MEDIA_TYPE, CORE_API_DEFAULT_VERSION
                ),
            )
            response = urllib.request.urlopen(api_req)
            remote_data = json.loads(response.read().decode('utf-8'))

        except Exception as ex:
            ex_str = str(ex)

            if len(ex_str) >= 255:
                ex_str = ex_str[:255]

            messages.error(
                request,
                'Unable to synchronize {}: {}'.format(
                    get_display_name(PROJECT_TYPE_PROJECT, plural=True), ex_str
                ),
            )
            return HttpResponseRedirect(redirect_url)

        # Sync data
        update_data = remote_api.sync_source_data(site, remote_data, request)

        # Check for updates
        user_count = len(
            [v for v in update_data['users'].values() if 'status' in v]
        )
        project_count = len(
            [v for v in update_data['projects'].values() if 'status' in v]
        )
        role_count = 0

        for p in [p for p in update_data['projects'].values() if 'roles' in p]:
            for _ in [r for r in p['roles'].values() if 'status' in r]:
                role_count += 1

        # Redirect if no changes were detected
        if user_count == 0 and project_count == 0 and role_count == 0:
            messages.warning(
                request,
                'No changes in remote site detected, nothing to synchronize',
            )
            return HttpResponseRedirect(redirect_url)

        context['update_data'] = update_data
        context['user_count'] = user_count
        context['project_count'] = project_count
        context['role_count'] = role_count
        messages.success(
            request,
            '{} data updated according to source site'.format(
                get_display_name(PROJECT_TYPE_PROJECT, title=True)
            ),
        )
        return super().render_to_response(context)
