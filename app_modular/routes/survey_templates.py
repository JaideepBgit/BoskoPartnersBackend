"""
Survey template management routes.
"""
from flask import Blueprint, request, jsonify
import logging

from ..config.database import db
from ..models.survey import SurveyTemplate, SurveyTemplateVersion, SurveyVersion, SurveyResponse
from ..models.question import Question, QuestionType, QuestionOption
from ..models.user import Title, UserOrganizationTitle
from ..models.reminder import SurveyReminderLog, SurveyReminderSetting

logger = logging.getLogger(__name__)

survey_templates_bp = Blueprint('survey_templates', __name__)


@survey_templates_bp.route('/template-versions', methods=['GET'])
def get_template_versions():
    """Get all survey template versions."""
    try:
        organization_id = request.args.get('organization_id', type=int)
        
        query = SurveyTemplateVersion.query
        if organization_id:
            query = query.filter_by(organization_id=organization_id)
        
        versions = query.all()
        
        return jsonify([{
            "id": v.id,
            "name": v.name,
            "description": v.description,
            "organization_id": v.organization_id,
            "organization_name": v.organization.name if v.organization else None,
            "template_count": len(v.templates),
            "created_at": v.created_at.isoformat() if v.created_at else None
        } for v in versions]), 200
        
    except Exception as e:
        logger.error(f"Error getting template versions: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/template-versions', methods=['POST'])
def add_template_version():
    """Create a new template version."""
    data = request.json
    
    name = data.get('name')
    if not name:
        return jsonify({"error": "Version name is required"}), 400
    
    try:
        version = SurveyTemplateVersion(
            name=name,
            description=data.get('description'),
            organization_id=data.get('organization_id')
        )
        db.session.add(version)
        db.session.commit()
        
        return jsonify({
            "message": "Template version created successfully",
            "id": version.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating template version: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/template-versions/<int:version_id>', methods=['PUT'])
def update_template_version(version_id):
    """Update a template version."""
    data = request.json
    version = SurveyTemplateVersion.query.get_or_404(version_id)
    
    try:
        if 'name' in data:
            version.name = data['name']
        if 'description' in data:
            version.description = data['description']
        
        db.session.commit()
        
        return jsonify({
            "message": "Template version updated successfully",
            "id": version.id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating template version: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/template-versions/<int:version_id>', methods=['DELETE'])
def delete_template_version(version_id):
    """Delete a template version and all associated templates."""
    version = SurveyTemplateVersion.query.get_or_404(version_id)
    
    try:
        # Delete all templates in this version
        for template in version.templates:
            # Delete questions
            Question.query.filter_by(template_id=template.id).delete()
        
        SurveyTemplate.query.filter_by(version_id=version_id).delete()
        db.session.delete(version)
        db.session.commit()
        
        return jsonify({"message": "Template version deleted successfully"}), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting template version: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/templates', methods=['GET'])
def get_templates():
    """Get all survey templates."""
    try:
        version_id = request.args.get('version_id', type=int)
        organization_id = request.args.get('organization_id', type=int)
        
        query = SurveyTemplate.query
        
        if version_id:
            query = query.filter_by(version_id=version_id)
        
        if organization_id:
            query = query.join(SurveyTemplateVersion).filter(
                SurveyTemplateVersion.organization_id == organization_id
            )
        
        templates = query.all()
        
        return jsonify([{
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "version_id": t.version_id,
            "version_name": t.version.name if t.version else None,
            "title_id": t.title_id,
            "title_name": t.title.name if t.title else None,
            "sections": t.sections,
            "question_count": len(t.question_list),
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None
        } for t in templates]), 200
        
    except Exception as e:
        logger.error(f"Error getting templates: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/templates/<int:template_id>', methods=['GET'])
def get_template(template_id):
    """Get a specific template with questions."""
    template = SurveyTemplate.query.get_or_404(template_id)
    
    # Get questions with their options
    questions = []
    for q in sorted(template.question_list, key=lambda x: x.sort_order):
        question_data = {
            "id": q.id,
            "question_text": q.question_text,
            "type_id": q.type_id,
            "type_name": q.type.name if q.type else None,
            "sort_order": q.sort_order,
            "is_required": q.is_required,
            "config": q.config,
            "section": q.section,
            "options": [{
                "id": opt.id,
                "option_text": opt.option_text,
                "sort_order": opt.sort_order
            } for opt in sorted(q.options, key=lambda x: x.sort_order)]
        }
        questions.append(question_data)
    
    # Calculate survey performance metrics
    all_responses = SurveyResponse.query.filter_by(template_id=template.id).all()
    invitation_count = len(all_responses)
    response_count = len([r for r in all_responses if r.status == 'completed'])

    # Count reminders actually sent for this template
    reminder_count = SurveyReminderLog.query.filter_by(
        template_id=template.id, status='sent'
    ).count()

    return jsonify({
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "version_id": template.version_id,
        "version_name": template.version.name if template.version else None,
        "organization_id": template.version.organization_id if template.version else None,
        "organization_name": template.version.organization.name if template.version and template.version.organization else None,
        "title_id": template.title_id,
        "title_name": template.title.name if template.title else None,
        "sections": template.sections,
        "questions": questions,
        "invitation_count": invitation_count,
        "response_count": response_count,
        "reminder_count": reminder_count,
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None
    }), 200


@survey_templates_bp.route('/templates', methods=['POST'])
def add_template():
    """Create a new survey template."""
    data = request.json
    
    name = data.get('name')
    version_id = data.get('version_id')
    
    if not name or not version_id:
        return jsonify({"error": "Name and version_id are required"}), 400
    
    try:
        # Handle title_id - can be an existing ID or a new title name
        title_id = data.get('title_id')
        new_title_name = data.get('new_title_name')
        
        if new_title_name and not title_id:
            # Create a new title if a name was provided
            existing_title = Title.query.filter_by(name=new_title_name.strip()).first()
            if existing_title:
                title_id = existing_title.id
            else:
                new_title = Title(name=new_title_name.strip())
                db.session.add(new_title)
                db.session.flush()
                title_id = new_title.id
                logger.info(f"Created new title '{new_title_name.strip()}' with ID: {title_id}")
        
        template = SurveyTemplate(
            name=name,
            description=data.get('description'),
            version_id=version_id,
            title_id=title_id,
            sections=data.get('sections')
        )
        db.session.add(template)
        db.session.flush()
        
        # Add questions if provided
        questions = data.get('questions', [])
        for i, q_data in enumerate(questions):
            question = Question(
                template_id=template.id,
                type_id=q_data.get('type_id', 1),
                question_text=q_data.get('question_text', ''),
                sort_order=q_data.get('sort_order', i),
                is_required=q_data.get('is_required', False),
                config=q_data.get('config'),
                section=q_data.get('section')
            )
            db.session.add(question)
            db.session.flush()
            
            # Add options if provided
            for j, opt_data in enumerate(q_data.get('options', [])):
                option = QuestionOption(
                    question_id=question.id,
                    option_text=opt_data.get('option_text', ''),
                    sort_order=opt_data.get('sort_order', j)
                )
                db.session.add(option)
        
        db.session.commit()
        
        return jsonify({
            "message": "Template created successfully",
            "id": template.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating template: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/templates/<int:template_id>', methods=['PUT'])
def update_template(template_id):
    """Update a survey template."""
    data = request.json
    template = SurveyTemplate.query.get_or_404(template_id)
    
    try:
        if 'name' in data:
            template.name = data['name']
        if 'description' in data:
            template.description = data['description']
        if 'sections' in data:
            template.sections = data['sections']
        if 'title_id' in data:
            template.title_id = data['title_id']
        
        db.session.commit()
        
        return jsonify({
            "message": "Template updated successfully",
            "id": template.id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating template: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/templates/<int:template_id>', methods=['DELETE'])
def delete_template(template_id):
    """Delete a survey template and its questions."""
    template = SurveyTemplate.query.get_or_404(template_id)
    
    try:
        # Delete question options
        for q in template.question_list:
            QuestionOption.query.filter_by(question_id=q.id).delete()
        
        # Delete questions
        Question.query.filter_by(template_id=template_id).delete()
        
        db.session.delete(template)
        db.session.commit()
        
        return jsonify({"message": "Template deleted successfully"}), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting template: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/question-types', methods=['GET'])
def get_question_types():
    """Get all question types."""
    try:
        category = request.args.get('category')
        
        query = QuestionType.query.filter_by(is_active=True)
        if category:
            query = query.filter_by(category=category)
        
        types = query.all()
        
        return jsonify([t.to_dict() for t in types]), 200
        
    except Exception as e:
        logger.error(f"Error getting question types: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/question-types/<int:type_id>', methods=['GET'])
def get_question_type(type_id):
    """Get a specific question type."""
    q_type = QuestionType.query.get_or_404(type_id)
    return jsonify(q_type.to_dict()), 200


@survey_templates_bp.route('/templates/<int:template_id>/sections', methods=['GET'])
def get_template_sections(template_id):
    """Get sections for a template."""
    template = SurveyTemplate.query.get_or_404(template_id)
    return jsonify(template.sections or []), 200


@survey_templates_bp.route('/templates/<int:template_id>/sections', methods=['PUT'])
def update_template_sections(template_id):
    """Update sections for a template."""
    data = request.json
    template = SurveyTemplate.query.get_or_404(template_id)
    
    try:
        template.sections = data.get('sections', [])
        db.session.commit()
        
        return jsonify({
            "message": "Sections updated successfully",
            "sections": template.sections
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating sections: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/templates/<int:template_id>/questions/<int:question_id>', methods=['DELETE'])
def delete_template_question(template_id, question_id):
    """Delete a specific question from a template."""
    question = Question.query.filter_by(id=question_id, template_id=template_id).first_or_404()
    
    try:
        # Delete question options
        QuestionOption.query.filter_by(question_id=question_id).delete()
        
        db.session.delete(question)
        db.session.commit()
        
        return jsonify({"message": "Question deleted successfully"}), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting question: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/templates/<int:template_id>/copy', methods=['POST'])
def copy_template_to_organization(template_id):
    """Copy a template to another organization's template version."""
    data = request.json
    target_version_id = data.get('target_version_id')
    new_name = data.get('new_name')
    
    if not target_version_id:
        return jsonify({"error": "target_version_id is required"}), 400
    
    source_template = SurveyTemplate.query.get_or_404(template_id)
    target_version = SurveyTemplateVersion.query.get_or_404(target_version_id)
    
    try:
        # Create new template
        new_template = SurveyTemplate(
            name=new_name or f"Copy of {source_template.name}",
            description=source_template.description,
            version_id=target_version_id,
            title_id=source_template.title_id,
            sections=source_template.sections
        )
        db.session.add(new_template)
        db.session.flush()
        
        # Copy questions
        for q in source_template.question_list:
            new_question = Question(
                template_id=new_template.id,
                type_id=q.type_id,
                question_text=q.question_text,
                sort_order=q.sort_order,
                is_required=q.is_required,
                config=q.config,
                section=q.section
            )
            db.session.add(new_question)
            db.session.flush()
            
            # Copy options
            for opt in q.options:
                new_option = QuestionOption(
                    question_id=new_question.id,
                    option_text=opt.option_text,
                    sort_order=opt.sort_order
                )
                db.session.add(new_option)
        
        db.session.commit()
        
        return jsonify({
            "message": "Template copied successfully",
            "new_template_id": new_template.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error copying template: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/template-versions/<int:version_id>/copy', methods=['POST'])
def copy_template_version_to_organization(version_id):
    """Copy a template version and all its templates to another organization."""
    data = request.json
    target_organization_id = data.get('target_organization_id')
    new_name = data.get('new_name')
    
    if not target_organization_id:
        return jsonify({"error": "target_organization_id is required"}), 400
    
    source_version = SurveyTemplateVersion.query.get_or_404(version_id)
    
    try:
        # Create new version
        new_version = SurveyTemplateVersion(
            name=new_name or f"Copy of {source_version.name}",
            description=source_version.description,
            organization_id=target_organization_id
        )
        db.session.add(new_version)
        db.session.flush()
        
        # Copy all templates in version
        for template in source_version.templates:
            new_template = SurveyTemplate(
                name=template.name,
                description=template.description,
                version_id=new_version.id,
                title_id=template.title_id,
                sections=template.sections
            )
            db.session.add(new_template)
            db.session.flush()
            
            # Copy questions
            for q in template.question_list:
                new_question = Question(
                    template_id=new_template.id,
                    type_id=q.type_id,
                    question_text=q.question_text,
                    sort_order=q.sort_order,
                    is_required=q.is_required,
                    config=q.config,
                    section=q.section
                )
                db.session.add(new_question)
                db.session.flush()
                
                for opt in q.options:
                    new_option = QuestionOption(
                        question_id=new_question.id,
                        option_text=opt.option_text,
                        sort_order=opt.sort_order
                    )
                    db.session.add(new_option)
        
        db.session.commit()
        
        return jsonify({
            "message": "Template version copied successfully",
            "new_version_id": new_version.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error copying template version: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/available-templates', methods=['GET'])
def get_available_survey_templates():
    """Get all available survey templates with complete information for users."""
    try:
        templates = SurveyTemplate.query.all()
        
        result = []
        for t in templates:
            result.append({
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "version_id": t.version_id,
                "version_name": t.version.name if t.version else None,
                "title_id": t.title_id,
                "title_name": t.title.name if t.title else None,
                "organization_id": t.version.organization_id if t.version else None,
                "organization_name": t.version.organization.name if t.version and t.version.organization else None,
                "question_count": len(t.question_list),
                "sections": t.sections,
                "created_at": t.created_at.isoformat() if t.created_at else None
            })
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error getting available templates: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/organizations/<int:org_id>/templates', methods=['GET'])
def get_survey_templates_by_organization(org_id):
    """Get survey templates for a specific organization for dropdown population."""
    try:
        templates = SurveyTemplate.query.join(SurveyTemplateVersion).filter(
            SurveyTemplateVersion.organization_id == org_id
        ).all()
        
        return jsonify([{
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "version_name": t.version.name if t.version else None,
            "title_id": t.title_id,
            "title_name": t.title.name if t.title else None
        } for t in templates]), 200
        
    except Exception as e:
        logger.error(f"Error getting organization templates: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/titles', methods=['GET'])
def get_all_titles():
    """Get all available titles for dropdown."""
    try:
        titles = Title.query.order_by(Title.name).all()
        return jsonify([{
            'id': t.id,
            'name': t.name
        } for t in titles]), 200
    except Exception as e:
        logger.error(f"Error getting titles: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/titles', methods=['POST'])
def create_title():
    """Create a new title."""
    data = request.json
    name = data.get('name', '').strip()
    
    if not name:
        return jsonify({"error": "Title name is required"}), 400
    
    try:
        # Check if title already exists
        existing = Title.query.filter_by(name=name).first()
        if existing:
            return jsonify({
                "id": existing.id,
                "name": existing.name,
                "message": "Title already exists"
            }), 200
        
        title = Title(name=name)
        db.session.add(title)
        db.session.commit()
        
        return jsonify({
            "id": title.id,
            "name": title.name,
            "message": "Title created successfully"
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating title: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/survey-assignments', methods=['POST'])
def assign_survey_to_user():
    """Assign a survey to existing user(s) and send email notifications.
    Also creates user_organization_titles record if the template has a title_id."""
    from ..models.survey import SurveyResponse
    from ..models.user import User
    from ..services.email_service import email_service
    
    data = request.json
    user_ids = data.get('user_ids', [])
    template_id = data.get('template_id')
    send_email = data.get('send_email', True)
    
    if not user_ids or not template_id:
        return jsonify({"error": "user_ids and template_id are required"}), 400
    
    template = SurveyTemplate.query.get_or_404(template_id)
    
    # Get the organization_id from the template's version
    organization_id = template.version.organization_id if template.version else None
    
    try:
        assigned_users = []
        errors = []
        
        for user_id in user_ids:
            user = User.query.get(user_id)
            if not user:
                errors.append(f"User {user_id} not found")
                continue
            
            # Check if assignment already exists
            existing = SurveyResponse.query.filter_by(
                user_id=user_id,
                template_id=template_id
            ).first()
            
            if existing:
                errors.append(f"User {user.username} already has this survey assigned")
                continue
            
            # Create survey response entry
            response = SurveyResponse(
                user_id=user_id,
                template_id=template_id,
                status='assigned',
                answers={}
            )
            db.session.add(response)
            
            # Create user_organization_titles record if template has a title and organization
            if template.title_id and organization_id:
                existing_uot = UserOrganizationTitle.query.filter_by(
                    user_id=user_id,
                    organization_id=organization_id,
                    title_id=template.title_id
                ).first()
                
                if not existing_uot:
                    uot = UserOrganizationTitle(
                        user_id=user_id,
                        organization_id=organization_id,
                        title_id=template.title_id
                    )
                    db.session.add(uot)
                    logger.info(f"Created user_organization_title: user={user_id}, org={organization_id}, title={template.title_id}")
            
            assigned_users.append({
                "user_id": user_id,
                "username": user.username,
                "email": user.email
            })
            
            # Send email if enabled
            if send_email and user.email:
                try:
                    # Get survey name from template's survey_code or version name
                    survey_name = template.survey_code
                    if template.version:
                        survey_name = f"{template.version.name} - {template.survey_code}"
                    
                    email_service.send_survey_assignment_email(
                        to_email=user.email,
                        username=user.username,
                        password=user.password,
                        survey_code=user.survey_code,
                        firstname=user.firstname,
                        survey_name=survey_name
                    )
                except Exception as e:
                    logger.error(f"Failed to send email to {user.email}: {str(e)}")
        
        db.session.commit()
        
        return jsonify({
            "message": f"Survey assigned to {len(assigned_users)} users",
            "assigned_users": assigned_users,
            "errors": errors
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error assigning survey: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/users/<int:user_id>/survey-assignments', methods=['GET'])
def get_user_survey_assignments(user_id):
    """Get all survey assignments for a specific user."""
    from ..models.survey import SurveyResponse
    from ..models.user import User
    
    user = User.query.get_or_404(user_id)
    
    try:
        responses = SurveyResponse.query.filter_by(user_id=user_id).all()
        
        result = []
        for r in responses:
            # Get template name from survey_code or version name
            template_name = None
            if r.template:
                template_name = r.template.survey_code
                if r.template.version:
                    template_name = f"{r.template.version.name} - {r.template.survey_code}"
            
            result.append({
                "id": r.id,
                "template_id": r.template_id,
                "template_name": template_name,
                "status": r.status,
                "assigned_at": r.created_at.isoformat() if r.created_at else None,
                "start_date": r.start_date.isoformat() if r.start_date else None,
                "end_date": r.end_date.isoformat() if r.end_date else None
            })
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error getting user survey assignments: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/users/<int:user_id>/survey-assignments/<int:assignment_id>', methods=['DELETE'])
def remove_survey_assignment(user_id, assignment_id):
    """Remove a survey assignment and its associated survey response."""
    from ..models.survey import SurveyResponse
    
    response = SurveyResponse.query.filter_by(
        id=assignment_id,
        user_id=user_id
    ).first_or_404()
    
    try:
        db.session.delete(response)
        db.session.commit()
        
        return jsonify({"message": "Survey assignment removed successfully"}), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error removing survey assignment: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/question-types/categories', methods=['GET'])
def get_question_type_categories():
    """Get all unique question type categories."""
    try:
        categories = db.session.query(QuestionType.category).distinct().all()
        return jsonify([c[0] for c in categories if c[0]]), 200
    except Exception as e:
        logger.error(f"Error getting question type categories: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/question-types/numeric', methods=['GET'])
def get_numeric_question_types():
    """Get all question types that are always numeric."""
    try:
        numeric_types = ['number', 'rating', 'slider', 'ranking', 'constant_sum']
        types = QuestionType.query.filter(
            QuestionType.name.in_(numeric_types),
            QuestionType.is_active == True
        ).all()
        return jsonify([t.to_dict() for t in types]), 200
    except Exception as e:
        logger.error(f"Error getting numeric question types: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/question-types/non-numeric', methods=['GET'])
def get_non_numeric_question_types():
    """Get all question types that are always non-numeric."""
    try:
        non_numeric_types = ['text', 'long_text', 'date', 'file_upload', 'yes_no', 'multi_select', 'paragraph']
        types = QuestionType.query.filter(
            QuestionType.name.in_(non_numeric_types),
            QuestionType.is_active == True
        ).all()
        return jsonify([t.to_dict() for t in types]), 200
    except Exception as e:
        logger.error(f"Error getting non-numeric question types: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/question-types/conditional', methods=['GET'])
def get_conditional_question_types():
    """Get all question types that may be numeric or non-numeric depending on content."""
    try:
        # Based on QUESTION_TYPE_REFERENCE.md: IDs 1, 2, 9 are conditional
        conditional_types = ['short_text', 'single_choice', 'flexible_input']
        types = QuestionType.query.filter(
            QuestionType.name.in_(conditional_types),
            QuestionType.is_active == True
        ).all()
        
        return jsonify([{
            'id': qt.id,
            'name': qt.name,
            'display_name': qt.display_name,
            'category': qt.category,
            'description': qt.description,
            'is_conditional': True
        } for qt in types]), 200
        
    except Exception as e:
        logger.error(f"Error getting conditional question types: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/question-types/classify', methods=['POST'])
def classify_question_endpoint():
    """Classify a question as numeric or non-numeric."""
    try:
        from text_analytics import classify_question_type
        
        data = request.get_json()
        question_text = data.get('question_text', '')
        question_metadata = data.get('metadata', {})
        
        if not question_text:
            return jsonify({'error': 'question_text is required'}), 400
        
        classification = classify_question_type(question_text, question_metadata)
        
        return jsonify(classification), 200
        
    except ImportError:
        # Fallback if text_analytics module is not available
        return jsonify({
            'is_numeric': False,
            'confidence': 0.5,
            'reason': 'Text analytics module not available'
        }), 200
    except Exception as e:
        logger.error(f"Error classifying question: {str(e)}")
        return jsonify({"error": str(e)}), 500


@survey_templates_bp.route('/question-types/initialize', methods=['POST'])
def initialize_question_types():
    """Initialize the database with the nine core question types only."""
    try:
        # Nine core question types data
        question_types_data = [
            {
                'id': 1, 'name': 'short_text', 'display_name': 'Short Text',
                'category': 'Core Questions', 'description': 'Brief free-text responses and fill-in-the-blank fields',
                'config_schema': {'max_length': 255, 'placeholder': '', 'required': False}
            },
            {
                'id': 2, 'name': 'single_choice', 'display_name': 'Single Choice',
                'category': 'Core Questions', 'description': 'Radio button selection from predefined categorical options',
                'config_schema': {'options': [], 'required': False}
            },
            {
                'id': 3, 'name': 'yes_no', 'display_name': 'Yes/No',
                'category': 'Core Questions', 'description': 'Binary choice questions for clear decision points',
                'config_schema': {'yes_label': 'Yes', 'no_label': 'No', 'required': False}
            },
            {
                'id': 4, 'name': 'likert5', 'display_name': 'Five-Point Likert Scale',
                'category': 'Core Questions', 'description': 'Five-point scale from "A great deal" to "None"',
                'config_schema': {'scale_labels': {1: 'None', 2: 'A little', 3: 'A moderate amount', 4: 'A lot', 5: 'A great deal'}, 'required': False}
            },
            {
                'id': 5, 'name': 'multi_select', 'display_name': 'Multiple Select',
                'category': 'Core Questions', 'description': '"Select all that apply" checkbox questions',
                'config_schema': {'options': [], 'required': False}
            },
            {
                'id': 6, 'name': 'paragraph', 'display_name': 'Paragraph Text',
                'category': 'Core Questions', 'description': 'Open-ended narrative and essay responses',
                'config_schema': {'max_length': 2000, 'placeholder': '', 'required': False}
            },
            {
                'id': 7, 'name': 'numeric', 'display_name': 'Numeric Entry',
                'category': 'Core Questions', 'description': 'Absolute number input with validation',
                'config_schema': {'number_type': 'integer', 'min_value': None, 'max_value': None, 'required': False}
            },
            {
                'id': 8, 'name': 'percentage', 'display_name': 'Percentage Allocation',
                'category': 'Core Questions', 'description': 'Distribution and allocation percentage questions',
                'config_schema': {'items': [], 'total_percentage': 100, 'allow_decimals': False, 'required': False}
            },
            {
                'id': 9, 'name': 'flexible_input', 'display_name': 'Flexible Input',
                'category': 'Core Questions', 'description': 'Collect alphanumeric responses across multiple items',
                'config_schema': {'items': [], 'instructions': '', 'placeholder': 'Enter your response', 'required': False}
            },
            {
                'id': 10, 'name': 'year_matrix', 'display_name': 'Year Matrix',
                'category': 'Core Questions', 'description': 'Row-by-year grid for temporal data collection',
                'config_schema': {'rows': [], 'start_year': 2024, 'end_year': 2029, 'required': False}
            }
        ]
        
        # Clear existing question types and add new ones
        QuestionType.query.delete()
        
        for qt_data in question_types_data:
            question_type = QuestionType(
                id=qt_data['id'],
                name=qt_data['name'],
                display_name=qt_data['display_name'],
                category=qt_data['category'],
                description=qt_data['description'],
                config_schema=qt_data['config_schema'],
                is_active=True
            )
            db.session.add(question_type)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Core question types initialized successfully',
            'count': len(question_types_data)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error initializing question types: {str(e)}")
        return jsonify({'error': 'Failed to initialize question types'}), 500


# ============================================================================
# Legacy Inventory Endpoints (for backward compatibility)
# ============================================================================

@survey_templates_bp.route('/surveys/<int:survey_id>/versions', methods=['GET'])
def get_survey_versions(survey_id):
    """Legacy endpoint for backward compatibility."""
    return jsonify([]), 200


@survey_templates_bp.route('/surveys/<int:survey_id>/versions', methods=['POST'])
def add_survey_version(survey_id):
    """Legacy endpoint for backward compatibility."""
    return jsonify({'error': 'API deprecated, use template API instead'}), 400


@survey_templates_bp.route('/versions/<int:version_id>', methods=['DELETE'])
def delete_survey_version(version_id):
    """Legacy endpoint for backward compatibility."""
    return jsonify({'error': 'API deprecated, use template API instead'}), 400


@survey_templates_bp.route('/versions/<int:version_id>/questions', methods=['GET'])
def get_version_questions(version_id):
    """Legacy endpoint for backward compatibility."""
    return jsonify([]), 200


@survey_templates_bp.route('/versions/<int:version_id>/questions', methods=['POST'])
def add_version_question(version_id):
    """Legacy endpoint for backward compatibility."""
    return jsonify({'error': 'API deprecated, use template API instead'}), 400


@survey_templates_bp.route('/questions/<int:question_id>', methods=['PUT'])
def update_question(question_id):
    """Legacy endpoint for backward compatibility."""
    return jsonify({'error': 'API deprecated, use template API instead'}), 400


@survey_templates_bp.route('/questions/<int:question_id>', methods=['DELETE'])
def delete_question(question_id):
    """Legacy endpoint for backward compatibility."""
    return jsonify({'error': 'API deprecated, use template API instead'}), 400
