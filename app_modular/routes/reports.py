"""
Report management routes.
"""
from flask import Blueprint, request, jsonify
import logging

from ..config.database import db
from ..models.report import ReportTemplate, SavedReport

logger = logging.getLogger(__name__)

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/report-templates', methods=['GET'])
def get_report_templates():
    """Get saved report templates."""
    try:
        user_id = request.args.get('user_id', type=int)
        
        query = ReportTemplate.query
        if user_id:
            query = query.filter_by(created_by=user_id)
        
        templates = query.all()
        
        return jsonify([t.to_dict() for t in templates]), 200
        
    except Exception as e:
        logger.error(f"Error getting report templates: {str(e)}")
        return jsonify({"error": str(e)}), 500


@reports_bp.route('/report-templates', methods=['POST'])
def save_report_template():
    """Save a report template."""
    data = request.json
    
    name = data.get('name')
    if not name:
        return jsonify({"error": "Name is required"}), 400
    
    try:
        template = ReportTemplate(
            name=name,
            description=data.get('description'),
            configuration=data.get('configuration'),
            created_by=data.get('user_id')
        )
        db.session.add(template)
        db.session.commit()
        
        return jsonify({
            "message": "Report template saved successfully",
            "id": template.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving report template: {str(e)}")
        return jsonify({"error": str(e)}), 500


@reports_bp.route('/report-templates/<int:template_id>', methods=['DELETE'])
def delete_report_template(template_id):
    """Delete a report template."""
    template = ReportTemplate.query.get_or_404(template_id)
    
    try:
        db.session.delete(template)
        db.session.commit()
        
        return jsonify({"message": "Report template deleted successfully"}), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting report template: {str(e)}")
        return jsonify({"error": str(e)}), 500


@reports_bp.route('/saved-reports', methods=['GET'])
def get_user_reports():
    """Get saved reports for a user."""
    try:
        user_id = request.args.get('user_id', type=int)
        
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        
        reports = SavedReport.query.filter_by(user_id=user_id).all()
        
        return jsonify([r.to_dict() for r in reports]), 200
        
    except Exception as e:
        logger.error(f"Error getting user reports: {str(e)}")
        return jsonify({"error": str(e)}), 500


@reports_bp.route('/saved-reports/<int:report_id>', methods=['GET'])
def get_report(report_id):
    """Get a specific saved report."""
    report = SavedReport.query.get_or_404(report_id)
    return jsonify(report.to_dict()), 200


@reports_bp.route('/saved-reports', methods=['POST'])
def save_report():
    """Save a report."""
    data = request.json
    
    user_id = data.get('user_id')
    name = data.get('name')
    
    if not user_id or not name:
        return jsonify({"error": "user_id and name are required"}), 400
    
    try:
        report = SavedReport(
            user_id=user_id,
            organization_id=data.get('organization_id'),
            name=name,
            content=data.get('content')
        )
        db.session.add(report)
        db.session.commit()
        
        return jsonify({
            "message": "Report saved successfully",
            "id": report.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving report: {str(e)}")
        return jsonify({"error": str(e)}), 500


@reports_bp.route('/saved-reports/<int:report_id>', methods=['PUT'])
def update_report(report_id):
    """Update a saved report."""
    data = request.json
    report = SavedReport.query.get_or_404(report_id)
    
    try:
        if 'name' in data:
            report.name = data['name']
        if 'content' in data:
            report.content = data['content']
        
        db.session.commit()
        
        return jsonify({
            "message": "Report updated successfully",
            "id": report.id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating report: {str(e)}")
        return jsonify({"error": str(e)}), 500


@reports_bp.route('/saved-reports/<int:report_id>', methods=['DELETE'])
def delete_report(report_id):
    """Delete a saved report."""
    report = SavedReport.query.get_or_404(report_id)
    
    try:
        db.session.delete(report)
        db.session.commit()
        
        return jsonify({"message": "Report deleted successfully"}), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting report: {str(e)}")
        return jsonify({"error": str(e)}), 500
