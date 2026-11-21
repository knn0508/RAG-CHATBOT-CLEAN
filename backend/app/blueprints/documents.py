"""Document upload/download/keyword routes."""
import io
import json
import logging
import os
import uuid

from flask import Blueprint, Response, jsonify, request, send_file, session

from app.auth import admin_required, login_required
from app.extensions import blob_storage, db_manager, rag_service
from app.uploads import validate_upload
from config import get_config

logger = logging.getLogger(__name__)
bp = Blueprint("documents", __name__)

# ============= DOCUMENT ROUTES =============
@bp.route('/api/documents', methods=['GET'])
@login_required
def list_documents():
    documents = db_manager.get_documents()

    return jsonify({
        'documents': [
            {
                'id': doc['id'],
                'name': doc['original_name'],
                'size': doc['file_size'],
                'type': doc['file_type'],
                'document_type': doc.get('document_type', 'other'),
                'uploaded_by': doc.get('uploaded_by_name', 'Unknown'),
                'is_processed': doc.get('is_processed', False),
                'is_template': doc.get('is_template', False),
                'created_at': doc['created_at']
            }
            for doc in documents
        ]
    })

@bp.route('/api/documents', methods=['POST'])
@admin_required
def upload_document():
    try:
        logger.info("Upload document request received")

        if 'file' not in request.files:
            return jsonify({'error': 'Fayl seçilməyib'}), 400

        file = request.files['file']
        if not file.filename:
            return jsonify({'error': 'Fayl seçin'}), 400

        logger.info(f"File received: {file.filename}")

        # Get document type from request
        doc_type = request.form.get('document_type', 'other')
        is_template = request.form.get('is_template', 'false').lower() == 'true'

        logger.info(f"Document type: {doc_type}, Is template: {is_template}")

        # Save file using appropriate storage method



        filename, error = validate_upload(file)
        if error:
            return error
        unique_filename = f"{uuid.uuid4()}_{filename}"

        # Check environment and storage availability
        is_vercel = os.getenv('VERCEL', '') == '1'
        blob_url = None
        file_path = None
        is_blob = False

        # Force Blob Storage on Vercel, LOCAL filesystem for development
        if is_vercel:
            # MUST USE BLOB STORAGE ON VERCEL - no local fallback
            if not (blob_storage and blob_storage.blob_enabled):
                logger.error("❌ VERCEL DETECTED but Blob Storage NOT enabled")
                return jsonify({
                    'error': 'Blob Storage not configured on Vercel',
                    'details': 'Environment variable BLOB_READ_WRITE_TOKEN (or VERCEL_BLOB_TOKEN) is missing',
                    'instructions': [
                        'Set environment variable in Vercel Project Settings',
                        'Variable name: BLOB_READ_WRITE_TOKEN (or VERCEL_BLOB_TOKEN)',
                        'Value: Get from Vercel Blob Storage settings',
                        'Then redeploy'
                    ]
                }), 400

            # Upload to Blob Storage
            logger.info("✅ Using Vercel Blob Storage")
            file.seek(0)
            success, result = blob_storage.upload_file(file, unique_filename)

            if not success:
                logger.error(f"❌ Blob upload failed: {result}")
                return jsonify({'error': f'Blob upload failed: {result}'}), 500

            blob_url = result
            file_path = blob_url
            is_blob = True
            logger.info(f"✅ File uploaded to Blob Storage: {blob_url[:80]}...")
        else:
            # Local development - use local filesystem
            logger.info("🖥️ Local development - using local filesystem storage")
            file_path = os.path.join(get_config().UPLOAD_FOLDER, unique_filename)
            os.makedirs(get_config().UPLOAD_FOLDER, exist_ok=True)
            file.seek(0)
            file.save(file_path)
            logger.info(f"✅ File saved to: {file_path}")

            if not os.path.exists(file_path):
                return jsonify({'error': 'Fayl saxlanmadı'}), 500

        # Get file info
        if is_blob:
            # For blob storage, use the size from the upload
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            logger.info(f"Blob file size: {file_size}")
        else:
            file_size = os.path.getsize(file_path)
            logger.info(f"Local file size: {file_size}")

        file_type = os.path.splitext(filename)[1].upper().replace('.', '')

        logger.info(f"File type: {file_type}")

        # Save to database
        try:
            doc_id = db_manager.create_document(
                filename=unique_filename,
                original_name=filename,
                file_path=file_path,
                file_size=file_size,
                file_type=file_type,
                uploaded_by=session['user_id'],
                is_blob_storage=is_blob
            )
            logger.info(f"Document saved to database with ID: {doc_id}")
        except Exception as db_error:
            logger.error(f"Database error: {db_error}")
            # Clean up file if error
            if is_blob and blob_url:
                blob_storage.delete_file(blob_url)
            elif not is_blob and os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({'error': f'Database xətası: {str(db_error)}'}), 500

        # Process with RAG
        try:
            if is_blob:
                # Download and process from blob storage
                file_content = blob_storage.download_file(blob_url)
                if file_content:
                    success = rag_service.process_document_from_bytes(file_content, doc_id, filename)
                else:
                    success = False
            else:
                # Process from local filesystem
                success = rag_service.process_document(file_path, doc_id)

            if success:
                db_manager.update_document_processed(doc_id, True)
                logger.info("Document processed successfully")
            else:
                logger.error("Document processing failed")
        except Exception as process_error:
            logger.error(f"Processing error: {process_error}")

            logger.exception("Unhandled error")
            success = False

        return jsonify({
            'message': f'{file_type} faylı yükləndi və işləndi' if success else f'{file_type} faylı yükləndi amma işlənmədi',
            'document': {
                'id': doc_id,
                'name': filename,
                'type': file_type,
                'document_type': doc_type,
                'size': file_size,
                'is_processed': success,
                'is_template': is_template,
                'storage_type': 'blob' if is_blob else 'local'
            }
        }), 201

    except Exception as e:
        logger.error(f"Upload error: {e}")

        logger.exception("Unhandled error")
        return jsonify({'error': f'Yükləmə xətası: {str(e)}'}), 500

