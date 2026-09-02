import json
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from gaf_core.audit_constants import AuditAction, AuditResourceType, get_client_ip
from gaf_core.mixins import AuditMixin, audit_action, build_diff_details
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import RoleBasedPermission
from resources.import_utils import (
    create_or_update_pack,
    create_pack_zip,
    get_destination_dir,
    get_resources_root,
    migrate_resource_pack,
    read_manifest,
)
from resources.models import ResourcePack, Tag, TemplateAnnotation, TemplateEffectiveness, TemplateVersion
from resources.serializers import (
    ResourcePackSerializer,
    RoiFullSerializer,
    RoiSerializer,
    RoiTaskSerializer,
    TagSerializer,
    TemplateAnnotationSerializer,
    TemplateEffectivenessSerializer,
    TemplateVersionSerializer,
)
from resources.validators import validate_resource_pack, validate_resource_pack_structure

logger = logging.getLogger(__name__)


def _safe_extract_zip(zf: zipfile.ZipFile, dest_dir: str) -> None:
    """Extract a ZIP file with path-traversal validation (zip-slip prevention).

    Validates that every member path resolves within ``dest_dir`` before
    extraction, preventing malicious archives from writing outside the
    target directory via ``../../`` sequences.
    """
    dest_path = Path(dest_dir).resolve()
    for info in zf.infolist():
        target = (dest_path / info.filename).resolve()
        if not str(target).startswith(str(dest_path)):
            raise ValueError(
                f"Refusing to extract '{info.filename}': path traversal detected "
                f"(resolves outside {dest_dir})"
            )
    zf.extractall(dest_dir)


# TD-268: path params used by roi_task/roi_delete actions are not
# ResourcePack model fields — declare them per action so spectacular does
# not default to "string" with a warning.
_ROI_TASK_PARAMETERS = [
    OpenApiParameter(
        name='task_name',
        type=OpenApiTypes.STR,
        location=OpenApiParameter.PATH,
        description='Task name (or "public" for the public group)',
        required=True,
    ),
]

_ROI_DELETE_PARAMETERS = [
    OpenApiParameter(
        name='task_name',
        type=OpenApiTypes.STR,
        location=OpenApiParameter.PATH,
        description='Task name (or "public" for the public group)',
        required=True,
    ),
    OpenApiParameter(
        name='roi_name',
        type=OpenApiTypes.STR,
        location=OpenApiParameter.PATH,
        description='ROI name to delete',
        required=True,
    ),
]


class ResourcePackSchema(AutoSchema):
    """Custom schema for ResourcePackViewSet.

    Generates per-HTTP-method operation_ids for the rois / roi_task /
    roi_delete actions so spectacular does not emit operationId collision
    warnings (TD-268).

    Background: ``@extend_schema(operation_id=...)`` sets the same operation_id
    for ALL HTTP methods of an action, so a multi-method action (e.g.
    ``methods=['get', 'put']``) would collide with itself on the same URL.
    Overriding ``get_operation_id`` here lets us differentiate by method.
    """

    _ROI_OP_IDS = {
        ('rois', 'get'): 'resources_resource_packs_rois_retrieve',
        ('rois', 'put'): 'resources_resource_packs_rois_replace',
        ('roi_task', 'get'): 'resources_resource_packs_roi_task_retrieve',
        ('roi_task', 'put'): 'resources_resource_packs_roi_task_replace',
        ('roi_task', 'post'): 'resources_resource_packs_roi_task_add',
        ('roi_delete', 'delete'): 'resources_resource_packs_roi_delete',
    }

    def get_operation_id(self) -> str:
        action = getattr(self.view, 'action', '')
        method = (self.method or '').lower()
        op_id = self._ROI_OP_IDS.get((action, method))
        if op_id:
            return op_id
        return super().get_operation_id()


