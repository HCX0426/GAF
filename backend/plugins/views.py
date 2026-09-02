"""插件管理 API 视图"""

import hashlib
import json
import logging
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

import yaml
from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from gaf_core.audit_constants import AuditAction, AuditResourceType, get_client_ip
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import RoleBasedPermission

from .models import PluginPackage, PluginSandbox

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


def _log_plugin_audit(request, action, resource_id, details):
    """Write an audit log row for Plugin write operations.

    Plugin views are plain ``APIView`` subclasses (not ``ModelViewSet``),
    so ``AuditMixin`` cannot be used here. We log directly via
    ``accounts.audit.log_audit`` with ``resource_type=PLUGIN``. The lazy
    import avoids the ``gaf_core`` ↔ ``accounts`` circular-import risk
    documented in ``gaf_core/mixins/audit.py``.
    """
    from accounts.audit import log_audit

    log_audit(
        user=getattr(request, 'user', None),
        action=action,
        resource_type=AuditResourceType.PLUGIN,
        resource_id=str(resource_id) if resource_id is not None else '',
        details=details or {},
        ip_address=get_client_ip(request),
    )


def _compute_checksum(file_path):
    """计算文件的 SHA-256 校验和"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def _validate_manifest(manifest_data):
    """校验 manifest 数据，返回 (is_valid, error_message)"""
    if not isinstance(manifest_data, dict):
        return False, 'manifest 格式无效，需为 YAML/JSON 对象'
    if not manifest_data.get('name'):
        return False, 'manifest 缺少 name 字段'
    if not manifest_data.get('version'):
        return False, 'manifest 缺少 version 字段'
    return True, None


def _serialize_plugin(pkg):
    """将 PluginPackage 实例序列化为字典"""
    manifest = pkg.manifest or {}
    latest_sandbox = pkg.sandboxes.order_by('-created_at').first()
    return {
        'id': pkg.id,
        'name': pkg.name,
        'version': pkg.version,
        'author': pkg.author,
        'description': pkg.description,
        'manifest': manifest,
        'is_installed': pkg.is_installed,
        'is_active': pkg.is_active,
        'installed_at': pkg.installed_at.isoformat() if pkg.installed_at else None,
        'checksum': pkg.checksum,
        'created_at': pkg.created_at.isoformat() if pkg.created_at else None,
        'updated_at': pkg.updated_at.isoformat() if pkg.updated_at else None,
        'sandbox_status': latest_sandbox.status if latest_sandbox else None,
        'sandbox_pid': latest_sandbox.pid if latest_sandbox else None,
    }


class PluginListView(APIView):
    """已安装插件列表"""

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT},
        description="List installed and uploaded-but-not-installed plugins.",
    )
    def get(self, request):
        """获取插件列表，返回已安装和已上传未安装的插件"""
        packages = PluginPackage.objects.all().prefetch_related('sandboxes')
        data = [_serialize_plugin(pkg) for pkg in packages]
        return Response(data)


class PluginUploadView(APIView):
    """上传插件包(.gafplugin zip)，校验 manifest"""

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'execute'

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
        description="Upload a .gafplugin ZIP package; validate manifest and save.",
    )
    def post(self, request):
        """上传插件包，验证 manifest 并保存"""
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({'error': '缺少上传文件'}, status=status.HTTP_400_BAD_REQUEST)

        file_name = uploaded_file.name
        if not file_name.endswith('.gafplugin'):
            return Response({'error': '仅支持 .gafplugin 格式的插件包'}, status=status.HTTP_400_BAD_REQUEST)

        tmp_file = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.gafplugin') as tmp:
                for chunk in uploaded_file.chunks():
                    tmp.write(chunk)
                tmp_file = tmp.name

            checksum = _compute_checksum(tmp_file)

            manifest_data = None
            with zipfile.ZipFile(tmp_file, 'r') as zf:
                names = zf.namelist()
                manifest_candidates = [n for n in names if n.endswith('manifest.yaml') or n.endswith('manifest.yml') or n.endswith('manifest.json')]
                if not manifest_candidates:
                    return Response({'error': '插件包中未找到 manifest.yaml/manifest.json'}, status=status.HTTP_400_BAD_REQUEST)

                manifest_name = manifest_candidates[0]
                raw_content = zf.read(manifest_name)
                content_str = raw_content.decode('utf-8', errors='replace')

                if manifest_name.endswith('.json'):
                    manifest_data = json.loads(content_str)
                else:
                    manifest_data = yaml.safe_load(content_str)

            valid, error_msg = _validate_manifest(manifest_data)
            if not valid:
                return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

            plugin_name = manifest_data['name']
            plugin_version = manifest_data['version']

            existing = PluginPackage.objects.filter(name=plugin_name).first()
            if existing and existing.is_installed:
                return Response(
                    {'error': f'插件 {plugin_name} 已安装，请先卸载后再上传新版本'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if existing:
                existing.version = plugin_version
                existing.author = manifest_data.get('author', '')
                existing.description = manifest_data.get('description', '')
                existing.manifest = manifest_data
                existing.package_path = tmp_file
                existing.checksum = checksum
                existing.save()
                # Upload of a new version for an existing (uninstalled)
                # plugin package — record as UPDATE since the row already
                # existed. ``checksum`` is included so auditors can verify
                # the binary content matches what was uploaded.
                _log_plugin_audit(request, AuditAction.UPDATE, existing.id, {
                    'op': 'upload_replace',
                    'name': existing.name,
                    'version': existing.version,
                    'checksum': existing.checksum,
                })
                return Response(_serialize_plugin(existing), status=status.HTTP_200_OK)

            pkg = PluginPackage.objects.create(
                name=plugin_name,
                version=plugin_version,
                author=manifest_data.get('author', ''),
                description=manifest_data.get('description', ''),
                manifest=manifest_data,
                package_path=tmp_file,
                checksum=checksum,
            )
            # New plugin upload = CREATE. ``checksum`` is safe to record
            # (it's a hash of the package, not the plugin's source code).
            _log_plugin_audit(request, AuditAction.CREATE, pkg.id, {
                'op': 'upload',
                'name': pkg.name,
                'version': pkg.version,
                'checksum': pkg.checksum,
            })
            return Response(_serialize_plugin(pkg), status=status.HTTP_201_CREATED)

        except (yaml.YAMLError, json.JSONDecodeError) as e:
            return Response({'error': f'manifest 解析失败: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        except zipfile.BadZipFile:
            return Response({'error': '无效的 zip 插件包'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error("PluginUpload: failed: %s", e, exc_info=True)
            if tmp_file and os.path.exists(tmp_file):
                os.unlink(tmp_file)
            return Response({'error': f'上传失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PluginInstallView(APIView):
    """安装插件"""

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'execute'

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
        description="Install a plugin package by id (extract zip into plugins_data).",
    )
    def post(self, request, pk):
        """安装指定插件包"""
        try:
            pkg = PluginPackage.objects.get(pk=pk)
        except PluginPackage.DoesNotExist:
            return Response({'error': '插件不存在'}, status=status.HTTP_404_NOT_FOUND)

        if pkg.is_installed:
            return Response({'error': '插件已安装'}, status=status.HTTP_400_BAD_REQUEST)

        if not pkg.package_path or not os.path.exists(pkg.package_path):
            return Response({'error': '插件包文件缺失'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            extract_dir = os.path.join(settings.BASE_DIR, 'plugins_data', pkg.name, pkg.version)
            os.makedirs(extract_dir, exist_ok=True)

            with zipfile.ZipFile(pkg.package_path, 'r') as zf:
                _safe_extract_zip(zf, extract_dir)

            pkg.is_installed = True
            pkg.installed_at = timezone.now()
            pkg.save()

            # Plugin install = CREATE (creates an installation record;
            # pkg row existed from upload but the install lifecycle event
            # is the auditable write).
            _log_plugin_audit(request, AuditAction.CREATE, pkg.id, {
                'op': 'install',
                'name': pkg.name,
                'version': pkg.version,
                'extract_dir': extract_dir,
            })
            return Response(_serialize_plugin(pkg))
        except Exception as e:
            logger.error("PluginInstall: failed: %s", e, exc_info=True)
            return Response({'error': f'安装失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PluginToggleView(APIView):
    """启用/禁用插件"""

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'execute'

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        description="Toggle a plugin's is_active flag (requires installed plugin).",
    )
    def post(self, request, pk):
        """切换插件启用/禁用状态"""
        try:
            pkg = PluginPackage.objects.get(pk=pk)
        except PluginPackage.DoesNotExist:
            return Response({'error': '插件不存在'}, status=status.HTTP_404_NOT_FOUND)

        if not pkg.is_installed:
            return Response({'error': '插件未安装，无法启用'}, status=status.HTTP_400_BAD_REQUEST)

        # Capture before-state so auditors can see enable vs disable.
        was_active = pkg.is_active
        pkg.is_active = not pkg.is_active
        pkg.save()
        _log_plugin_audit(request, AuditAction.UPDATE, pkg.id, {
            'op': 'toggle',
            'name': pkg.name,
            'version': pkg.version,
            'before_is_active': was_active,
            'after_is_active': pkg.is_active,
        })
        return Response(_serialize_plugin(pkg))


class PluginUninstallView(APIView):
    """卸载插件"""

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'execute'

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        description="Uninstall a plugin: delete extracted dir, package file, and DB row.",
    )
    def post(self, request, pk):
        """卸载并删除指定插件"""
        try:
            pkg = PluginPackage.objects.get(pk=pk)
        except PluginPackage.DoesNotExist:
            return Response({'error': '插件不存在'}, status=status.HTTP_404_NOT_FOUND)

        extract_dir = os.path.join(settings.BASE_DIR, 'plugins_data', pkg.name)
        if os.path.exists(extract_dir):
            import shutil
            shutil.rmtree(extract_dir, ignore_errors=True)

        if pkg.package_path and os.path.exists(pkg.package_path):
            os.unlink(pkg.package_path)

        # Snapshot plugin identity before deletion so the audit row is
        # meaningful after the row is gone.
        audit_details = {
            'op': 'uninstall',
            'name': pkg.name,
            'version': pkg.version,
            'was_installed': pkg.is_installed,
            'was_active': pkg.is_active,
        }
        plugin_id = pkg.id
        pkg.delete()
        _log_plugin_audit(request, AuditAction.DELETE, plugin_id, audit_details)
        return Response({'success': True, 'message': '插件已卸载'})


class PluginReloadView(APIView):
    """热重载插件"""

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'execute'

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
        description="Hot-reload a plugin: re-read manifest and recompute checksum.",
    )
    def post(self, request, pk):
        """热重载指定插件（重新读取 manifest 和配置）"""
        try:
            pkg = PluginPackage.objects.get(pk=pk)
        except PluginPackage.DoesNotExist:
            return Response({'error': '插件不存在'}, status=status.HTTP_404_NOT_FOUND)

        if not pkg.is_installed:
            return Response({'error': '插件未安装'}, status=status.HTTP_400_BAD_REQUEST)

        if not pkg.package_path or not os.path.exists(pkg.package_path):
            return Response({'error': '插件包文件缺失'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            checksum = _compute_checksum(pkg.package_path)
            manifest_data = None
            with zipfile.ZipFile(pkg.package_path, 'r') as zf:
                manifest_candidates = [n for n in zf.namelist() if n.endswith('manifest.yaml') or n.endswith('manifest.yml') or n.endswith('manifest.json')]
                if manifest_candidates:
                    raw_content = zf.read(manifest_candidates[0])
                    content_str = raw_content.decode('utf-8', errors='replace')
                    if manifest_candidates[0].endswith('.json'):
                        manifest_data = json.loads(content_str)
                    else:
                        manifest_data = yaml.safe_load(content_str)

            if manifest_data:
                valid, error_msg = _validate_manifest(manifest_data)
                if not valid:
                    return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)
                pkg.manifest = manifest_data
                pkg.version = manifest_data.get('version', pkg.version)
                pkg.author = manifest_data.get('author', pkg.author)
                pkg.description = manifest_data.get('description', pkg.description)

            pkg.checksum = checksum
            pkg.save()
            # Reload = UPDATE (manifest re-read + checksum recomputed; the
            # plugin row already existed).
            _log_plugin_audit(request, AuditAction.UPDATE, pkg.id, {
                'op': 'reload',
                'name': pkg.name,
                'version': pkg.version,
                'checksum': pkg.checksum,
            })
            return Response(_serialize_plugin(pkg))
        except (yaml.YAMLError, json.JSONDecodeError) as e:
            return Response({'error': f'manifest 解析失败: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error("PluginReload: failed: %s", e, exc_info=True)
            return Response({'error': f'重载失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PluginSandboxExecView(APIView):
    """沙箱中执行插件（子进程隔离）"""

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'execute'

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
        description="Spawn plugin entry_point in an isolated subprocess sandbox.",
    )
    def post(self, request, pk):
        """在子进程沙箱中执行指定插件"""
        try:
            pkg = PluginPackage.objects.get(pk=pk)
        except PluginPackage.DoesNotExist:
            return Response({'error': '插件不存在'}, status=status.HTTP_404_NOT_FOUND)

        if not pkg.is_installed:
            return Response({'error': '插件未安装'}, status=status.HTTP_400_BAD_REQUEST)

        extract_dir = os.path.join(settings.BASE_DIR, 'plugins_data', pkg.name, pkg.version)
        if not os.path.exists(extract_dir):
            return Response({'error': '插件安装目录不存在'}, status=status.HTTP_400_BAD_REQUEST)

        existing_sandbox = pkg.sandboxes.filter(status='running').first()
        if existing_sandbox:
            return Response({'error': '插件沙箱已在运行中', 'sandbox_id': existing_sandbox.id, 'pid': existing_sandbox.pid}, status=status.HTTP_409_CONFLICT)

        entry_point = pkg.manifest.get('entry_point', 'main.py')
        entry_path = os.path.join(extract_dir, entry_point)

        if not os.path.exists(entry_path):
            return Response({'error': f'入口文件不存在: {entry_point}'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            process = subprocess.Popen(
                ['python', entry_path],
                cwd=extract_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )

            sandbox = PluginSandbox.objects.create(
                plugin=pkg,
                pid=process.pid,
                status=PluginSandbox.Status.RUNNING,
            )

            # Sandbox execution is the highest-risk plugin operation
            # (arbitrary code runs in a subprocess). Log the plugin
            # identity + entry_point + sandbox_id + pid, but NEVER log
            # the plugin's source code or stdout/stderr content (the
            # plugin may print secrets during execution).
            _log_plugin_audit(request, AuditAction.EXECUTE, pkg.id, {
                'op': 'sandbox_exec',
                'name': pkg.name,
                'version': pkg.version,
                'entry_point': entry_point,
                'sandbox_id': sandbox.id,
                'pid': process.pid,
            })
            return Response({
                'sandbox_id': sandbox.id,
                'pid': process.pid,
                'status': PluginSandbox.Status.RUNNING.value,
                'message': f'插件 {pkg.name} 已在沙箱中启动',
            })
        except Exception as e:
            logger.error("PluginSandboxExec: failed: %s", e, exc_info=True)
            PluginSandbox.objects.create(
                plugin=pkg,
                status=PluginSandbox.Status.ERROR,
            )
            return Response({'error': f'沙箱启动失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
