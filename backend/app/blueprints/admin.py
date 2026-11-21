"""Admin-only maintenance routes (bulk reprocess, template initialisation)."""
import logging
import os
import shutil
import uuid

from flask import Blueprint, jsonify, request, session

from app.auth import admin_required
from app.extensions import db_manager, rag_service
from config import get_config

logger = logging.getLogger(__name__)
bp = Blueprint("admin", __name__)

@bp.route('/api/admin/documents/bulk-reprocess', methods=['POST'])
@admin_required
def bulk_reprocess_documents():
    """Reprocess multiple documents"""
    try:
        data = request.get_json()
        document_ids = data.get('document_ids', [])

        if not document_ids:
            # Reprocess all documents
            documents = db_manager.get_documents()
            document_ids = [doc['id'] for doc in documents]

        results = {
            'success': [],
            'failed': []
        }

        for doc_id in document_ids:
            try:
                # Get document
                doc_result = db_manager.execute_query(
                    "SELECT * FROM documents WHERE id = ?",
                    (doc_id,),
                    fetch_one=True
                )

                if not doc_result:
                    results['failed'].append({
                        'id': doc_id,
                        'error': 'Sənəd tapılmadı'
                    })
                    continue

                doc = dict(doc_result)

                # Delete old vectors
                rag_service.delete_document_vectors(doc_id)

                # Reprocess
                success = rag_service.process_document(doc['file_path'], doc_id)

                if success:
                    db_manager.update_document_processed(doc_id, True)
                    results['success'].append({
                        'id': doc_id,
                        'name': doc['original_name']
                    })
                else:
                    results['failed'].append({
                        'id': doc_id,
                        'name': doc['original_name'],
                        'error': 'İşlənmədi'
                    })

            except Exception as e:
                results['failed'].append({
                    'id': doc_id,
                    'error': str(e)
                })

        return jsonify({
            'message': f"{len(results['success'])} sənəd uğurla işləndi, {len(results['failed'])} uğursuz",
            'results': results
        })

    except Exception as e:
        return jsonify({'error': f'Bulk reprocess xətası: {str(e)}'}), 500

# ============= TEMPLATE MANAGEMENT ROUTES =============
@bp.route('/api/templates/initialize', methods=['POST'])
@admin_required
def initialize_templates():
    """Initialize template documents from example_docs folder"""
    try:
        example_docs_path = get_config().EXAMPLE_DOCS_DIR

        if not os.path.exists(example_docs_path):
            return jsonify({'error': 'example_docs klasörü tapılmadı'}), 404

        # Template type mapping based on filename
        template_mappings = {
            'ezamiyyet_template.docx': 'business_trip',
            'memorandum_template.docx': 'memorandum',
            'mezuniyyet_template.docx': 'vacation',
            'muqavile_template.docx': 'contract',
            'demo_leave_policy.txt': 'vacation',
            'demo_business_trip_rules.txt': 'business_trip',
            'demo_work_rules.txt': 'other',
        }

        initialized_count = 0
        errors = []

        for filename, doc_type in template_mappings.items():
            file_path = os.path.join(example_docs_path, filename)

            if not os.path.exists(file_path):
                errors.append(f"{filename} faylı tapılmadı")
                continue

            # Check if template already exists
            existing = db_manager.execute_query(
                "SELECT id FROM documents WHERE original_name = ? AND is_template = TRUE",
                (filename,), fetch_one=True
            )

            if existing:
                logger.info(f"Template {filename} already exists, skipping...")
                continue

            try:
                # Copy file to documents directory



                unique_filename = f"{uuid.uuid4()}_{filename}"
                dest_path = os.path.join(get_config().UPLOAD_FOLDER, unique_filename)

                os.makedirs(get_config().UPLOAD_FOLDER, exist_ok=True)
                shutil.copy2(file_path, dest_path)

                # Get file info
                file_size = os.path.getsize(dest_path)
                file_type = os.path.splitext(filename)[1].upper().replace('.', '')

                # Save to database as template
                doc_id = db_manager.execute_query(
                    """INSERT INTO documents 
                       (filename, original_name, file_path, file_size, file_type, 
                        uploaded_by, document_type, is_template, is_processed) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (unique_filename, filename, dest_path, file_size, file_type,
                     session['user_id'], doc_type, True, False)
                )

                # Process with RAG (optional for templates)
                try:
                    success = rag_service.process_document(dest_path, doc_id)
                    if success:
                        db_manager.update_document_processed(doc_id, True)
                except Exception as process_error:
                    logger.error(f"Template processing warning for {filename}: {process_error}")
                    # Don't fail initialization if processing fails

                initialized_count += 1
                logger.info(f"Initialized template: {filename} with type: {doc_type}")

            except Exception as file_error:
                errors.append(f"{filename}: {str(file_error)}")
                continue

        message = f"{initialized_count} şablon uğurla yükləndi"
        if errors:
            message += f". Xətalar: {'; '.join(errors)}"

        return jsonify({
            'message': message,
            'initialized_count': initialized_count,
            'errors': errors
        })

    except Exception as e:
        logger.error(f"Template initialization error: {e}")

        logger.exception("Unhandled error")
        return jsonify({'error': f'Şablon yükləmə xətası: {str(e)}'}), 500
