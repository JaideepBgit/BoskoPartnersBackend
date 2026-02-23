"""
RAG (Retrieval-Augmented Generation) routes for AI question answering.
"""
from flask import Blueprint, request, jsonify
import logging

logger = logging.getLogger(__name__)

rag_bp = Blueprint('rag', __name__)

# RAG service will be initialized when the app starts
rag_service = None


def initialize_rag_service(db):
    """Initialize RAG service with database connection."""
    global rag_service
    try:
        from rag_service import SurveyRAGService
        rag_service = SurveyRAGService(db)
        logger.info("✅ RAG Service initialized successfully")
    except Exception as e:
        logger.error(f"⚠️ Failed to initialize RAG Service: {e}")
        rag_service = None


@rag_bp.route('/rag/ask', methods=['POST'])
def rag_ask_question():
    """
    RAG endpoint for answering questions about survey data.
    Uses Gemini 2.0 Flash Lite with database retrieval and grounding.
    
    Request body:
    {
        "question": "What surveys do we have from churches in Kenya?",
        "user_id": <optional>,
        "filters": {
            "organization_types": ["church"],
            "countries": ["Kenya"]
        }
    }
    """
    global rag_service
    
    if not rag_service:
        return jsonify({
            "error": "RAG Service is not available",
            "answer": "I'm sorry, but the AI service is currently unavailable. Please try again later."
        }), 503
    
    data = request.json
    question = data.get('question')
    
    if not question:
        return jsonify({"error": "Question is required"}), 400
    
    try:
        # Call RAG service
        result = rag_service.ask(
            question=question,
            user_id=data.get('user_id'),
            filters=data.get('filters', {})
        )
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error in RAG endpoint: {str(e)}")
        return jsonify({
            "error": str(e),
            "answer": "I encountered an error processing your question. Please try again."
        }), 500


@rag_bp.route('/parse-document', methods=['POST'])
def parse_document():
    """Parse uploaded document and return structured questions."""
    try:
        from document_parser import DocumentParserService
        
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        parser = DocumentParserService()
        result = parser.parse(file)
        
        return jsonify(result), 200
        
    except ImportError:
        return jsonify({"error": "Document parser service is not available"}), 503
    except Exception as e:
        logger.error(f"Error parsing document: {str(e)}")
        return jsonify({"error": str(e)}), 500