@bp.route('/api/documents/<int:doc_id>/download', methods=['GET'])
@login_required
def download_document(doc_id):
    """Download document file with proper cache handling"""
    try:
        logger.info(f"Download request for document ID: {doc_id}")

        documents = db_manager.get_documents()
        doc = next((d for d in documents if d['id'] == doc_id), None)

        if not doc:
            return jsonify({'error': 'Sənəd tapılmadı'}), 404

        file_path = doc['file_path']
        is_blob = doc.get('is_blob_storage', False)

        # Get file content
        if is_blob:
            logger.info(f"Downloading from Blob Storage: {file_path}")
            file_content = blob_storage.download_file(file_path)
            if not file_content:
                return jsonify({'error': 'Fayl tapılmadı'}), 404
            file_size = len(file_content)
        else:
            logger.info(f"Downloading from local filesystem: {file_path}")
            if not os.path.exists(file_path):
                return jsonify({'error': 'Fayl tapılmadı'}), 404
            file_size = os.path.getsize(file_path)

        # MIME type mapping
        file_extension = os.path.splitext(doc['original_name'])[1].lower()
        mime_types = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.txt': 'text/plain; charset=utf-8',
            '.md': 'text/markdown; charset=utf-8',
            '.json': 'application/json',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.xls': 'application/vnd.ms-excel'
        }
        mimetype = mime_types.get(file_extension, 'application/octet-stream')

        if is_blob:
            # For blob storage, send content directly
            return send_file(
                io.BytesIO(file_content),
                mimetype=mimetype,
                as_attachment=True,
                download_name=doc['original_name']
            )
        else:
            # For local filesystem, stream the file
            def generate():
                with open(file_path, 'rb') as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        yield chunk

            response = Response(
                generate(),
                mimetype=mimetype,
                headers={
                    'Content-Disposition': f'attachment; filename="{doc["original_name"]}"',
                    'Content-Length': str(file_size),
                    'Content-Type': mimetype,
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0',
                    'Accept-Ranges': 'bytes'
                }
            )

            logger.info(f"Sending file: {doc['original_name']} ({file_size} bytes)")
            return response

    except Exception as e:
        logger.error(f"Download error: {e}")

        logger.exception("Unhandled error")
        return jsonify({'error': f'Yükləmə xətası: {str(e)}'}), 500

