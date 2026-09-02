"""
备份与恢复 API
"""
import json
import logging
import os
import shutil
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.http import FileResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

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


@extend_schema(
    tags=['backup'],
    summary='Create full backup ZIP (dumpdata + summary)',
    request=OpenApiTypes.OBJECT,
    responses={
        (200, 'application/zip'): OpenApiTypes.BINARY,
        500: OpenApiTypes.OBJECT,
    },
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_backup(request):
    """创建全量备份 ZIP"""
    # @api_view allowed: cross-model backup via dumpdata + ZIP artifact, not model CRUD
    tag = request.data.get('tag', timezone.now().strftime('%Y%m%d_%H%M%S'))
    backup_dir = tempfile.mkdtemp(prefix='gaf_backup_')

    try:
        # Use .json extension because dumpdata outputs JSON fixtures (not SQL).
        # restore_backup uses call_command('loaddata', ...) which is symmetric
        # with dumpdata and avoids arbitrary SQL execution via cursor.execute.
        db_file = os.path.join(backup_dir, 'database.json')
        with open(db_file, 'w') as f:
            call_command('dumpdata', '--exclude=contenttypes', '--exclude=auth.permission', stdout=f)

        summary = {
            'created_at': timezone.now().isoformat(),
            'tag': tag,
            'db_engine': settings.DATABASES['default']['ENGINE'],
        }
        summary_file = os.path.join(backup_dir, 'backup_info.json')
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(backup_dir):
                for file in files:
                    filepath = os.path.join(root, file)
                    arcname = os.path.relpath(filepath, backup_dir)
                    zf.write(filepath, arcname)

        zip_buffer.seek(0)
        filename = f"gaf_backup_{tag}.zip"
        response = FileResponse(zip_buffer, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception:
        # B003 fix: never leak internal exception details to the client —
        # log the full traceback server-side, return generic message.
        logger.exception('create_backup failed for tag=%s', tag)
        return Response(
            {'detail': '备份失败，请查看服务器日志'},
            status=500,
        )
    finally:
        shutil.rmtree(backup_dir, ignore_errors=True)


@extend_schema(
    tags=['backup'],
    summary='Restore from uploaded backup ZIP',
    request={
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'file': {'type': 'string', 'format': 'binary', 'description': 'Backup ZIP file (max 200MB).'},
            },
            'required': ['file'],
        },
    },
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def restore_backup(request):
    """从上传的备份 ZIP 恢复"""
    # @api_view allowed: cross-model restore (upload ZIP + loaddata), not model CRUD
    uploaded = request.FILES.get('file')
    if not uploaded:
        return Response({'error': '请上传备份文件'}, status=400)

    if not uploaded.name.endswith('.zip'):
        return Response({'error': '仅支持 .zip 格式'}, status=400)

    if uploaded.size > 200 * 1024 * 1024:
        return Response({'error': '文件过大（上限200MB）'}, status=400)

    try:
        temp_dir = tempfile.mkdtemp(prefix='gaf_restore_')
        zip_path = os.path.join(temp_dir, uploaded.name)
        with open(zip_path, 'wb') as f:
            for chunk in uploaded.chunks():
                f.write(chunk)

        with zipfile.ZipFile(zip_path, 'r') as zf:
            _safe_extract_zip(zf, temp_dir)

        # Match create_backup's database.json filename. Use loaddata (symmetric
        # with dumpdata) instead of cursor.execute to prevent arbitrary SQL
        # execution from malicious uploaded ZIP contents.
        db_file = os.path.join(temp_dir, 'database.json')
        if os.path.exists(db_file):
            call_command('loaddata', db_file)

        return Response({'status': 'ok', 'message': '备份恢复完成'})
    except Exception:
        # B003 fix: never leak internal exception details to the client —
        # log the full traceback server-side, return generic message.
        logger.exception('restore_backup failed for file=%s', uploaded.name)
        return Response(
            {'detail': '备份恢复失败，请查看服务器日志'},
            status=500,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
