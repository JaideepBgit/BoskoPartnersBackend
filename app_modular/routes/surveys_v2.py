"""
Surveys V2 routes — standalone surveys with many-to-many organization attachment.
Questions are stored as JSON on the survey (same pattern as survey_templates).
Completely independent from the legacy survey_templates / survey_template_versions tables.
"""
from flask import Blueprint, request, jsonify
from sqlalchemy import text
import logging

from ..config.database import db
from ..models.survey_v2 import SurveyV2, SurveyOrganization
from ..models.user import Title
from ..models.organization import Organization

logger = logging.getLogger(__name__)

surveys_v2_bp = Blueprint('surveys_v2', __name__)


# ============================================================================
# Surveys CRUD
# ============================================================================

@surveys_v2_bp.route('/v2/surveys', methods=['GET'])
def get_surveys():
    """Get all surveys with their organizations."""
    try:
        surveys = SurveyV2.query.all()
        result = []
        for s in surveys:
            org_names = [so.organization.name for so in s.organizations if so.organization]
            org_ids = [so.organization_id for so in s.organizations]
            questions = s.questions if s.questions else []
            result.append({
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "title_id": s.title_id,
                "title_name": s.title.name if s.title else None,
                "status": s.status,
                "sections": s.sections,
                "questions": questions,
                "question_count": len(questions),
                "organization_ids": org_ids,
                "organization_names": org_names,
                "organization_name": org_names[0] if org_names else None,
                "start_date": s.start_date.isoformat() if s.start_date else None,
                "end_date": s.end_date.isoformat() if s.end_date else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            })
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error getting surveys: {str(e)}")
        return jsonify({"error": str(e)}), 500