@bp.route('/api/documents/<int:doc_id>', methods=['DELETE'])
@admin_required
def delete_document(doc_id):
    doc = db_manager.delete_document(doc_id)
    if not doc:
        return jsonify({'error': 'Sənəd tapılmadı'}), 404

    # Delete file based on storage type
    is_blob = doc.get('is_blob_storage', False)
    file_path = doc['file_path']

    if is_blob and blob_storage:
        # Delete from Blob Storage
        logger.info(f"Deleting file from Blob Storage: {file_path}")
        blob_storage.delete_file(file_path)
    else:
        # Delete local file
        if os.path.exists(file_path):
            logger.info(f"Deleting local file: {file_path}")
            os.remove(file_path)

    # Delete vector store
    rag_service.delete_document_vectors(doc_id)

    return jsonify({'message': 'Sənəd silindi'})

@bp.route('/api/documents/<int:doc_id>/reprocess', methods=['POST'])
@admin_required
def reprocess_document(doc_id):
    """Reprocess document with enhanced keyword extraction"""
    try:
        logger.info(f"Reprocess request for document ID: {doc_id}")

        # Get document info
        documents = db_manager.get_documents()
        doc = next((d for d in documents if d['id'] == doc_id), None)

        if not doc:
            return jsonify({'error': 'Sənəd tapılmadı'}), 404

        file_path = doc['file_path']
        is_blob = doc.get('is_blob_storage', False)

        logger.info(f"Reprocessing document: {doc['original_name']}")

        # Delete old vector store
        rag_service.delete_document_vectors(doc_id)

        # Mark as not processed
        db_manager.execute_query(
            "UPDATE documents SET is_processed = FALSE WHERE id = ?",
            (doc_id,)
        )

        # Reprocess with enhanced keyword extraction
        if is_blob:
            # Download and process from blob storage
            file_content = blob_storage.download_file(file_path)
            if not file_content:
                return jsonify({'error': 'Fayl Blob Storage-dan alına bilmədi'}), 500
            success = rag_service.process_document_from_bytes(file_content, doc_id, doc['original_name'])
        else:
            # Process from local filesystem
            if not os.path.exists(file_path):
                return jsonify({'error': 'Fayl tapılmadı'}), 404
            success = rag_service.process_document(file_path, doc_id)

        if success:
            db_manager.update_document_processed(doc_id, True)

            # Get extracted keywords
            keywords_result = db_manager.execute_query(
                "SELECT keywords FROM documents WHERE id = ?",
                (doc_id,),
                fetch_one=True
            )

            keywords = []
            if keywords_result:
                try:
                    keywords_dict = dict(keywords_result)
                    keywords = json.loads(keywords_dict.get('keywords', '[]'))
                except:
                    keywords = []

            return jsonify({
                'message': 'Sənəd uğurla yenidən işləndi',
                'document': {
                    'id': doc_id,
                    'name': doc['original_name'],
                    'keywords_count': len(keywords),
                    'top_keywords': keywords[:10] if keywords else []
                }
            })
        else:
            return jsonify({'error': 'Sənəd işlənmədi'}), 500

    except Exception as e:
        logger.error(f"Reprocess error: {e}")

        logger.exception("Unhandled error")
        return jsonify({'error': f'Reprocess xətası: {str(e)}'}), 500

@bp.route('/api/documents/<int:doc_id>/keywords', methods=['GET'])
@login_required
def get_document_keywords(doc_id):
    """Get document keywords"""
    try:
        # Get document info
        result = db_manager.execute_query(
            "SELECT original_name, keywords FROM documents WHERE id = ?",
            (doc_id,),
            fetch_one=True
        )

        if not result:
            return jsonify({'error': 'Sənəd tapılmadı'}), 404

        doc_dict = dict(result)
        keywords = []

        try:
            keywords = json.loads(doc_dict.get('keywords', '[]'))
        except:
            keywords = []

        return jsonify({
            'document_id': doc_id,
            'document_name': doc_dict['original_name'],
            'keywords': keywords,
            'keywords_count': len(keywords)
        })

    except Exception as e:
        return jsonify({'error': f'Keywords xətası: {str(e)}'}), 500

