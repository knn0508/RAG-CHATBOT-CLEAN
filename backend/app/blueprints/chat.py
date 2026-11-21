"""Chat and conversation routes."""
import json
import logging
import re
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, session

from app.auth import login_required
from app.extensions import chat_service, db_manager, rag_service

logger = logging.getLogger(__name__)
bp = Blueprint("chat", __name__)

# ============= CHAT ROUTES =============
@bp.route('/api/chat/ask', methods=['POST'])
@login_required
def ask_question():
    """Enhanced smart chat endpoint with context awareness and better formatting"""
    data = request.get_json()
    question = data.get('question', '').strip()
    document_id = data.get('document_id')
    conversation_id = data.get('conversation_id')

    if not question:
        return jsonify({'error': 'Sual tələb olunur'}), 400

    logger.info("\n=== CHAT REQUEST ===")
    logger.debug(f"Question: {question}")
    logger.info(f"Document ID: {document_id}")
    logger.info(f"Conversation ID: {conversation_id}")

    # Handle explicit document selection
    if document_id:
        documents = db_manager.get_documents()

        # If question clearly mentions a different filename, override stale selected document
        try:
            name_matched_doc_id = chat_service.document_matcher._match_by_document_name(question, documents)
            if name_matched_doc_id and name_matched_doc_id != document_id:
                logger.info(f"Overriding selected document {document_id} with filename-matched document {name_matched_doc_id}")
                document_id = name_matched_doc_id
        except Exception as e:
            logger.info(f"Filename override check skipped: {e}")

        doc = next((d for d in documents if d['id'] == document_id), None)

        if not doc:
            return jsonify({'error': 'Sənəd tapılmadı'}), 404

        if not doc.get('is_processed'):
            return jsonify({'error': 'Sənəd hələ işlənməyib'}), 400

        logger.info(f"Using explicitly selected document: {doc['original_name']}")

        # Use RAG directly with selected document
        result = rag_service.answer_question(question, document_id)
        raw_answer = result.get('answer', 'Cavab tapılmadı')

        # Format structured answer
        formatted_answer = chat_service.format_structured_answer(
            raw_answer, question, doc['original_name'], doc.get('document_type', 'other')
        )

        # Save conversation
        message = {
            'question': question,
            'answer': formatted_answer,
            'document_id': document_id,
            'document_name': doc['original_name'],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        if not conversation_id:
            title = f"{doc['original_name']}: {question[:30]}..."
            conversation_id = db_manager.create_conversation(
                user_id=session['user_id'],
                document_id=document_id,
                title=title,
                messages=json.dumps([message])
            )
        else:
            conv = db_manager.get_conversation(conversation_id, session['user_id'])
            if conv:
                messages = json.loads(conv['messages'])
                messages.append(message)
                db_manager.update_conversation(conversation_id, json.dumps(messages))

        return jsonify({
            'answer': formatted_answer,
            'conversation_id': conversation_id,
            'document_used': {
                'id': doc['id'],
                'name': doc['original_name']
            },
            'type': 'document_answer'
        })

    # Check for document download requests - always delegate to chat service
    # (intent detection is done inside find_template_by_keywords itself)
    template_match = chat_service.find_template_by_keywords(question)

    if template_match:
        template_doc = template_match['document']
        display_name = template_match.get('doc_display_name',
            re.sub(r'\.[^.]+$', '', template_doc['original_name']).replace('_', ' '))

        # Build a download URL that works in any environment
        base = request.url_root.rstrip('/')
        download_url = f"{base}/api/documents/{template_doc['id']}/download"

        size_kb = round((template_doc.get('file_size') or 0) / 1024, 1)
        size_str = f"{size_kb} KB" if size_kb >= 1 else f"{template_doc.get('file_size', 0)} bayt"

        answer = (
            f"**📄 {display_name}**\n\n"
            f"**[⬇️ Faylı yüklə]({download_url})**\n\n"
            f"| | |\n|---|---|\n"
            f"| Fayl adı | `{template_doc['original_name']}` |\n"
            f"| Növ | {template_doc.get('file_type', '—')} |\n"
            f"| Ölçü | {size_str} |\n\n"
            f"Linki klikləyərək faylı kompüterinizə yükləyə bilərsiniz."
        )

        message = {
            'question': question,
            'answer': answer,
            'document_id': template_doc['id'],
            'document_name': template_doc['original_name'],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        if not conversation_id:
            conversation_id = db_manager.create_conversation(
                user_id=session['user_id'],
                document_id=template_doc['id'],
                title=f"Fayl: {question[:40]}",
                messages=json.dumps([message])
            )
        else:
            conv = db_manager.get_conversation(conversation_id, session['user_id'])
            if conv:
                msgs = json.loads(conv['messages'])
                msgs.append(message)
                db_manager.update_conversation(conversation_id, json.dumps(msgs))

        return jsonify({
            'answer': answer,
            'conversation_id': conversation_id,
            'document_used': {'id': template_doc['id'], 'name': template_doc['original_name']},
            'download_url': download_url,
            'type': 'template_download'
        })

    # USE CONTEXT-AWARE CHAT SERVICE
    logger.info("Using context-aware chat service...")
    result = chat_service.process_chat_message(
        question=question,
        user_id=session['user_id'],
        conversation_id=conversation_id
    )

    return jsonify(result)

# ============= CONVERSATION ROUTES =============
@bp.route('/api/chat/conversations', methods=['GET'])
@login_required
def list_conversations():
    conversations = db_manager.get_conversations(session['user_id'])

    return jsonify({
        'conversations': [
            {
                'id': conv['id'],
                'title': conv['title'],
                'document_id': conv['document_id'],
                'document_name': conv.get('document_name'),
                'message_count': len(json.loads(conv['messages'])),
                'created_at': conv['created_at'],
                'updated_at': conv['updated_at']
            }
            for conv in conversations
        ]
    })

@bp.route('/api/chat/conversations/<int:conv_id>', methods=['GET'])
@login_required
def get_conversation(conv_id):
    conversation = db_manager.get_conversation(conv_id, session['user_id'])

    if not conversation:
        return jsonify({'error': 'Söhbət tapılmadı'}), 404

    return jsonify({
        'conversation': {
            'id': conversation['id'],
            'title': conversation['title'],
            'document_id': conversation['document_id'],
            'messages': json.loads(conversation['messages']),
            'created_at': conversation['created_at'],
            'updated_at': conversation['updated_at']
        }
    })

@bp.route('/api/chat/conversations/<int:conv_id>/rename', methods=['PUT'])
@login_required
def rename_conversation(conv_id):
    data = request.get_json()
    new_title = data.get('title', '').strip()

    if not new_title:
        return jsonify({'error': 'Yeni başlıq tələb olunur'}), 400

    conversation = db_manager.get_conversation(conv_id, session['user_id'])
    if not conversation:
        return jsonify({'error': 'Söhbət tapılmadı'}), 404

    db_manager.execute_query(
        "UPDATE conversations SET title = ? WHERE id = ? AND user_id = ?",
        (new_title, conv_id, session['user_id'])
    )

    return jsonify({'message': 'Başlıq dəyişdirildi'})

@bp.route('/api/chat/conversations/<int:conv_id>', methods=['DELETE'])
@login_required
def delete_conversation(conv_id):
    success = db_manager.delete_conversation(conv_id, session['user_id'])
    if success:
        return jsonify({'message': 'Söhbət silindi'})
    return jsonify({'error': 'Söhbət tapılmadı'}), 404