@surveys_v2_bp.route('/v2/surveys/<int:survey_id>', methods=['GET'])
def get_survey(survey_id):
    """Get a single survey with questions and organizations."""
    survey = SurveyV2.query.get_or_404(survey_id)
    try:
        org_list = [{
            "id": so.organization_id,
            "name": so.organization.name if so.organization else None,
        } for so in survey.organizations]

        questions = survey.questions if survey.questions else []

        # KPI counts from survey_responses_v2
        row = db.session.execute(text(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN status IN ('submitted','completed') THEN 1 ELSE 0 END) AS completed "
            "FROM survey_responses_v2 WHERE survey_id = :sid"
        ), {"sid": survey.id}).fetchone()
        invitation_count = row[0] if row else 0
        response_count = row[1] if row else 0

        return jsonify({
            "id": survey.id,
            "name": survey.name,
            "description": survey.description,
            "title_id": survey.title_id,
            "title_name": survey.title.name if survey.title else None,
            "status": survey.status,
            "sections": survey.sections,
            "questions": questions,
            "organizations": org_list,
            "organization_id": org_list[0]["id"] if org_list else None,
            "organization_name": org_list[0]["name"] if org_list else None,
            "start_date": survey.start_date.isoformat() if survey.start_date else None,
            "end_date": survey.end_date.isoformat() if survey.end_date else None,
            "invitation_count": invitation_count,
            "response_count": response_count,
            "reminder_count": 0,
            "created_at": survey.created_at.isoformat() if survey.created_at else None,
            "updated_at": survey.updated_at.isoformat() if survey.updated_at else None,
        }), 200
    except Exception as e:
        logger.error(f"Error getting survey {survey_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


@surveys_v2_bp.route('/v2/surveys', methods=['POST'])
def create_survey():
    """Create a new survey with questions (JSON) and organization attachments."""
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({"error": "name is required"}), 400

    try:
        # Handle title
        title_id = data.get('title_id')
        new_title_name = data.get('new_title_name')
        if new_title_name and not title_id:
            existing_title = Title.query.filter_by(name=new_title_name.strip()).first()
            if existing_title:
                title_id = existing_title.id
            else:
                new_title = Title(name=new_title_name.strip())
                db.session.add(new_title)
                db.session.flush()
                title_id = new_title.id

        survey = SurveyV2(
            name=name,
            description=data.get('description'),
            title_id=title_id,
            sections=data.get('sections'),
            questions=data.get('questions', []),
            status=data.get('status', 'draft'),
            start_date=data.get('start_date') or None,
            end_date=data.get('end_date') or None,
        )
        db.session.add(survey)
        db.session.flush()

        # Attach organizations
        for org_id in data.get('organization_ids', []):
            so = SurveyOrganization(survey_id=survey.id, organization_id=org_id)
            db.session.add(so)

        db.session.commit()
        return jsonify({"message": "Survey created successfully", "id": survey.id}), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating survey: {str(e)}")
        return jsonify({"error": str(e)}), 500


@surveys_v2_bp.route('/v2/surveys/<int:survey_id>', methods=['PUT'])
def update_survey(survey_id):
    """Update survey details including questions."""
    data = request.json
    survey = SurveyV2.query.get_or_404(survey_id)

    try:
        if 'name' in data:
            survey.name = data['name']
        if 'description' in data:
            survey.description = data['description']
        if 'status' in data:
            survey.status = data['status']
        if 'title_id' in data:
            survey.title_id = data['title_id']
        if 'sections' in data:
            survey.sections = data['sections']
        if 'questions' in data:
            survey.questions = data['questions']
        if 'start_date' in data:
            survey.start_date = data['start_date'] or None
        if 'end_date' in data:
            survey.end_date = data['end_date'] or None

        db.session.commit()
        return jsonify({"message": "Survey updated successfully", "id": survey.id}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating survey {survey_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


@surveys_v2_bp.route('/v2/surveys/<int:survey_id>', methods=['DELETE'])
def delete_survey(survey_id):
    """Delete a survey and all its organization links."""
    survey = SurveyV2.query.get_or_404(survey_id)

    try:
        db.session.delete(survey)  # cascade handles org links
        db.session.commit()
        return jsonify({"message": "Survey deleted successfully"}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting survey {survey_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


@surveys_v2_bp.route('/v2/surveys/<int:survey_id>/duplicate', methods=['POST'])
def duplicate_survey(survey_id):
    """Duplicate a survey with all its questions and organization links."""
    source = SurveyV2.query.get_or_404(survey_id)
    data = request.json or {}

    try:
        new_survey = SurveyV2(
            name=data.get('name', f"Copy of {source.name}"),
            description=data.get('description', source.description),
            title_id=source.title_id,
            sections=source.sections,
            questions=source.questions,
            status='draft',
            start_date=data.get('start_date') or source.start_date,
            end_date=data.get('end_date') or source.end_date,
        )
        db.session.add(new_survey)
        db.session.flush()

        # Organization handling: target org takes precedence over copy
        target_org_id = data.get('target_organization_id')
        if target_org_id:
            db.session.add(SurveyOrganization(
                survey_id=new_survey.id,
                organization_id=target_org_id,
            ))
        elif data.get('copy_organizations', True):
            for so in source.organizations:
                db.session.add(SurveyOrganization(
                    survey_id=new_survey.id,
                    organization_id=so.organization_id,
                ))

        db.session.commit()
        return jsonify({"message": "Survey duplicated successfully", "id": new_survey.id}), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error duplicating survey {survey_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# Organization attachment
# ============================================================================

@surveys_v2_bp.route('/v2/surveys/<int:survey_id>/organizations', methods=['GET'])
def get_survey_organizations(survey_id):
    """Get all organizations attached to a survey."""
    survey = SurveyV2.query.get_or_404(survey_id)

    orgs = [{
        "id": so.organization_id,
        "name": so.organization.name if so.organization else None,
        "attached_at": so.created_at.isoformat() if so.created_at else None,
    } for so in survey.organizations]

    return jsonify(orgs), 200


@surveys_v2_bp.route('/v2/surveys/<int:survey_id>/organizations', methods=['POST'])
def attach_organizations(survey_id):
    """Attach one or more organizations to a survey."""
    survey = SurveyV2.query.get_or_404(survey_id)
    data = request.json
    organization_ids = data.get('organization_ids', [])

    if not organization_ids:
        return jsonify({"error": "organization_ids is required"}), 400

    try:
        attached = []
        errors = []
        existing_org_ids = {so.organization_id for so in survey.organizations}

        for org_id in organization_ids:
            if org_id in existing_org_ids:
                org = Organization.query.get(org_id)
                errors.append(f"Already attached: {org.name if org else org_id}")
                continue

            org = Organization.query.get(org_id)
            if not org:
                errors.append(f"Organization {org_id} not found")
                continue

            so = SurveyOrganization(survey_id=survey.id, organization_id=org_id)
            db.session.add(so)
            attached.append({"id": org_id, "name": org.name})

        db.session.commit()
        return jsonify({
            "message": f"Attached {len(attached)} organization(s)",
            "attached": attached,
            "errors": errors,
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error attaching orgs to survey {survey_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


@surveys_v2_bp.route('/v2/surveys/<int:survey_id>/organizations/<int:org_id>', methods=['DELETE'])
def detach_organization(survey_id, org_id):
    """Detach an organization from a survey."""
    link = SurveyOrganization.query.filter_by(
        survey_id=survey_id, organization_id=org_id
    ).first()

    if not link:
        return jsonify({"error": "Organization is not attached to this survey"}), 404

    try:
        db.session.delete(link)
        db.session.commit()
        return jsonify({"message": "Organization detached successfully"}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error detaching org {org_id} from survey {survey_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# Sections
# ============================================================================

@surveys_v2_bp.route('/v2/surveys/<int:survey_id>/sections', methods=['GET'])
def get_sections(survey_id):
    """Get sections for a survey."""
    survey = SurveyV2.query.get_or_404(survey_id)
    return jsonify(survey.sections or []), 200


@surveys_v2_bp.route('/v2/surveys/<int:survey_id>/sections', methods=['PUT'])
def update_sections(survey_id):
    """Update sections for a survey."""
    survey = SurveyV2.query.get_or_404(survey_id)
    data = request.json

    try:
        survey.sections = data.get('sections', [])
        db.session.commit()
        return jsonify({"message": "Sections updated", "sections": survey.sections}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating sections for survey {survey_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500
