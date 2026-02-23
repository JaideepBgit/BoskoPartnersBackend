"""
Survey response routes.
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import logging

from ..config.database import db
from ..models.survey import SurveyResponse, SurveyTemplate

logger = logging.getLogger(__name__)

survey_responses_bp = Blueprint('survey_responses', __name__)


@survey_responses_bp.route('/responses', methods=['GET'])
def get_responses():
    """Get all survey responses."""
    try:
        user_id = request.args.get('user_id', type=int)
        template_id = request.args.get('template_id', type=int)
        status = request.args.get('status')

        query = SurveyResponse.query

        if user_id:
            query = query.filter_by(user_id=user_id)
        if template_id:
            query = query.filter_by(template_id=template_id)
        if status:
            query = query.filter_by(status=status)

        responses = query.all()

        result = []
        for r in responses:
            data = r.to_dict()
            # Include user details for display
            if r.user:
                data['user_name'] = f"{r.user.firstname or ''} {r.user.lastname or ''}".strip() or r.user.username
                data['user_email'] = r.user.email
            # Calculate progress from answers
            if r.answers and r.template:
                total_questions = len(r.template.question_list)
                answered = len(r.answers) if isinstance(r.answers, dict) else 0
                data['progress'] = round((answered / total_questions) * 100) if total_questions > 0 else 0
            else:
                data['progress'] = 100 if r.status == 'completed' else 0
            # Map submitted_at from updated_at when completed
            if r.status == 'completed':
                data['submitted_at'] = r.updated_at.isoformat() if r.updated_at else None
            result.append(data)

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting responses: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_responses_bp.route('/responses/<int:response_id>', methods=['GET'])
def get_response(response_id):
    """Get a specific survey response."""
    response = SurveyResponse.query.get_or_404(response_id)
    return jsonify(response.to_dict()), 200


@survey_responses_bp.route('/templates/<int:template_id>/responses', methods=['POST'])
def add_response(template_id):
    """Create or update a survey response."""
    data = request.json
    user_id = data.get('user_id')
    
    # Check if template exists
    template = SurveyTemplate.query.get_or_404(template_id)
    
    try:
        # Check if response already exists for this user and template
        existing = SurveyResponse.query.filter_by(
            template_id=template_id,
            user_id=user_id
        ).first()
        
        if existing:
            # Update existing response
            existing.answers = data.get('answers', existing.answers)
            existing.status = data.get('status', existing.status)
            db.session.commit()
            
            return jsonify({
                "message": "Response updated successfully",
                "id": existing.id
            }), 200
        else:
            # Create new response
            response = SurveyResponse(
                template_id=template_id,
                user_id=user_id,
                answers=data.get('answers', {}),
                status=data.get('status', 'draft'),
                start_date=datetime.utcnow()
            )
            db.session.add(response)
            db.session.commit()
            
            return jsonify({
                "message": "Response created successfully",
                "id": response.id
            }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating/updating response: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_responses_bp.route('/responses/<int:response_id>', methods=['PUT'])
def update_response(response_id):
    """Update a survey response."""
    data = request.json
    response = SurveyResponse.query.get_or_404(response_id)
    
    try:
        if 'answers' in data:
            response.answers = data['answers']
        if 'status' in data:
            response.status = data['status']
            if data['status'] == 'submitted':
                response.end_date = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            "message": "Response updated successfully",
            "id": response.id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating response: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_responses_bp.route('/responses/<int:response_id>/dates', methods=['PUT'])
def update_response_dates(response_id):
    """Update start_date and end_date for a survey response."""
    data = request.json
    response = SurveyResponse.query.get_or_404(response_id)
    
    try:
        if 'start_date' in data and data['start_date']:
            response.start_date = datetime.fromisoformat(data['start_date'].replace('Z', '+00:00'))
        if 'end_date' in data and data['end_date']:
            response.end_date = datetime.fromisoformat(data['end_date'].replace('Z', '+00:00'))
        
        db.session.commit()
        
        return jsonify({
            "message": "Response dates updated successfully",
            "id": response.id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating response dates: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_responses_bp.route('/users/<int:user_id>/templates/<int:template_id>/response', methods=['GET'])
def get_user_template_response(user_id, template_id):
    """Get existing survey response for a specific user and template."""
    response = SurveyResponse.query.filter_by(
        user_id=user_id,
        template_id=template_id
    ).first()
    
    if not response:
        return jsonify({"message": "No response found"}), 404
    
    return jsonify(response.to_dict()), 200


@survey_responses_bp.route('/users/<int:user_id>/responses', methods=['GET'])
def get_user_survey_responses(user_id):
    """Get all survey responses for a specific user."""
    try:
        responses = SurveyResponse.query.filter_by(user_id=user_id).all()
        
        result = []
        for r in responses:
            response_data = r.to_dict()
            if r.template:
                response_data['template_name'] = r.template.name
                response_data['template_description'] = r.template.description
            result.append(response_data)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error getting user responses: {str(e)}")
        return jsonify({"error": str(e)}), 500