class ResourcePackViewSet(AuditMixin, viewsets.ModelViewSet):
    """资源包管理视图集，支持导入/导出/校验/激活/模板列表等操作。"""

    queryset = ResourcePack.objects.all().select_related('game_profile').prefetch_related('custom_tasks', 'scheduled_tasks', 'templates')
    serializer_class = ResourcePackSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'
    filterset_fields = ['is_active', 'target_app']
    search_fields = ['name', 'author']
    audit_resource_type = AuditResourceType.RESOURCE_PACK
    # TD-268: per-method operation_ids for rois / roi_task / roi_delete
    # actions (see ResourcePackSchema._ROI_OP_IDS).
    schema = ResourcePackSchema()

    def get_permissions(self):
        """写操作需要 manage 权限。"""
        if self.action in (
            'create', 'update', 'partial_update', 'destroy',
            'activate', 'deactivate', 'import_pack',
        ):
            self.required_permission = 'manage'
        elif self.action in ('rois', 'roi_task', 'roi_delete') and self.request.method in ('PUT', 'POST', 'DELETE'):
            # R37-P2 C3: ROI write ops require manage; GET stays at view.
            self.required_permission = 'manage'
        else:
            self.required_permission = 'view'
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        """上传/导入资源包，支持 ZIP 文件或目录路径。"""
        directory_path = request.data.get('directory_path', '')
        zip_file = request.FILES.get('zip_file')

        if not directory_path and not zip_file:
            return Response(
                {'detail': '请提供 directory_path 或 zip_file'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if zip_file:
            return self._import_from_zip(request, zip_file)

        return self._import_from_directory(request, directory_path)

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build audit details for ResourcePack writes.

        ``config_data`` is excluded — it can carry arbitrary user config and
        is not auditable field-by-field. ``directory_path`` is included for
        traceability (where the pack was imported from).
        """
        snapshot_keys = ("name", "version", "is_active", "target_app", "directory_path")
        if action == AuditAction.CREATE:
            return {"after": {k: getattr(instance, k) for k in snapshot_keys}}
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k) for k in snapshot_keys},
                after={k: getattr(instance, k) for k in snapshot_keys},
            )
        if action == AuditAction.DELETE:
            return {"before": {k: getattr(instance, k) for k in snapshot_keys}}
        return {}

    def _import_from_zip(self, request, zip_file):
        """Import a resource pack from an uploaded ZIP file.

        TD-004 (Option A): The extracted files are placed directly under the
        project `resources/<pack_name>/` directory. No copy is made under
        `MEDIA_ROOT/resource_packs/`. The database record points to the
        canonical `resources/` location.

        Args:
            request: HTTP request object.
            zip_file: Uploaded ZIP file object.

        Returns:
            Response with the created/updated ResourcePack.
        """
        temp_dir = tempfile.mkdtemp(prefix='gaf_import_')
        try:
            with zipfile.ZipFile(zip_file, 'r') as zf:
                _safe_extract_zip(zf, temp_dir)

            pack_dir = _find_pack_root(temp_dir)
            validation = validate_resource_pack_structure(pack_dir)
            if not validation["valid"]:
                return Response(
                    {'detail': '资源包校验失败', 'errors': validation["errors"]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            manifest = read_manifest(pack_dir)
            dest_dir = get_destination_dir(manifest)
            if dest_dir.exists():
                shutil.rmtree(str(dest_dir), ignore_errors=True)
            shutil.copytree(pack_dir, str(dest_dir))

            resource_pack = create_or_update_pack(manifest, str(dest_dir), activate=False)
            # AuditMixin's perform_create is bypassed because this view
            # overrides ``create()`` to handle ZIP imports directly; log
            # the IMPORT action manually after the pack row is committed.
            if self.audit_log_create:
                self._log_audit(AuditAction.IMPORT, resource_pack)
            return Response(
                ResourcePackSerializer(resource_pack).data,
                status=status.HTTP_201_CREATED,
            )
        except zipfile.BadZipFile:
            return Response(
                {'detail': '无效的 ZIP 文件'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _import_from_directory(self, request, directory_path):
        """Import a resource pack from a directory path.

        TD-004 (Option A): If the provided directory is already under the
        project `resources/` tree, it is used in-place (the database record
        points to it). Otherwise the pack is copied into the canonical
        `resources/<pack_name>/` location so that `resources/` remains the
        single source of truth.

        Args:
            request: HTTP request object.
            directory_path: Resource pack directory path.

        Returns:
            Response with the created/updated ResourcePack.
        """
        if not os.path.isdir(directory_path):
            return Response(
                {'detail': f'目录不存在: {directory_path}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        validation = validate_resource_pack_structure(directory_path)
        if not validation["valid"]:
            return Response(
                {'detail': '资源包校验失败', 'errors': validation["errors"]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        manifest = read_manifest(directory_path)
        dest_dir = get_destination_dir(manifest)
        source_path = Path(directory_path)
        resources_root = get_resources_root()

        # If the source is outside resources/, copy it to the canonical location.
        try:
            source_path.relative_to(resources_root)
            in_resources = True
        except ValueError:
            in_resources = False

        if not in_resources:
            if dest_dir.exists():
                shutil.rmtree(str(dest_dir), ignore_errors=True)
            shutil.copytree(str(source_path), str(dest_dir))
            target_dir = str(dest_dir)
        else:
            target_dir = directory_path

        resource_pack = create_or_update_pack(manifest, target_dir, activate=False)
        # See _import_from_zip: log IMPORT manually (create() is overridden).
        if self.audit_log_create:
            self._log_audit(AuditAction.IMPORT, resource_pack)
        return Response(
            ResourcePackSerializer(resource_pack).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='activate')
    @audit_action(AuditAction.UPDATE, AuditResourceType.RESOURCE_PACK)
    def activate(self, request, pk=None):
        """激活指定资源包，同时取消其他资源包的激活状态。"""
        resource_pack = self.get_object()
        ResourcePack.objects.filter(is_active=True).update(is_active=False)
        resource_pack.is_active = True
        resource_pack.save(update_fields=['is_active', 'updated_at'])
        return Response(
            ResourcePackSerializer(resource_pack).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='deactivate')
    @audit_action(AuditAction.UPDATE, AuditResourceType.RESOURCE_PACK)
    def deactivate(self, request, pk=None):
        """停用指定资源包。"""
        resource_pack = self.get_object()
        resource_pack.is_active = False
        resource_pack.save(update_fields=['is_active', 'updated_at'])
        return Response(
            ResourcePackSerializer(resource_pack).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='validate')
    def validate(self, request, pk=None):
        """校验资源包的结构完整性和版本兼容性。"""
        resource_pack = self.get_object()
        result = validate_resource_pack(resource_pack)
        if result["valid"]:
            return Response(result, status=status.HTTP_200_OK)
        return Response(result, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='validate-path')
    def validate_path(self, request):
        """校验指定路径的资源包目录结构（导入前预校验）。"""
        directory_path = request.data.get('directory_path', '')
        if not directory_path:
            return Response(
                {'valid': False, 'errors': ['directory_path 不能为空']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = validate_resource_pack_structure(directory_path)
        if result["valid"]:
            return Response(result, status=status.HTTP_200_OK)
        return Response(result, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='scan')
    @audit_action(AuditAction.IMPORT, AuditResourceType.RESOURCE_PACK, resource_id_kw="")
    def scan_packs(self, request):
        """扫描 resources/ 目录下的所有子文件夹，将未导入的资源包注册到数据库。

        每个子文件夹应有 manifest.json 描述资源包元数据。
        已存在的资源包（同名同版本）会更新，不存在的会创建。
        """
        project_root = Path(settings.BASE_DIR).parent
        resources_dir = project_root / "resources"

        if not resources_dir.is_dir():
            return Response(
                {"detail": "资源目录不存在", "path": str(resources_dir)},
                status=status.HTTP_404_NOT_FOUND,
            )

        results = []
        for subdir in sorted(resources_dir.iterdir()):
            if not subdir.is_dir():
                continue
            result = migrate_resource_pack(str(subdir), activate=False, deep_import=True)
            result["name"] = subdir.name
            results.append(result)

        ghost_packs = []
        for pack in ResourcePack.objects.all():
            if pack.directory_path and not Path(pack.directory_path).is_dir():
                ghost_packs.append({"id": pack.id, "name": pack.name, "directory": pack.directory_path})

        success_count = sum(1 for r in results if "error" not in r)
        return Response({
            "total": len(results),
            "success": success_count,
            "failed": len(results) - success_count,
            "results": results,
            "ghost_packs": ghost_packs,
        })

    @action(detail=False, methods=['post'], url_path='create')
    def create_pack(self, request):
        """新建资源包，自动生成目录结构和 manifest.json。"""
        name = request.data.get('name', '').strip()
        version = request.data.get('version', '1.0').strip()
        target_app = request.data.get('target_app', '').strip()
        description = request.data.get('description', '').strip()

        if not name:
            return Response(
                {'detail': '资源包名称不能为空'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        import re
        if not re.match(r'^[\w\-\u4e00-\u9fff]+$', name):
            return Response(
                {'detail': '名称只能包含字母、数字、中文、横线和下划线'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        project_root = Path(settings.BASE_DIR).parent
        resources_dir = project_root / "resources"
        pack_dir = resources_dir / name

        if pack_dir.exists():
            existing = ResourcePack.objects.filter(name=name, version=version).first()
            if existing:
                return Response(
                    {'detail': f'同名同版本资源包已存在: {name} v{version}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        templates_dir = pack_dir / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)

        from django.utils import timezone
        manifest = {
            'name': name,
            'version': version,
            'description': description,
            'target_app': target_app if target_app else None,
            'author': request.user.username if request.user.is_authenticated else 'unknown',
            'created_at': timezone.now().isoformat(),
            'updated_at': timezone.now().isoformat(),
            'template_count': 0,
        }
        manifest_path = pack_dir / "manifest.json"
        import json
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        resource_pack = ResourcePack.objects.create(
            name=name,
            version=version,
            description=description,
            target_app=target_app if target_app else '',
            author=manifest['author'],
            directory_path=str(pack_dir),
            is_active=False,
        )
        # @audit_action cannot capture the new pack ID (detail=False URL has
        # no pk); log manually so resource_id is the actual new pack PK.
        if self.audit_log_create:
            self._log_audit(AuditAction.CREATE, resource_pack)

        return Response(
            ResourcePackSerializer(resource_pack).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['get'], url_path='export')
    def export(self, request, pk=None):
        """Export a resource pack as a .gafpack ZIP file.

        The zip is created on-demand from the canonical `resources/`
        directory (single source of truth) and stored under
        `MEDIA_ROOT/resource_pack_zips/` as a transient download artifact.
        """
        resource_pack = self.get_object()
        pack_dir = resource_pack.directory_path
        if not os.path.isdir(pack_dir):
            return Response(
                {'detail': '资源包目录不存在'},
                status=status.HTTP_404_NOT_FOUND,
            )

        manifest = read_manifest(Path(pack_dir))
        if manifest is None:
            return Response(
                {'detail': 'manifest.json 不存在或解析失败'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        zip_path = create_pack_zip(Path(pack_dir), manifest)
        if not zip_path or not os.path.isfile(zip_path):
            return Response(
                {'detail': '生成资源包 ZIP 失败'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        pack_filename = os.path.basename(zip_path)
        return FileResponse(
            open(zip_path, 'rb'),
            as_attachment=True,
            filename=pack_filename,
            content_type='application/zip',
        )

    @action(detail=True, methods=['get'], url_path='templates')
    def templates(self, request, pk=None):
        """获取资源包中的模板文件列表，按子目录分组。"""
        resource_pack = self.get_object()
        templates_dir = os.path.join(resource_pack.directory_path, 'templates')
        template_groups = {}
        if os.path.isdir(templates_dir):
            for root, _dirs, files in os.walk(templates_dir):
                rel_dir = os.path.relpath(root, templates_dir).replace('\\', '/')
                if rel_dir == '.':
                    rel_dir = 'root'
                group_files = [
                    f for f in files
                    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))
                ]
                if group_files:
                    template_groups[rel_dir] = sorted(group_files)
        return Response({'templates': template_groups}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='config')
    def config(self, request, pk=None):
        """获取资源包的配置文件内容（settings.json 和 rois.json）。"""
        resource_pack = self.get_object()
        config_dir = os.path.join(resource_pack.directory_path, 'config')
        config_data = {}

        settings_path = os.path.join(config_dir, 'settings.json')
        if os.path.isfile(settings_path):
            with open(settings_path, encoding='utf-8') as f:
                config_data['settings'] = json.load(f)

        rois_path = os.path.join(config_dir, 'rois.json')
        if os.path.isfile(rois_path):
            with open(rois_path, encoding='utf-8') as f:
                config_data['rois'] = json.load(f)

        legacy_path = os.path.join(resource_pack.directory_path, 'config.json')
        if os.path.isfile(legacy_path):
            with open(legacy_path, encoding='utf-8') as f:
                config_data['legacy'] = json.load(f)

        return Response({'config': config_data}, status=status.HTTP_200_OK)

    # -----------------------------------------------------------------------
    # R37-P2 C3 — ROI CRUD (file-based storage, no DB model)
    # -----------------------------------------------------------------------

    def _rois_path(self, resource_pack) -> str:
        """Return the absolute path to the pack's rois.json."""
        return os.path.join(resource_pack.directory_path, 'config', 'rois.json')

    def _read_rois(self, resource_pack) -> dict:
        """Read rois.json from the pack's config dir.

        Returns an empty structure ``{'public': {}, 'tasks': {}}`` when the
        file is missing or malformed so callers can safely mutate the result.
        """
        rois_path = self._rois_path(resource_pack)
        if not os.path.isfile(rois_path):
            return {'public': {}, 'tasks': {}}
        try:
            with open(rois_path, encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {'public': {}, 'tasks': {}}
        # Normalise: ensure both keys exist
        if not isinstance(data, dict):
            return {'public': {}, 'tasks': {}}
        data.setdefault('public', {})
        data.setdefault('tasks', {})
        return data

    def _write_rois(self, resource_pack, data: dict) -> None:
        """Write rois.json atomically (write-then-replace)."""
        rois_path = self._rois_path(resource_pack)
        os.makedirs(os.path.dirname(rois_path), exist_ok=True)
        # Write to a temp file then move, so a partial write does not
        # corrupt the existing rois.json if the process is interrupted.
        tmp_path = rois_path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, rois_path)

    def _get_task_rois(self, data: dict, task_name: str) -> dict:
        """Return the ROI map for a single task.

        ``task_name='public'`` returns the public group; any other value is
        looked up under ``data['tasks'][task_name]``. Returns an empty dict
        when the task does not exist.
        """
        if task_name == 'public':
            return data.get('public', {})
        return data.get('tasks', {}).get(task_name, {})

    def _set_task_rois(self, data: dict, task_name: str, rois: dict) -> None:
        """Write the ROI map for a single task back into the full structure."""
        if task_name == 'public':
            data['public'] = rois
        else:
            data.setdefault('tasks', {})[task_name] = rois

    @extend_schema(
        description='Get or replace the full rois.json for a resource pack.',
    )
    @action(detail=True, methods=['get', 'put'], url_path='rois')
    def rois(self, request, pk=None):
        """GET/PUT the full rois.json for a resource pack.

        GET /api/v2/resources/resource-packs/{pk}/rois/
            Returns ``{public: {name: [x,y,w,h]}, tasks: {task_name: {...}}}``.

        PUT /api/v2/resources/resource-packs/{pk}/rois/
            Replaces the entire rois.json with the request body. Write
            requires ``manage`` permission (enforced by get_permissions).
        """
        resource_pack = self.get_object()

        if request.method == 'GET':
            data = self._read_rois(resource_pack)
            return Response(data, status=status.HTTP_200_OK)

        # PUT — full replace
        serializer = RoiFullSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        # Normalise keys so the file always has both 'public' and 'tasks'
        normalized = {
            'public': validated.get('public', {}),
            'tasks': validated.get('tasks', {}),
        }
        self._write_rois(resource_pack, normalized)
        # Manual audit log (mixed GET/PUT endpoint — @audit_action would
        # also fire on GET). resource_type is RESOURCE_PACK since ROIs are
        # a child resource of the pack (no separate i18n key).
        self._log_roi_audit(request, AuditAction.UPDATE, str(resource_pack.pk), {
            'op': 'rois_replace',
            'task_name': '*',
        })
        return Response(normalized, status=status.HTTP_200_OK)

    @extend_schema(
        parameters=_ROI_TASK_PARAMETERS,
        description='Get/replace/add ROIs for a single task.',
    )
    @action(detail=True, methods=['get', 'put', 'post'], url_path=r'rois/(?P<task_name>[^/.]+)')
    def roi_task(self, request, pk=None, task_name=None):
        """GET/PUT/POST ROIs for a single task.

        GET /api/v2/resources/resource-packs/{pk}/rois/{task_name}/
            Returns ``{task_name: str, rois: {name: [x,y,w,h]}}``.

        PUT /api/v2/resources/resource-packs/{pk}/rois/{task_name}/
            Replaces all ROIs for the given task with the request body
            (a map of ``{name: [x,y,w,h]}``).

        POST /api/v2/resources/resource-packs/{pk}/rois/{task_name}/
            Adds a single ROI. Body: ``{name: str, coords: [x,y,w,h]}``.
            If a ROI with the same name exists it is overwritten.
        """
        resource_pack = self.get_object()
        data = self._read_rois(resource_pack)

        if request.method == 'GET':
            rois = self._get_task_rois(data, task_name)
            return Response(
                {'task_name': task_name, 'rois': rois},
                status=status.HTTP_200_OK,
            )

        if request.method == 'PUT':
            # Body is a map of {roi_name: [x,y,w,h]}
            serializer = RoiTaskSerializer(data={
                'task_name': task_name,
                'rois': request.data if isinstance(request.data, dict) else {},
            })
            serializer.is_valid(raise_exception=True)
            self._set_task_rois(data, task_name, serializer.validated_data['rois'])
            self._write_rois(resource_pack, data)
            self._log_roi_audit(request, AuditAction.UPDATE, str(resource_pack.pk), {
                'op': 'roi_task_replace',
                'task_name': task_name,
            })
            return Response(
                {'task_name': task_name, 'rois': serializer.validated_data['rois']},
                status=status.HTTP_200_OK,
            )

        # POST — add a single ROI
        serializer = RoiSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data['name']
        coords = serializer.validated_data['coords']

        task_rois = dict(self._get_task_rois(data, task_name))
        task_rois[name] = coords
        self._set_task_rois(data, task_name, task_rois)
        self._write_rois(resource_pack, data)
        self._log_roi_audit(request, AuditAction.CREATE, str(resource_pack.pk), {
            'op': 'roi_add',
            'task_name': task_name,
            'roi_name': name,
        })
        return Response(
            {'task_name': task_name, 'name': name, 'coords': coords},
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        parameters=_ROI_DELETE_PARAMETERS,
        description='Delete a single ROI from a task.',
    )
    @action(
        detail=True,
        methods=['delete'],
        url_path=r'rois/(?P<task_name>[^/.]+)/(?P<roi_name>[^/.]+)',
    )
    @audit_action(AuditAction.DELETE, AuditResourceType.RESOURCE_PACK)
    def roi_delete(self, request, pk=None, task_name=None, roi_name=None):
        """DELETE a single ROI from a task.

        DELETE /api/v2/resources/resource-packs/{pk}/rois/{task_name}/{roi_name}/
            Removes the named ROI from the given task. Returns 404 if the
            ROI does not exist.
        """
        resource_pack = self.get_object()
        data = self._read_rois(resource_pack)
        task_rois = self._get_task_rois(data, task_name)

        if roi_name not in task_rois:
            return Response(
                {'detail': f'ROI {roi_name!r} not found in task {task_name!r}'},
                status=status.HTTP_404_NOT_FOUND,
            )

        del task_rois[roi_name]
        # _get_task_rois returned a reference into `data` for the tasks dict;
        # for the 'public' group it's data['public'] (same reference). So the
        # del above already mutated `data`. Write it back.
        self._write_rois(resource_pack, data)
        return Response(
            {'deleted': roi_name, 'task_name': task_name},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='test')
    @audit_action(AuditAction.EXECUTE, AuditResourceType.RESOURCE_PACK)
    def test(self, request, pk=None):
        """直接测试资源包: 在指定窗口上运行资源包关联的某个任务.

        ``POST /api/v2/resource-packs/{pk}/test/``

        Body:
            - ``task_id`` (int, required): 要运行的 Task ID
            - ``device_id`` (int, optional): 目标窗口 Device ID.
                省略时由 execute_task 从 task.device_mappings 取默认.
            - ``game_account_id`` (int, optional): 游戏账号 ID.
                省略时自动创建默认账号绑定此资源包.

        效果等价于 ``POST /api/v2/tasks/{task_id}/execute/`` 传入
        ``resource_pack_id``, 但更直观 — 用户从资源包出发, 更符合
        「已登录, 直接测试资源包」的心智模型.
        """
        from tasks.serializers import TaskExecuteSerializer
        from tasks.services import TaskBindingError, execute_task

        resource_pack = self.get_object()
        serializer = TaskExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        task_id = serializer.validated_data.get('task_id')
        if not task_id:
            return Response(
                {'detail': 'task_id 是必填字段'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from tasks.models import Task
        try:
            task = Task.objects.get(pk=task_id)
        except Task.DoesNotExist:
            return Response(
                {'detail': f'Task {task_id} 不存在'},
                status=status.HTTP_404_NOT_FOUND,
            )

        device_id = serializer.validated_data.get('device_id')
        game_account_id = serializer.validated_data.get('game_account_id')

        try:
            execution = execute_task(
                task,
                agent_id=serializer.validated_data.get('agent_id'),
                user=request.user,
                device_id=device_id,
                game_account_id=game_account_id,
                resource_pack_id=resource_pack.id,
            )
        except TaskBindingError as exc:
            return Response(
                {'detail': exc.message},
                status=exc.status_code,
            )

        from tasks.serializers import TaskExecutionSerializer
        return Response(
            TaskExecutionSerializer(execution).data,
            status=status.HTTP_201_CREATED,
        )

    def _log_roi_audit(self, request, action, resource_id, details):
        """Write an audit log row for ROI write operations.

        ROI writes are file-based (``rois.json`` under the pack directory),
        so they bypass ``AuditMixin.perform_*``. We log directly via
        ``accounts.audit.log_audit`` with ``resource_type=RESOURCE_PACK``
        (ROIs are a child resource of the pack; no separate i18n key).
        ``details`` carries the operation kind so auditors can distinguish
        replace / add / delete at a glance.
        """
        from accounts.audit import log_audit

        log_audit(
            user=getattr(request, 'user', None),
            action=action,
            resource_type=AuditResourceType.RESOURCE_PACK,
            resource_id=resource_id,
            details=details,
            ip_address=get_client_ip(request),
        )


class TemplateVersionViewSet(AuditMixin, viewsets.ModelViewSet):
    """Viewset for TemplateVersion model with create and restore actions."""

    queryset = TemplateVersion.objects.all().select_related('created_by', 'template')
    serializer_class = TemplateVersionSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'execute'
    audit_resource_type = AuditResourceType.TEMPLATE_VERSION

    def create(self, request, *args, **kwargs):
        """Create a new version snapshot of a template.

        Auto-increments version_number for the template and saves current
        template state as snapshot_data.
        """
        template_id = request.data.get('template')
        if not template_id:
            return Response(
                {'detail': 'template ID is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from resources.models import Template
            template = Template.objects.get(id=template_id)
        except Template.DoesNotExist:
            return Response(
                {'detail': f'Template not found: id={template_id}'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Auto-increment version number
        last_version = TemplateVersion.objects.filter(
            template=template
        ).order_by('-version_number').first()
        new_version_number = (last_version.version_number + 1) if last_version else 1

        # Build snapshot data from current template state
        snapshot_data = {
            'name': template.name,
            'image_path': template.image_path,
            'template_type': template.template_type,
            'match_threshold': template.match_threshold,
            'is_active': template.is_active,
            'tags': list(template.tags.values_list('id', flat=True)),
        }

        version = TemplateVersion.objects.create(
            template=template,
            version_number=new_version_number,
            snapshot_data=snapshot_data,
            comment=request.data.get('comment', ''),
            created_by=request.user,
        )
        # Custom create() bypasses AuditMixin.perform_create — log manually
        # so the snapshot row is auditable (IMPORT = snapshot taken from
        # the live template).
        if self.audit_log_create:
            self._log_audit(AuditAction.IMPORT, version)

        serializer = self.get_serializer(version)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build audit details for TemplateVersion writes."""
        snapshot_keys = ("version_number", "comment", "template_id", "created_by_id")
        if action == AuditAction.CREATE or action == AuditAction.IMPORT:
            return {"after": {k: getattr(instance, k) for k in snapshot_keys}}
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k) for k in snapshot_keys},
                after={k: getattr(instance, k) for k in snapshot_keys},
            )
        if action == AuditAction.DELETE:
            return {"before": {k: getattr(instance, k) for k in snapshot_keys}}
        return {}

    @action(detail=True, methods=['post'], url_path='restore')
    @audit_action(AuditAction.UPDATE, AuditResourceType.TEMPLATE_VERSION)
    def restore(self, request, pk=None):
        """Restore a template from this version snapshot.

        Applies the snapshot_data back to the template.
        """
        version = self.get_object()
        template = version.template
        snapshot = version.snapshot_data

        # Restore template fields from snapshot
        if 'name' in snapshot:
            template.name = snapshot['name']
        if 'image_path' in snapshot:
            template.image_path = snapshot['image_path']
        if 'template_type' in snapshot:
            template.template_type = snapshot['template_type']
        if 'match_threshold' in snapshot:
            template.match_threshold = snapshot['match_threshold']
        if 'is_active' in snapshot:
            template.is_active = snapshot['is_active']

        template.save()

        # Restore tags if present in snapshot
        if 'tags' in snapshot:
            template.tags.set(snapshot['tags'])

        return Response({
            'detail': f'Template restored to version {version.version_number}',
            'version': TemplateVersionSerializer(version).data,
        }, status=status.HTTP_200_OK)


class TagViewSet(AuditMixin, viewsets.ModelViewSet):
    """Viewset for Tag model with search support."""

    queryset = Tag.objects.all().prefetch_related('templates')
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'manage'
    search_fields = ['name']
    audit_resource_type = AuditResourceType.TAG

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build audit details for Tag writes."""
        snapshot_keys = ("name",)
        if action == AuditAction.CREATE:
            return {"after": {k: getattr(instance, k) for k in snapshot_keys}}
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k) for k in snapshot_keys},
                after={k: getattr(instance, k) for k in snapshot_keys},
            )
        if action == AuditAction.DELETE:
            return {"before": {k: getattr(instance, k) for k in snapshot_keys}}
        return {}


class TemplateAnnotationViewSet(AuditMixin, viewsets.ModelViewSet):
    """Viewset for TemplateAnnotation model (R37-P1).

    Exposes CRUD at /api/v2/resources/annotations/. Supports `?template=<id>`
    filter for listing annotations of a single template (used by
    TemplateAnnotationPage Tab 2). Also exposes a batch-delete action at
    /api/v2/resources/annotations/batch-delete/ for clearing all annotations
    of a template before re-import.
    """

    queryset = TemplateAnnotation.objects.all()
    serializer_class = TemplateAnnotationSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'
    filterset_fields = ['template', 'annotation_type']
    search_fields = ['label']
    audit_resource_type = AuditResourceType.TEMPLATE_ANNOTATION

    def get_permissions(self):
        """Write operations require manage permission."""
        if self.action in (
            'create', 'update', 'partial_update', 'destroy', 'batch_delete',
        ):
            self.required_permission = 'manage'
        else:
            self.required_permission = 'view'
        return super().get_permissions()

    def get_queryset(self):
        """Allow filtering by ?template=<id> in addition to filterset_fields."""
        qs = super().get_queryset().select_related('template')
        template_id = self.request.query_params.get('template')
        if template_id:
            qs = qs.filter(template_id=template_id)
        return qs

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build audit details for TemplateAnnotation writes."""
        snapshot_keys = ("template_id", "annotation_type", "label")
        if action == AuditAction.CREATE:
            return {"after": {k: getattr(instance, k) for k in snapshot_keys}}
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k) for k in snapshot_keys},
                after={k: getattr(instance, k) for k in snapshot_keys},
            )
        if action == AuditAction.DELETE:
            return {"before": {k: getattr(instance, k) for k in snapshot_keys}}
        return {}

    @action(detail=False, methods=['post'], url_path='batch-delete')
    @audit_action(AuditAction.DELETE, AuditResourceType.TEMPLATE_ANNOTATION, resource_id_kw="")
    def batch_delete(self, request):
        """Delete all annotations matching the given template_id.

        POST /api/v2/resources/annotations/batch-delete/
        Body: {"template_id": <int>}
        Returns: {"deleted": <int>}
        """
        template_id = request.data.get('template_id')
        if not template_id:
            return Response(
                {'detail': 'template_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deleted_count, _ = TemplateAnnotation.objects.filter(
            template_id=template_id
        ).delete()
        return Response({'deleted': deleted_count}, status=status.HTTP_200_OK)


@extend_schema(
    tags=['resources'],
    summary='Batch import templates from ZIP into a resource pack',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def template_batch_import_view(request):
    """
    Batch import templates from a ZIP file into a resource pack.

    POST /api/resources/templates/batch-import/
    Body: multipart/form-data { zip_file, pack_id }
    Extracts image files from ZIP and saves them to the target pack's templates directory.
    """
    # @api_view allowed: file upload + ZIP extraction into filesystem, not model CRUD
    zip_file = request.FILES.get('zip_file')
    pack_id = request.data.get('pack_id')

    if not zip_file:
        return Response(
            {'detail': '请提供 zip_file'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not pack_id:
        return Response(
            {'detail': '请提供 pack_id'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        resource_pack = ResourcePack.objects.get(id=pack_id)
    except ResourcePack.DoesNotExist:
        return Response(
            {'detail': f'资源包不存在: id={pack_id}'},
            status=status.HTTP_404_NOT_FOUND,
        )

    templates_dir = os.path.join(resource_pack.directory_path, 'templates')
    os.makedirs(templates_dir, exist_ok=True)

    temp_dir = tempfile.mkdtemp(prefix='gaf_batch_import_')
    imported_count = 0
    skipped_count = 0
    errors = []

    try:
        with zipfile.ZipFile(zip_file, 'r') as zf:
            file_list = zf.namelist()
            image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}

            for fname in file_list:
                basename = os.path.basename(fname)
                if not basename:
                    continue

                ext = os.path.splitext(basename)[1].lower()
                if ext not in image_extensions:
                    skipped_count += 1
                    continue

                try:
                    data = zf.read(fname)
                    dest_path = os.path.join(templates_dir, basename)
                    with open(dest_path, 'wb') as df:
                        df.write(data)
                    imported_count += 1
                except Exception as e:
                    logger.warning("import_templates: failed to import %s: %s", fname, e)
                    errors.append(f'{fname}: {str(e)}')

        return Response({
            'imported': imported_count,
            'skipped': skipped_count,
            'errors': errors[:10],
            'pack_name': resource_pack.name,
        }, status=status.HTTP_200_OK)

    except zipfile.BadZipFile:
        return Response(
            {'detail': '无效的 ZIP 文件'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@extend_schema(
    tags=['resources'],
    summary='Check template references before disable/delete',
    responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def template_references_view(request):
    """
    Check template references before disable/delete.

    GET /api/resources/templates/{id}/references/
    Returns counts of dependent records (annotations, effectiveness, etc.)
    """
    # @api_view allowed: cross-model reference aggregation (Template + Annotation + TemplateEffectiveness)
    from resources.models import Template

    template_id = request.query_params.get('id')
    if not template_id:
        return Response(
            {'detail': 'Missing id parameter'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        template = Template.objects.get(id=template_id)
    except Template.DoesNotExist:
        return Response(
            {'detail': f'Template not found: id={template_id}'},
            status=status.HTTP_404_NOT_FOUND,
        )

    references = {
        'annotations': template.annotations.count(),
        'template_name': template.name,
        'pack_name': template.resource_pack.name,
    }

    try:
        references['effectiveness_records'] = TemplateEffectiveness.objects.filter(
            template=template
        ).count()
    except Exception:
        logger.warning("check_template_references: TemplateEffectiveness query failed", exc_info=True)
        references['effectiveness_records'] = 0

    has_references = any(
        v > 0 for k, v in references.items() if k not in ('template_name', 'pack_name')
    )

    return Response({
        'template_id': int(template_id),
        'has_references': has_references,
        'references': references,
    }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['resources'],
    summary='List templates from resource pack filesystem',
    responses={200: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter(
            name='pack_id',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description='Filter templates by resource pack id',
        ),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def resource_templates_view(request):
    """
    资源包模板列表 API。

    GET /api/resources/templates/?pack_id=N
    从 ResourcePack 的文件系统中读取模板列表，可按 pack_id 过滤。
    """
    # @api_view allowed: walks resource pack filesystem to list template image files, not model CRUD
    pack_id = request.query_params.get('pack_id')
    packs = ResourcePack.objects.all()
    if pack_id:
        packs = packs.filter(id=pack_id)

    templates = []
    for rp in packs:
        templates_dir = os.path.join(rp.directory_path, 'templates') if rp.directory_path else ''
        if templates_dir and os.path.isdir(templates_dir):
            for root, _dirs, files in os.walk(templates_dir):
                for f in files:
                    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                        rel_path = os.path.relpath(os.path.join(root, f), templates_dir)
                        fpath = os.path.join(root, f)
                        # TD-004 (Option A): serve template image directly from resources/
                        image_url = f'/api/v2/resources/templates/files/{rp.id}/{rel_path.replace(chr(92), "/")}'
                        templates.append({
                            'id': len(templates) + 1,
                            'pack_id': rp.id,
                            'pack_name': rp.name,
                            'name': rel_path.replace('\\', '/'),
                            'thumbnail_url': image_url,
                            'image_url': image_url,
                            'match_threshold': 0.85,
                            'region_info': '[0, 0, 1080, 1920]',
                            'is_valid': rp.is_active and os.path.getsize(fpath) > 0,
                            'tag_ids': [],
                            'updated_at': rp.updated_at.isoformat() if rp.updated_at else None,
                        })

    return Response({'results': templates, 'total': len(templates)})


@extend_schema(
    tags=['resources'],
    summary='Resource pack validation status aggregation',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def resource_validation_view(request):
    """
    资源包验证状态 API。

    GET /api/resources/validation/
    从 ResourcePack 表查询各资源包的模板文件数量和有效性状态。
    """
    # @api_view allowed: aggregates template file validity across resource packs (custom report)
    from django.utils import timezone

    packs = ResourcePack.objects.all()
    results = []
    for rp in packs:
        templates_dir = os.path.join(rp.directory_path, 'templates') if rp.directory_path else ''
        template_count = 0
        valid_count = 0
        if templates_dir and os.path.isdir(templates_dir):
            for root, _dirs, files in os.walk(templates_dir):
                for f in files:
                    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                        template_count += 1
                        fpath = os.path.join(root, f)
                        if os.path.getsize(fpath) > 0:
                            valid_count += 1

        invalid_count = template_count - valid_count
        if template_count == 0:
            status_label = 'stale'
        elif invalid_count == 0:
            status_label = 'ok'
        elif invalid_count >= template_count * 0.5:
            status_label = 'stale'
        else:
            status_label = 'partial'

        results.append({
            'pack_id': rp.id,
            'pack_name': rp.name,
            'total_count': template_count,
            'valid_count': valid_count,
            'invalid_count': invalid_count,
            'status': status_label,
            'last_validated_at': rp.updated_at.isoformat() if rp.updated_at else None,
        })

    return Response({
        'results': results,
        'total': len(results),
        'last_validated': timezone.now().isoformat(),
    })


@extend_schema(
    tags=['resources'],
    summary='Resource pack version history and change log',
    responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def resource_pack_version_history_view(request, pk=None):
    """
    Resource pack version history and change log API.

    GET /api/resources/resource-packs/{id}/version-history/
    Returns version information and recent update history for a specific resource pack.
    """
    # @api_view allowed: custom version history report (model + filesystem aggregation)
    from resources.models import ResourcePack

    if not pk:
        return Response(
            {'detail': 'Missing resource pack ID'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        pack = ResourcePack.objects.get(pk=pk)
    except ResourcePack.DoesNotExist:
        return Response(
            {'detail': f'Resource pack {pk} not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    version_info = {
        'pack_id': pack.id,
        'pack_name': pack.name,
        'current_version': pack.version or '1.0.0',
        'description': pack.description,
        'created_at': pack.created_at.isoformat() if pack.created_at else None,
        'updated_at': pack.updated_at.isoformat() if pack.updated_at else None,
        'template_count': 0,
        'is_active': pack.is_active,
    }

    templates_dir = os.path.join(pack.directory_path, 'templates') if pack.directory_path else ''
    if templates_dir and os.path.isdir(templates_dir):
        version_info['template_count'] = sum(
            1 for f in os.listdir(templates_dir)
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))
        )

    return Response(version_info)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_pack_root(search_dir):
    """Locate the resource pack root inside an extracted/imported directory.

    A valid root contains manifest.json. If the top-level directory contains
    manifest.json, it is returned. Otherwise we look one level deeper for a
    single subdirectory that contains manifest.json (common ZIP layout).

    Args:
        search_dir: Directory to search (Path or string).

    Returns:
        str: Path to the pack root directory.

    Raises:
        ValueError: If no manifest.json is found.
    """
    search_path = Path(search_dir)
    if (search_path / "manifest.json").is_file():
        return str(search_path)

    subdirs = [d for d in search_path.iterdir() if d.is_dir()]
    if len(subdirs) == 1 and (subdirs[0] / "manifest.json").is_file():
        return str(subdirs[0])

    raise ValueError(f"manifest.json not found in {search_dir}")


@extend_schema(
    tags=['resources'],
    summary='Serve a template image file from resources/',
    responses={
        (200, 'image/png'): OpenApiTypes.BINARY,
        (200, 'image/jpeg'): OpenApiTypes.BINARY,
        (200, 'image/webp'): OpenApiTypes.BINARY,
        404: OpenApiTypes.OBJECT,
    },
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def template_file_view(request, pack_id, file_path):
    """Serve a template image file from the canonical resources/ directory.

    TD-004 (Option A): Template images are served directly from
    `resources/<pack_name>/templates/<file_path>`. The database only stores
    metadata; no MEDIA_ROOT copy is required.

    Args:
        request: HTTP request.
        pack_id: ResourcePack primary key.
        file_path: Relative path inside the pack's templates/ directory.

    Returns:
        FileResponse for the image file.
    """
    try:
        pack = ResourcePack.objects.get(pk=pack_id)
    except ResourcePack.DoesNotExist:
        raise Http404("Resource pack not found") from None

    if not pack.directory_path:
        raise Http404("Resource pack has no directory_path")

    # Resolve the requested file under pack.directory_path/templates/.
    base_dir = Path(pack.directory_path).resolve()
    templates_dir = (base_dir / "templates").resolve()
    requested_path = (templates_dir / file_path).resolve()

    # Traversal protection: requested_path must be inside templates_dir.
    try:
        requested_path.relative_to(templates_dir)
    except ValueError as exc:
        raise Http404("Invalid file path") from exc

    if not requested_path.is_file():
        raise Http404("Template file not found")

    content_type = _guess_image_content_type(requested_path.suffix)
    return FileResponse(
        open(requested_path, 'rb'),
        content_type=content_type,
    )


def _guess_image_content_type(ext):
    """Return a MIME type for common image extensions."""
    mapping = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.bmp': 'image/bmp',
        '.webp': 'image/webp',
    }
    return mapping.get(ext.lower(), 'application/octet-stream')


class TemplateEffectivenessViewSet(viewsets.ReadOnlyModelViewSet):
    """模板有效性视图集，提供模板匹配成功率统计。

    R37-P3 Stage 7 Task 20a: migrated from tasks app. ReadOnly — effectiveness
    records are populated by the execution engine, not by direct API writes.
    """

    queryset = TemplateEffectiveness.objects.all().select_related('template')
    serializer_class = TemplateEffectivenessSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'
    filterset_fields = ['is_suspected_invalid', 'consecutive_failures']
    search_fields = ['template_name']


# ---------------------------------------------------------------------------
# R37-P2 真实模板匹配预览 — 后端 cv2.matchTemplate（替换标注页硬编码 mock）
# ---------------------------------------------------------------------------

def _decode_image_b64(b64: str):
    """解码裸 base64 或 data URL 图片，失败返回 None。"""
    import base64 as _b64

    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    if "," in b64 and b64.startswith("data:"):
        b64 = b64.split(",", 1)[1]
    try:
        raw = _b64.b64decode(b64)
    except Exception:  # noqa: BLE001
        return None
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img if img is not None else None


def _nms_boxes(boxes: list[dict], iou_threshold: float = 0.3) -> list[dict]:
    """按置信度排序 + 贪心 NMS 去重叠框。"""
    ordered = sorted(boxes, key=lambda b: b["confidence"], reverse=True)
    kept: list[dict] = []
    for cand in ordered:
        overlap = False
        for k in kept:
            ax1, ay1 = cand["x"], cand["y"]
            ax2, ay2 = cand["x"] + cand["w"], cand["y"] + cand["h"]
            bx1, by1 = k["x"], k["y"]
            bx2, by2 = k["x"] + k["w"], k["y"] + k["h"]
            inter_w = max(0, min(ax2, bx2) - max(ax1, bx1))
            inter_h = max(0, min(ay2, by2) - max(ay1, by1))
            inter = inter_w * inter_h
            union = cand["w"] * cand["h"] + k["w"] * k["h"] - inter
            if union > 0 and inter / union > iou_threshold:
                overlap = True
                break
        if not overlap:
            kept.append(cand)
    return kept


@extend_schema(
    tags=["resources"],
    summary="Real-time template match preview (R37-P2, cv2)",
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def template_match_preview_view(request):
    """对给定截图执行真实模板匹配（cv2.matchTemplate）。

    body::

        {
          "image_base64": "<裸 base64 或 data URL>",   # 设备实时截图帧
          "template_base64": "<裸 base64 或 data URL>", # 标注裁剪/资源包模板
          "threshold": 0.8                              # 可选，默认 0.8
        }

    返回 ``{"matches": [{"x","y","w","h","confidence"}...]}``（图片像素
    坐标系，最多 5 个，已 NMS 去重叠）。R37-P2 占位升级：标注页"匹配预览"
    从此调真实 cv2 而非硬编码 mock。
    """
    try:
        image_b64 = str(request.data.get("image_base64") or "").strip()
        template_b64 = str(request.data.get("template_base64") or "").strip()
    except (AttributeError, KeyError):
        return Response({"matches": [], "error": "invalid body"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        threshold = float(request.data.get("threshold", 0.8))
    except (TypeError, ValueError):
        threshold = 0.8

    if not image_b64 or not template_b64:
        return Response({"matches": [], "error": "image_base64 and template_base64 are required"},
                        status=status.HTTP_400_BAD_REQUEST)

    image = _decode_image_b64(image_b64)
    template = _decode_image_b64(template_b64)
    if image is None or template is None:
        return Response({"matches": [], "error": "failed to decode image or template"},
                        status=status.HTTP_400_BAD_REQUEST)

    img_h, img_w = image.shape[:2]
    tmpl_h, tmpl_w = template.shape[:2]
    if tmpl_w > img_w or tmpl_h > img_h:
        return Response({"matches": [], "error": "template larger than image"},
                        status=status.HTTP_400_BAD_REQUEST)

    import cv2  # noqa: PLC0415

    result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)

    matches: list[dict] = []
    ys, xs = result.shape[:2]
    for ty in range(ys):
        for tx in range(xs):
            conf = float(result[ty, tx])
            if conf >= threshold:
                matches.append({"x": tx, "y": ty, "w": tmpl_w, "h": tmpl_h, "confidence": round(conf, 4)})

    matches = _nms_boxes(matches)[:5]
    return Response({"matches": matches, "error": None})