@bp.route('/api/documents/templates', methods=['GET'])
@login_required
def list_template_documents():
    """List all template documents"""
    try:
        templates = db_manager.execute_query(
            """SELECT d.*, u.username as uploaded_by_name 
               FROM documents d 
               JOIN users u ON d.uploaded_by = u.id 
               WHERE d.is_template = TRUE 
               ORDER BY d.document_type, d.created_at DESC"""
        )

        return jsonify({
            'templates': [
                {
                    'id': doc['id'],
                    'name': doc['original_name'],
                    'type': doc['file_type'],
                    'document_type': doc.get('document_type', 'other'),
                    'size': doc['file_size'],
                    'uploaded_by': doc['uploaded_by_name'],
                    'created_at': doc['created_at'],
                    'download_url': f"/api/documents/{doc['id']}/download"
                }
                for doc in templates
            ]
        })

    except Exception as e:
        return jsonify({'error': f'Templates xətası: {str(e)}'}), 500

@bp.route('/api/documents/search-by-keywords', methods=['POST'])
@login_required
def search_documents_by_keywords():
    """Search documents by keywords"""
    try:
        data = request.get_json()
        search_keywords = data.get('keywords', [])

        if not search_keywords:
            return jsonify({'error': 'Açar sözlər tələb olunur'}), 400

        documents = db_manager.get_documents()
        results = []

        for doc in documents:
            if not doc.get('keywords'):
                continue

            try:
                doc_keywords = json.loads(doc['keywords'])

                # Calculate relevance score
                score = 0
                matched_keywords = []

                for search_kw in search_keywords:
                    search_kw_lower = search_kw.lower()
                    for doc_kw in doc_keywords:
                        doc_kw_lower = doc_kw.lower()
                        if search_kw_lower in doc_kw_lower or doc_kw_lower in search_kw_lower:
                            score += 1
                            if doc_kw not in matched_keywords:
                                matched_keywords.append(doc_kw)

                if score > 0:
                    results.append({
                        'document': {
                            'id': doc['id'],
                            'name': doc['original_name'],
                            'type': doc.get('document_type', 'other')
                        },
                        'relevance_score': score,
                        'matched_keywords': matched_keywords[:10]
                    })

            except:
                continue

        # Sort by relevance
        results.sort(key=lambda x: x['relevance_score'], reverse=True)

        return jsonify({
            'search_keywords': search_keywords,
            'results': results[:20],
            'total_results': len(results)
        })

    except Exception as e:
        return jsonify({'error': f'Search xətası: {str(e)}'}), 500


# Add these endpoints to simple_app.py after other document routes

@bp.route('/api/documents/<int:doc_id>/keywords', methods=['PUT'])
@admin_required
def update_document_keywords(doc_id):
    """Admin can manually update document keywords"""
    try:
        data = request.get_json()
        new_keywords = data.get('keywords', [])

        # Validate keywords
        if not isinstance(new_keywords, list):
            return jsonify({'error': 'Açar sözlər list formatında olmalıdır'}), 400

        # Limit to 15 keywords
        if len(new_keywords) > 15:
            return jsonify({'error': 'Maksimum 15 açar söz əlavə edilə bilər'}), 400

        # Clean and validate each keyword
        cleaned_keywords = []
        for keyword in new_keywords:
            keyword = str(keyword).strip()
            if keyword and len(keyword) >= 2 and len(keyword) <= 50:
                cleaned_keywords.append(keyword)

        # Check document exists
        doc_result = db_manager.execute_query(
            "SELECT original_name FROM documents WHERE id = ?",
            (doc_id,),
            fetch_one=True
        )

        if not doc_result:
            return jsonify({'error': 'Sənəd tapılmadı'}), 404

        doc_name = dict(doc_result)['original_name']

        # Update keywords in database
        keywords_json = json.dumps(cleaned_keywords, ensure_ascii=False)
        db_manager.execute_query(
            "UPDATE documents SET keywords = ? WHERE id = ?",
            (keywords_json, doc_id)
        )

        logger.info(f"Keywords updated for document {doc_id}: {cleaned_keywords}")

        return jsonify({
            'message': 'Açar sözlər yeniləndi',
            'document_id': doc_id,
            'document_name': doc_name,
            'keywords': cleaned_keywords,
            'keywords_count': len(cleaned_keywords)
        })

    except Exception as e:
        logger.error(f"Update keywords error: {e}")
        return jsonify({'error': f'Açar sözlər yenilənmədi: {str(e)}'}), 500

