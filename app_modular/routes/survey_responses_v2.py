"""
Survey response routes for surveys_v2.
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import logging

from ..config.database import db
from ..models.survey_v2 import SurveyResponseV2, SurveyV2

logger = logging.getLogger(__name__)

survey_responses_v2_bp = Blueprint('survey_responses_v2', __name__)


@survey_responses_v2_bp.route('/v2/responses', methods=['GET'])
def get_responses():
    """Get all survey responses with optional filters."""
    try:
        user_id = request.args.get('user_id', type=int)
        survey_id = request.args.get('survey_id', type=int)
        organization_id = request.args.get('organization_id', type=int)
        status = request.args.get('status')

        query = SurveyResponseV2.query

        if user_id:
            query = query.filter_by(user_id=user_id)
        if survey_id:
            query = query.filter_by(survey_id=survey_id)
        if organization_id:
            query = query.filter_by(organization_id=organization_id)
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
            # Calculate progress from answers vs questions JSON
            if r.answers and r.survey and r.survey.questions:
                total_questions = len(r.survey.questions) if isinstance(r.survey.questions, list) else 0
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
        logger.error(f"Error getting v2 responses: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_responses_v2_bp.route('/v2/responses/<int:response_id>', methods=['GET'])
def get_response(response_id):
    """Get a specific survey response."""
    response = SurveyResponseV2.query.get_or_404(response_id)
    return jsonify(response.to_dict()), 200


@survey_responses_v2_bp.route('/v2/surveys/<int:survey_id>/responses', methods=['POST'])
def add_response(survey_id):
    """Create or update a survey response."""
    data = request.json
    user_id = data.get('user_id')

    # Check if survey exists
    survey = SurveyV2.query.get_or_404(survey_id)

    try:
        # Check if response already exists for this user and survey
        existing = SurveyResponseV2.query.filter_by(
            survey_id=survey_id,
            user_id=user_id
        ).first()

        if existing:
            # Update existing response
            existing.answers = data.get('answers', existing.answers)
            existing.status = data.get('status', existing.status)
            if 'organization_id' in data:
                existing.organization_id = data['organization_id']
            db.session.commit()

            return jsonify({
                "message": "Response updated successfully",
                "id": existing.id
            }), 200
        else:
            # Create new response
            response = SurveyResponseV2(
                survey_id=survey_id,
                user_id=user_id,
                organization_id=data.get('organization_id'),
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
        logger.error(f"Error creating/updating v2 response: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_responses_v2_bp.route('/v2/responses/<int:response_id>', methods=['PUT'])
def update_response(response_id):
    """Update a survey response."""
    data = request.json
    response = SurveyResponseV2.query.get_or_404(response_id)

    try:
        if 'answers' in data:
            response.answers = data['answers']
        if 'status' in data:
            response.status = data['status']
            if data['status'] == 'submitted':
                response.end_date = datetime.utcnow()
        if 'organization_id' in data:
            response.organization_id = data['organization_id']

        db.session.commit()

        return jsonify({
            "message": "Response updated successfully",
            "id": response.id
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating v2 response: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_responses_v2_bp.route('/v2/responses/<int:response_id>/dates', methods=['PUT'])
def update_response_dates(response_id):
    """Update start_date and end_date for a survey response."""
    data = request.json
    response = SurveyResponseV2.query.get_or_404(response_id)

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
        logger.error(f"Error updating v2 response dates: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_responses_v2_bp.route('/v2/users/<int:user_id>/surveys/<int:survey_id>/response', methods=['GET'])
def get_user_survey_response(user_id, survey_id):
    """Get existing survey response for a specific user and survey."""
    response = SurveyResponseV2.query.filter_by(
        user_id=user_id,
        survey_id=survey_id
    ).first()

    if not response:
        return jsonify({"message": "No response found"}), 404

    return jsonify(response.to_dict()), 200


@survey_responses_v2_bp.route('/v2/surveys/<int:survey_id>/join', methods=['POST'])
def join_survey(survey_id):
    """Self-assign a user to a survey via shareable link / QR code.

    Idempotent: returns the existing response if the user already has one.
    """
    from ..models.user import User

    data = request.json or {}
    user_id = data.get('user_id')

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    survey = SurveyV2.query.get(survey_id)
    if not survey:
        return jsonify({"error": "Survey not found"}), 404

    if survey.status not in ('open', 'draft'):
        return jsonify({"error": "This survey is no longer accepting responses"}), 403

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    try:
        # Idempotent — return existing response if one exists
        existing = SurveyResponseV2.query.filter_by(
            survey_id=survey_id,
            user_id=user_id
        ).first()

        if existing:
            response_data = existing.to_dict()
        else:
            new_response = SurveyResponseV2(
                survey_id=survey_id,
                user_id=user_id,
                organization_id=user.organization_id,
                answers={},
                status='pending',
                start_date=datetime.utcnow()
            )
            db.session.add(new_response)
            db.session.commit()
            response_data = new_response.to_dict()

        # Include survey details the frontend needs
        response_data['survey_name'] = survey.name
        response_data['survey_description'] = survey.description
        response_data['questions_count'] = len(survey.questions) if isinstance(survey.questions, list) else 0

        return jsonify(response_data), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error joining survey {survey_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_responses_v2_bp.route('/v2/users/<int:user_id>/responses', methods=['GET'])
def get_user_responses(user_id):
    """Get all survey responses for a specific user."""
    try:
        responses = SurveyResponseV2.query.filter_by(user_id=user_id).all()

        result = []
        for r in responses:
            response_data = r.to_dict()
            if r.survey:
                response_data['survey_name'] = r.survey.name
                response_data['survey_description'] = r.survey.description
            result.append(response_data)

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting user v2 responses: {str(e)}")
        return jsonify({"error": str(e)}), 500
