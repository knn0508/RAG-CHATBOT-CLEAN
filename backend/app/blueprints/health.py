"""Health check and API index routes."""
import logging

from flask import Blueprint, jsonify, session

logger = logging.getLogger(__name__)
bp = Blueprint("health", __name__)

# ============= HEALTH CHECK ROUTES =============
@bp.route('/api/health', methods=['GET'])
def health_check():
    try:
        from config import get_config
        cfg = get_config()
        return jsonify({
            'status': 'healthy',
            'session_exists': bool(session),
            'authenticated': 'user_id' in session,
            'llm_model': getattr(cfg, 'LLM_MODEL', None),
            'embedding_model': getattr(cfg, 'EMBEDDING_MODEL', None),
            'features': [
                'context_aware_chat',
                'improved_document_matching',
                'structured_formatting',
                'conversation_memory',
                'keyword_extraction',
                'document_reprocessing'
            ]
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

# Route removed to allow serving React Frontend
# @bp.route('/')
# def index():
#     return jsonify({ ... })

@bp.route('/api')
def api_root():
    return jsonify({
        'message': 'Enhanced RAG API v2.0',
        'status': 'active',
        'features': [
            'Context awareness',
            'Memory persistence',
            'Structured formatting',
            'Keyword extraction',
            'Document reprocessing'
        ],
        'endpoints': [
            '/api/auth/login',
            '/api/auth/check',
            '/api/documents',
            '/api/documents/types',
            '/api/chat/ask',
            '/api/health',
            '/api/documents/{id}/reprocess'
        ]
    })