@bp.route('/api/documents/<int:doc_id>/add-keywords', methods=['POST'])
@admin_required
def add_document_keywords(doc_id):
    """Admin can add additional keywords to existing ones"""
    try:
        data = request.get_json()
        additional_keywords = data.get('keywords', [])

        if not isinstance(additional_keywords, list):
            return jsonify({'error': 'Açar sözlər list formatında olmalıdır'}), 400

        # Get existing keywords
        result = db_manager.execute_query(
            "SELECT keywords, original_name FROM documents WHERE id = ?",
            (doc_id,),
            fetch_one=True
        )

        if not result:
            return jsonify({'error': 'Sənəd tapılmadı'}), 404

        doc_dict = dict(result)
        existing_keywords = []

        try:
            if doc_dict.get('keywords'):
                existing_keywords = json.loads(doc_dict['keywords'])
        except:
            existing_keywords = []

        # Combine keywords
        all_keywords = existing_keywords + additional_keywords

        # Remove duplicates and limit to 15
        unique_keywords = []
        seen = set()
        for keyword in all_keywords:
            keyword = str(keyword).strip().lower()
            if keyword and keyword not in seen and len(keyword) >= 2 and len(keyword) <= 50:
                seen.add(keyword)
                unique_keywords.append(keyword)

        unique_keywords = unique_keywords[:15]  # Limit to 15

        # Update in database
        keywords_json = json.dumps(unique_keywords, ensure_ascii=False)
        db_manager.execute_query(
            "UPDATE documents SET keywords = ? WHERE id = ?",
            (keywords_json, doc_id)
        )

        return jsonify({
            'message': 'Açar sözlər əlavə edildi',
            'document_id': doc_id,
            'document_name': doc_dict['original_name'],
            'keywords': unique_keywords,
            'keywords_count': len(unique_keywords),
            'added_count': len(unique_keywords) - len(existing_keywords)
        })

    except Exception as e:
        logger.error(f"Add keywords error: {e}")
        return jsonify({'error': f'Açar sözlər əlavə edilmədi: {str(e)}'}), 500

@bp.route('/api/documents/<int:doc_id>/remove-keyword', methods=['DELETE'])
@admin_required
def remove_document_keyword(doc_id):
    """Admin can remove a specific keyword"""
    try:
        data = request.get_json()
        keyword_to_remove = data.get('keyword', '').strip().lower()

        if not keyword_to_remove:
            return jsonify({'error': 'Silinəcək açar söz təyin edilməyib'}), 400

        # Get existing keywords
        result = db_manager.execute_query(
            "SELECT keywords, original_name FROM documents WHERE id = ?",
            (doc_id,),
            fetch_one=True
        )

        if not result:
            return jsonify({'error': 'Sənəd tapılmadı'}), 404

        doc_dict = dict(result)
        existing_keywords = []

        try:
            if doc_dict.get('keywords'):
                existing_keywords = json.loads(doc_dict['keywords'])
        except:
            existing_keywords = []

        # Remove the keyword
        updated_keywords = [kw for kw in existing_keywords if kw.lower() != keyword_to_remove]

        if len(updated_keywords) == len(existing_keywords):
            return jsonify({'error': 'Bu açar söz tapılmadı'}), 404

        # Update in database
        keywords_json = json.dumps(updated_keywords, ensure_ascii=False)
        db_manager.execute_query(
            "UPDATE documents SET keywords = ? WHERE id = ?",
            (keywords_json, doc_id)
        )

        return jsonify({
            'message': f'"{keyword_to_remove}" açar sözü silindi',
            'document_id': doc_id,
            'document_name': doc_dict['original_name'],
            'keywords': updated_keywords,
            'keywords_count': len(updated_keywords)
        })

    except Exception as e:
        logger.error(f"Remove keyword error: {e}")
        return jsonify({'error': f'Açar söz silinmədi: {str(e)}'}), 500

# Override the upload endpoint to include manual keywords
@bp.route('/api/documents/upload-with-keywords', methods=['POST'])
@admin_required
def upload_document_with_keywords():
    """Upload document with manual keywords"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Fayl seçilməyib'}), 400

        file = request.files['file']
        if not file.filename:
            return jsonify({'error': 'Fayl seçin'}), 400

        # Get parameters
        doc_type = request.form.get('document_type', 'other')
        is_template = request.form.get('is_template', 'false').lower() == 'true'
        manual_keywords = request.form.get('keywords', '')

        # Parse manual keywords
        keywords_list = []
        if manual_keywords:
            try:
                # Try to parse as JSON first
                keywords_list = json.loads(manual_keywords)
            except:
                # If not JSON, split by comma
                keywords_list = [kw.strip() for kw in manual_keywords.split(',') if kw.strip()]

        # Limit to 15 keywords
        keywords_list = keywords_list[:15]

        logger.debug(f"Uploading file with manual keywords: {keywords_list}")

        # Save file



        filename, error = validate_upload(file)
        if error:
            return error
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(get_config().UPLOAD_FOLDER, unique_filename)

        os.makedirs(get_config().UPLOAD_FOLDER, exist_ok=True)
        file.save(file_path)

        # Get file info
        file_size = os.path.getsize(file_path)
        file_type = os.path.splitext(filename)[1].upper().replace('.', '')

        # Save to database with initial keywords
        doc_id = db_manager.execute_query(
            """INSERT INTO documents 
               (filename, original_name, file_path, file_size, file_type, 
                uploaded_by, document_type, is_template, is_processed, keywords) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (unique_filename, filename, file_path, file_size, file_type,
             session['user_id'], doc_type, is_template, False,
             json.dumps(keywords_list, ensure_ascii=False) if keywords_list else None)
        )

        # Process with RAG
        try:
            success = rag_service.process_document(file_path, doc_id)
            if success:
                db_manager.update_document_processed(doc_id, True)

                # If manual keywords were provided, merge with extracted ones
                if keywords_list:
                    # Get extracted keywords
                    result = db_manager.execute_query(
                        "SELECT keywords FROM documents WHERE id = ?",
                        (doc_id,),
                        fetch_one=True
                    )

                    extracted_keywords = []
                    if result:
                        try:
                            extracted_keywords = json.loads(dict(result).get('keywords', '[]'))
                        except:
                            extracted_keywords = []

                    # Merge and deduplicate
                    all_keywords = list(set(keywords_list + extracted_keywords))[:15]

                    # Update with merged keywords
                    db_manager.execute_query(
                        "UPDATE documents SET keywords = ? WHERE id = ?",
                        (json.dumps(all_keywords, ensure_ascii=False), doc_id)
                    )

                    keywords_list = all_keywords

        except Exception as process_error:
            logger.error(f"Processing error: {process_error}")
            success = False

        return jsonify({
            'message': f'{file_type} faylı yükləndi və işləndi',
            'document': {
                'id': doc_id,
                'name': filename,
                'type': file_type,
                'document_type': doc_type,
                'size': file_size,
                'is_processed': success,
                'is_template': is_template,
                'keywords': keywords_list
            }
        }), 201

    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({'error': f'Yükləmə xətası: {str(e)}'}), 500

@bp.route('/api/templates', methods=['GET'])
@login_required
def list_templates():
    """List all available templates"""
    try:
        documents = db_manager.get_documents()
        templates = [
            {
                'id': doc['id'],
                'name': doc['original_name'],
                'type': doc.get('document_type', 'other'),
                'size': doc['file_size'],
                'file_type': doc['file_type'],
                'download_url': f"/api/documents/{doc['id']}/download",
                'created_at': doc['created_at']
            }
            for doc in documents if doc.get('is_template')
        ]

        return jsonify({
            'templates': templates,
            'count': len(templates)
        })

    except Exception as e:
        return jsonify({'error': f'Şablon siyahısı alınmadı: {str(e)}'}), 500

# ============= UTILITY ROUTES =============
@bp.route('/api/documents/types', methods=['GET'])
def get_document_types():
    """Get available document types"""
    types = [
        {'value': 'contact', 'label': 'Əlaqə məlumatları'},
        {'value': 'contract', 'label': 'Müqavilə'},
        {'value': 'vacation', 'label': 'Məzuniyyət'},
        {'value': 'business_trip', 'label': 'Ezamiyyət'},
        {'value': 'memorandum', 'label': 'Anlaşma memorandumu'},
        {'value': 'report', 'label': 'Hesabat'},
        {'value': 'letter', 'label': 'Məktub'},
        {'value': 'invoice', 'label': 'Qaimə'},
        {'value': 'other', 'label': 'Digər'}
    ]
    return jsonify({'types': types})
