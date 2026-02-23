"""
Analytics routes for dashboard statistics and reports.
"""
from flask import Blueprint, request, jsonify
import logging
from sqlalchemy import func

from ..config.database import db
from ..models.user import User
from ..models.organization import Organization, OrganizationType
from ..models.survey import SurveyResponse, SurveyTemplate

logger = logging.getLogger(__name__)

analytics_bp = Blueprint('analytics', __name__)


@analytics_bp.route('/admin/dashboard-stats', methods=['GET'])
def get_admin_dashboard_stats():
    """Get statistics for admin dashboard."""
    try:
        total_users = User.query.count()
        total_organizations = Organization.query.count()
        total_surveys = SurveyTemplate.query.count()
        total_responses = SurveyResponse.query.count()
        
        # Get responses by status
        draft_responses = SurveyResponse.query.filter_by(status='draft').count()
        submitted_responses = SurveyResponse.query.filter_by(status='submitted').count()
        
        return jsonify({
            "total_users": total_users,
            "total_organizations": total_organizations,
            "total_surveys": total_surveys,
            "total_responses": total_responses,
            "draft_responses": draft_responses,
            "submitted_responses": submitted_responses,
            "completion_rate": round(submitted_responses / total_responses * 100, 2) if total_responses > 0 else 0
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting admin stats: {str(e)}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/admin/organization-stats', methods=['GET'])
def get_organization_stats():
    """Get detailed organization statistics."""
    try:
        org_stats = []
        
        organizations = Organization.query.all()
        for org in organizations:
            user_count = User.query.filter_by(organization_id=org.id).count()
            
            # Get response stats for this organization's users
            user_ids = [u.id for u in org.users]
            responses = SurveyResponse.query.filter(SurveyResponse.user_id.in_(user_ids)).all() if user_ids else []
            
            submitted = len([r for r in responses if r.status == 'submitted'])
            draft = len([r for r in responses if r.status == 'draft'])
            
            org_stats.append({
                "id": org.id,
                "name": org.name,
                "type": org.organization_type.type if org.organization_type else None,
                "user_count": user_count,
                "submitted_responses": submitted,
                "draft_responses": draft,
                "total_responses": len(responses)
            })
        
        return jsonify(org_stats), 200
        
    except Exception as e:
        logger.error(f"Error getting organization stats: {str(e)}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/admin/survey-responses', methods=['GET'])
def get_admin_survey_responses():
    """Get all survey responses for admin reports."""
    try:
        organization_id = request.args.get('organization_id', type=int)
        template_id = request.args.get('template_id', type=int)
        
        query = SurveyResponse.query
        
        if organization_id:
            user_ids = [u.id for u in User.query.filter_by(organization_id=organization_id).all()]
            query = query.filter(SurveyResponse.user_id.in_(user_ids)) if user_ids else query.filter(False)
        
        if template_id:
            query = query.filter_by(template_id=template_id)
        
        responses = query.all()
        
        result = []
        for r in responses:
            user = r.user
            response_data = r.to_dict()
            
            if user:
                response_data['user_name'] = f"{user.firstname or ''} {user.lastname or ''}".strip() or user.username
                response_data['user_email'] = user.email
                response_data['organization_id'] = user.organization_id
                response_data['organization_name'] = user.organization.name if user.organization else None
            
            if r.template:
                response_data['template_name'] = r.template.name
            
            result.append(response_data)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error getting admin survey responses: {str(e)}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/analytics/overview', methods=['GET'])
def get_analytics_overview():
    """Get overview analytics for the report builder."""
    try:
        organization_id = request.args.get('organization_id', type=int)
        
        # Base query filters
        user_filter = User.query
        if organization_id:
            user_filter = user_filter.filter_by(organization_id=organization_id)
        
        user_ids = [u.id for u in user_filter.all()]
        
        # Get response statistics
        if user_ids:
            responses = SurveyResponse.query.filter(SurveyResponse.user_id.in_(user_ids))
        else:
            responses = SurveyResponse.query
        
        total_responses = responses.count()
        submitted = responses.filter_by(status='submitted').count()
        draft = responses.filter_by(status='draft').count()
        
        return jsonify({
            "total_responses": total_responses,
            "submitted_responses": submitted,
            "draft_responses": draft,
            "completion_rate": round(submitted / total_responses * 100, 2) if total_responses > 0 else 0,
            "total_users": len(user_ids)
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting analytics overview: {str(e)}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/survey-questions', methods=['GET'])
def get_survey_questions():
    """Get survey questions structure for analytics."""
    try:
        template_id = request.args.get('template_id', type=int)
        
        if not template_id:
            return jsonify({"error": "template_id is required"}), 400
        
        template = SurveyTemplate.query.get_or_404(template_id)
        
        questions = []
        for q in sorted(template.question_list, key=lambda x: x.sort_order):
            questions.append({
                "id": q.id,
                "question_text": q.question_text,
                "type_id": q.type_id,
                "type_name": q.type.name if q.type else None,
                "section": q.section,
                "options": [opt.option_text for opt in sorted(q.options, key=lambda x: x.sort_order)]
            })
        
        return jsonify({
            "template_id": template.id,
            "template_name": template.name,
            "questions": questions
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting survey questions: {str(e)}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/users-with-pending-surveys', methods=['GET'])
def get_users_with_pending_surveys():
    """Get all users who have not completed their surveys yet."""
    try:
        organization_id = request.args.get('organization_id', type=int)
        
        query = User.query.filter(User.survey_code.isnot(None))
        
        if organization_id:
            query = query.filter_by(organization_id=organization_id)
        
        users = query.all()
        
        pending_users = []
        for user in users:
            # Check if user has any submitted response
            submitted = SurveyResponse.query.filter_by(
                user_id=user.id,
                status='submitted'
            ).first()
            
            if not submitted:
                pending_users.append({
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "firstname": user.firstname,
                    "lastname": user.lastname,
                    "survey_code": user.survey_code,
                    "organization_name": user.organization.name if user.organization else None
                })
        
        return jsonify(pending_users), 200
        
    except Exception as e:
        logger.error(f"Error getting users with pending surveys: {str(e)}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/generate-report', methods=['POST'])
def generate_report_data():
    """Generate report data based on configuration."""
    data = request.json
    template_id = data.get('template_id')
    organization_id = data.get('organization_id')
    question_ids = data.get('question_ids', [])
    include_text_analysis = data.get('include_text_analysis', False)
    
    try:
        # Get responses
        query = SurveyResponse.query.filter_by(status='submitted')
        
        if template_id:
            query = query.filter_by(template_id=template_id)
        
        if organization_id:
            user_ids = [u.id for u in User.query.filter_by(organization_id=organization_id).all()]
            query = query.filter(SurveyResponse.user_id.in_(user_ids)) if user_ids else query.filter(False)
        
        responses = query.all()
        
        # Process answers
        answer_summary = {}
        
        for response in responses:
            if response.answers:
                for key, value in response.answers.items():
                    if key not in answer_summary:
                        answer_summary[key] = {
                            "count": 0,
                            "values": []
                        }
                    answer_summary[key]["count"] += 1
                    answer_summary[key]["values"].append(value)
        
        return jsonify({
            "response_count": len(responses),
            "answer_summary": answer_summary
        }), 200
        
    except Exception as e:
        logger.error(f"Error generating report data: {str(e)}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/export-report', methods=['POST'])
def export_report():
    """Export report data in various formats."""
    from flask import make_response
    import csv
    import io
    
    data = request.json
    format_type = data.get('format', 'csv')
    template_id = data.get('template_id')
    
    try:
        query = SurveyResponse.query.filter_by(status='submitted')
        if template_id:
            query = query.filter_by(template_id=template_id)
        
        responses = query.all()
        
        if format_type == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Header row
            writer.writerow(['Response ID', 'User', 'Template', 'Status', 'Created At', 'Answers'])
            
            for r in responses:
                writer.writerow([
                    r.id,
                    r.user.username if r.user else 'N/A',
                    r.template.name if r.template else 'N/A',
                    r.status,
                    r.created_at.isoformat() if r.created_at else '',
                    str(r.answers)
                ])
            
            response = make_response(output.getvalue())
            response.headers['Content-Disposition'] = 'attachment; filename=report.csv'
            response.headers['Content-Type'] = 'text/csv'
            return response
        
        else:
            # JSON format
            return jsonify([r.to_dict() for r in responses]), 200
        
    except Exception as e:
        logger.error(f"Error exporting report: {str(e)}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/survey-questions-with-types', methods=['GET'])
def get_survey_questions_with_types():
    """Get survey questions with their question types for Custom Chart Builder."""
    from ..models.question import Question, QuestionType
    
    try:
        template_id = request.args.get('template_id', type=int)
        
        if not template_id:
            # Get all templates with their questions
            templates = SurveyTemplate.query.all()
            result = []
            
            for t in templates:
                template_data = {
                    "id": t.id,
                    "name": t.name,
                    "questions": []
                }
                
                for q in sorted(t.question_list, key=lambda x: x.sort_order):
                    question_data = {
                        "id": q.id,
                        "question_text": q.question_text,
                        "type_id": q.type_id,
                        "type_name": q.type.name if q.type else None,
                        "type_display_name": q.type.display_name if q.type else None,
                        "is_numeric": q.type.name in ['number', 'rating', 'slider', 'ranking', 'constant_sum'] if q.type else False,
                        "section": q.section,
                        "options": [opt.option_text for opt in sorted(q.options, key=lambda x: x.sort_order)]
                    }
                    template_data["questions"].append(question_data)
                
                result.append(template_data)
            
            return jsonify(result), 200
        
        # Get specific template
        template = SurveyTemplate.query.get_or_404(template_id)
        
        questions = []
        for q in sorted(template.question_list, key=lambda x: x.sort_order):
            questions.append({
                "id": q.id,
                "question_text": q.question_text,
                "type_id": q.type_id,
                "type_name": q.type.name if q.type else None,
                "type_display_name": q.type.display_name if q.type else None,
                "is_numeric": q.type.name in ['number', 'rating', 'slider', 'ranking', 'constant_sum'] if q.type else False,
                "section": q.section,
                "options": [opt.option_text for opt in sorted(q.options, key=lambda x: x.sort_order)]
            })
        
        return jsonify({
            "template_id": template.id,
            "template_name": template.name,
            "questions": questions
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting survey questions with types: {str(e)}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/admin/survey-responses-with-geo', methods=['GET'])
def get_admin_survey_responses_with_geo():
    """Get all survey responses with geographic data from geo_locations table."""
    from ..models.geo_location import GeoLocation
    
    try:
        organization_id = request.args.get('organization_id', type=int)
        template_id = request.args.get('template_id', type=int)
        
        query = SurveyResponse.query
        
        if organization_id:
            user_ids = [u.id for u in User.query.filter_by(organization_id=organization_id).all()]
            query = query.filter(SurveyResponse.user_id.in_(user_ids)) if user_ids else query.filter(False)
        
        if template_id:
            query = query.filter_by(template_id=template_id)
        
        responses = query.all()
        
        result = []
        for r in responses:
            user = r.user
            response_data = r.to_dict()
            
            if user:
                response_data['user_name'] = f"{user.firstname or ''} {user.lastname or ''}".strip() or user.username
                response_data['user_email'] = user.email
                response_data['organization_name'] = user.organization.name if user.organization else None
                
                # Add geo location data
                if user.geo_location:
                    geo = user.geo_location
                    response_data['geo_location'] = {
                        "latitude": float(geo.latitude) if geo.latitude else 0,
                        "longitude": float(geo.longitude) if geo.longitude else 0,
                        "city": geo.city,
                        "country": geo.country,
                        "province": geo.province
                    }
            
            result.append(response_data)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error getting admin survey responses with geo: {str(e)}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/compare-surveys', methods=['POST'])
def compare_surveys_by_template():
    """Compare surveys based on matching questions from survey_templates."""
    data = request.json
    template_id = data.get('template_id')
    response_ids = data.get('response_ids', [])
    
    if not template_id or not response_ids:
        return jsonify({"error": "template_id and response_ids are required"}), 400
    
    try:
        template = SurveyTemplate.query.get_or_404(template_id)
        responses = SurveyResponse.query.filter(SurveyResponse.id.in_(response_ids)).all()
        
        comparison = {
            "template": {
                "id": template.id,
                "name": template.name
            },
            "response_count": len(responses),
            "question_comparisons": []
        }
        
        for question in sorted(template.question_list, key=lambda x: x.sort_order):
            q_comparison = {
                "question_id": question.id,
                "question_text": question.question_text,
                "type": question.type.name if question.type else None,
                "answers": []
            }
            
            for response in responses:
                answer = response.answers.get(str(question.id)) if response.answers else None
                q_comparison["answers"].append({
                    "response_id": response.id,
                    "user_id": response.user_id,
                    "answer": answer
                })
            
            comparison["question_comparisons"].append(q_comparison)
        
        return jsonify(comparison), 200
        
    except Exception as e:
        logger.error(f"Error comparing surveys: {str(e)}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/similar-survey-comparison', methods=['GET'])
def get_similar_survey_comparison():
    """Get comparison data for similar surveys."""
    template_id = request.args.get('template_id', type=int)
    response_id = request.args.get('response_id', type=int)
    
    if not template_id:
        return jsonify({"error": "template_id is required"}), 400
    
    try:
        template = SurveyTemplate.query.get_or_404(template_id)
        
        # Get all submitted responses for this template
        responses = SurveyResponse.query.filter_by(
            template_id=template_id,
            status='submitted'
        ).all()
        
        if response_id:
            current_response = SurveyResponse.query.get(response_id)
        else:
            current_response = None
        
        comparison_data = {
            "template_name": template.name,
            "response_count": len(responses),
            "current_response_id": response_id,
            "aggregate": {}
        }
        
        # Aggregate answers
        for response in responses:
            if response.answers:
                for key, value in response.answers.items():
                    if key not in comparison_data["aggregate"]:
                        comparison_data["aggregate"][key] = {
                            "values": [],
                            "count": 0
                        }
                    comparison_data["aggregate"][key]["values"].append(value)
                    comparison_data["aggregate"][key]["count"] += 1
        
        return jsonify(comparison_data), 200
        
    except Exception as e:
        logger.error(f"Error getting similar survey comparison: {str(e)}")
        return jsonify({"error": str(e)}), 500


# Stub endpoints for backward compatibility

@analytics_bp.route('/denominations', methods=['GET'])
def get_denominations():
    """Stub endpoint for denominations (backward compatibility)."""
    return jsonify([]), 200


@analytics_bp.route('/accreditation-bodies', methods=['GET'])
def get_accreditation_bodies():
    """Stub endpoint for accreditation bodies (backward compatibility)."""
    return jsonify([]), 200


@analytics_bp.route('/umbrella-associations', methods=['GET'])
def get_umbrella_associations():
    """Stub endpoint for umbrella associations (backward compatibility)."""
    return jsonify([]), 200


@analytics_bp.route('/test-admin', methods=['GET'])
def test_admin_endpoint():
    """Test endpoint to verify admin routes are working."""
    return jsonify({"message": "Admin endpoint working", "status": "ok"}), 200


@analytics_bp.route('/check-database-state', methods=['GET'])
def check_database_state():
    """Check the current state of templates, responses, and related data."""
    try:
        return jsonify({
            "templates": SurveyTemplate.query.count(),
            "responses": SurveyResponse.query.count(),
            "users": User.query.count(),
            "organizations": Organization.query.count(),
            "status": "ok"
        }), 200
    except Exception as e:
        logger.error(f"Error checking database state: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ============================================================================
# Textual Analytics (Qualitative) Endpoints
# ============================================================================

def create_sample_dataframe_for_analytics(survey_type, response_id, selected_surveys):
    """Create a pandas DataFrame from sample data that mimics the database structure for text analytics."""
    import json
    import os
    import pandas as pd
    
    # Define the sample data directory path
    sample_data_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'BoskoPartnersFrontend', 'public', 'sample-data')
    
    # Define text fields to analyze by survey type
    text_fields_map = {
        'church': [
            'other_training_areas',
            'why_choose_institution', 
            'expectations_met_explanation',
            'better_preparation_areas',
            'different_preparation_explanation',
            'ongoing_support_description',
            'better_ongoing_support'
        ],
        'institution': [
            'other_training_areas',
            'why_choose_institution',
            'expectations_met_explanation', 
            'better_preparation_areas',
            'different_preparation_explanation',
            'ongoing_support_description',
            'better_ongoing_support'
        ],
        'non_formal': [
            'why_choose_non_formal',
            'better_preparation_areas',
            'different_preparation_explanation',
            'ongoing_support_description',
            'better_ongoing_support'
        ]
    }
    
    # Map survey types to file names
    file_map = {
        'church': 'church-survey-responses.json',
        'institution': 'institution-survey-responses.json', 
        'non_formal': 'non-formal-survey-responses.json'
    }
    
    # Determine which files to load
    files_to_load = []
    if survey_type and survey_type in file_map:
        files_to_load = [survey_type]
    else:
        files_to_load = ['church', 'institution', 'non_formal']
    
    rows = []
    question_id_counter = 1
    
    for survey_key in files_to_load:
        file_path = os.path.join(sample_data_dir, file_map[survey_key])
        
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            text_fields = text_fields_map.get(survey_key, [])
            
            for response in data.get('responses', []):
                response_id_val = response.get('id', 0)
                
                # Extract text responses from this survey response
                for field in text_fields:
                    text_value = response.get(field, '').strip() if response.get(field) else ''
                    if text_value and len(text_value) > 5:  # Only include meaningful text
                        rows.append({
                            "response_id": response_id_val,
                            "question_id": question_id_counter,
                            "question_type": "paragraph" if len(text_value) > 100 else "short_text",
                            "answer": text_value
                        })
                        question_id_counter += 1
    
    df = pd.DataFrame(rows)
    
    # Apply filters if needed
    if selected_surveys:
        try:
            selected_ids = [int(id.strip()) for id in selected_surveys.split(',')]
            df = df[df['response_id'].isin(selected_ids)]
        except (ValueError, AttributeError):
            pass
    
    if response_id:
        try:
            target_id = int(response_id)
            df = df[df['response_id'] == target_id]
        except (ValueError, TypeError):
            pass
    
    return df


def get_sample_text_analytics(survey_type, response_id, selected_surveys):
    """Return sample text analytics using proper NLP analysis from text_analytics.py module."""
    from ..models.question import Question
    
    try:
        # Create a DataFrame from sample data
        df = create_sample_dataframe_for_analytics(survey_type, response_id, selected_surveys)
        
        if df.empty:
            return jsonify({'success': True, 'results': []}), 200
        
        # Try to use full NLP analysis
        try:
            from text_analytics import run_full_analysis
            
            # Run full NLP analysis
            analyzed_df = run_full_analysis(db.session, SurveyResponse, Question)
            
            # Filter to only the responses we have in our sample data
            response_ids = df['response_id'].unique()
            analyzed_df = analyzed_df[analyzed_df['response_id'].isin(response_ids)]
            
            # Merge the analysis results back to our original DataFrame
            df = df.merge(
                analyzed_df[['response_id', 'question_id', 'sentiment', 'topic', 'cluster']], 
                on=['response_id', 'question_id'], 
                how='left',
                suffixes=('', '_analyzed')
            )
            
            # Use analyzed values where available
            df['sentiment'] = df.get('sentiment_analyzed', df.get('sentiment', 'neutral')).fillna('neutral')
            df['topic'] = df.get('topic', 0).fillna(0).astype(int)
            df['cluster'] = df.get('cluster', 0).fillna(0).astype(int)
            
            # Add meaningful labels
            df['topic_label'] = df['topic'].apply(lambda x: f"Topic {x}" if x != -1 else "Outlier Topic")
            df['topic_description'] = df['topic'].apply(lambda x: f"Topic {x} responses" if x != -1 else "Outlier responses")
            df['cluster_label'] = df['cluster'].apply(lambda x: f"Cluster {x}")
            df['cluster_description'] = df['cluster'].apply(lambda x: f"Cluster {x} responses")
            
            # Clean up temporary columns
            df = df.drop(columns=[col for col in df.columns if col.endswith('_analyzed')], errors='ignore')
            
        except Exception as nlp_error:
            logger.warning(f"NLP analysis failed, falling back to simple analysis: {str(nlp_error)}")
            # Fallback to simple analysis if NLP fails
            df["sentiment"] = "neutral"
            df["topic"] = 0
            df["topic_label"] = "General Ministry"
            df["topic_description"] = "General ministry-related responses"
            df["cluster"] = 0
            df["cluster_label"] = "All Responses"
            df["cluster_description"] = "All responses grouped together"
        
        # Convert to the format expected by the frontend
        results = df.drop(columns=['clean_text'], errors='ignore').to_dict(orient='records')
        
        return jsonify({'success': True, 'results': results}), 200
        
    except Exception as e:
        logger.error(f"Error running sample text analytics: {str(e)}")
        return jsonify({'success': False, 'error': str(e), 'results': []}), 500


@analytics_bp.route('/reports/analytics/text', methods=['GET'])
def get_textual_analytics():
    """Return sentiment, topic and cluster labels for open-ended answers."""
    from flask import g
    from ..models.question import Question
    
    try:
        refresh = request.args.get('refresh', 'false').lower() == 'true'
        survey_type = request.args.get('survey_type')
        response_id = request.args.get('response_id')
        user_id = request.args.get('user_id')
        selected_surveys = request.args.get('selected_surveys')
        test_mode = request.args.get('test_mode', 'false').lower() == 'true'
        
        logger.info(f"Text analytics request - refresh: {refresh}, survey_type: {survey_type}, response_id: {response_id}, user_id: {user_id}, selected_surveys: {selected_surveys}, test_mode: {test_mode}")
        
        if test_mode:
            # Return sample/mock data for test mode
            logger.info("Returning sample text analytics for test mode")
            return get_sample_text_analytics(survey_type, response_id, selected_surveys)
        
        # Check if we have open-ended answers in the database before running analysis
        try:
            from text_analytics import fetch_open_ended_answers, run_full_analysis
            logger.info("Checking for open-ended answers in database...")
            open_ended_df = fetch_open_ended_answers(db.session, SurveyResponse, Question)
            logger.info(f"Found {len(open_ended_df)} open-ended answers in database")
            
            if open_ended_df.empty:
                logger.warning("No open-ended answers found in database. Returning empty results.")
                return jsonify({'success': True, 'results': [], 'message': 'No open-ended answers found in database'}), 200
            
            if refresh or not hasattr(g, 'text_analysis_df'):
                logger.info("Running full text analysis...")
                try:
                    g.text_analysis_df = run_full_analysis(db.session, SurveyResponse, Question)
                    logger.info(f"Text analysis completed successfully. Results shape: {g.text_analysis_df.shape}")
                except ValueError as ve:
                    if "No open-ended answers found in database" in str(ve):
                        logger.warning("No open-ended answers found during analysis. Returning empty results.")
                        return jsonify({'success': True, 'results': [], 'message': 'No open-ended answers found in database'}), 200
                    else:
                        raise ve

            df = g.text_analysis_df.copy()
            logger.info(f"Using cached text analysis data. Shape: {df.shape}")
            
            # Apply filters if provided
            original_count = len(df)
            if survey_type:
                # Get survey responses of the specified type
                survey_responses = SurveyResponse.query.filter(
                    SurveyResponse.status == 'completed'
                ).all()
                # Filter by survey_type if the column exists
                response_ids = [sr.id for sr in survey_responses]
                df = df[df['response_id'].isin(response_ids)]
                logger.info(f"Filtered by survey_type '{survey_type}'. Reduced from {original_count} to {len(df)} records.")
            
            if user_id:
                # Get user's survey responses
                user_responses = SurveyResponse.query.filter(
                    SurveyResponse.user_id == user_id
                ).all()
                user_response_ids = [ur.id for ur in user_responses]
                df = df[df['response_id'].isin(user_response_ids)]
                logger.info(f"Filtered by user_id '{user_id}'. Reduced from {original_count} to {len(df)} records.")
            
            if selected_surveys:
                # Filter by selected survey IDs
                selected_ids = [int(id.strip()) for id in selected_surveys.split(',') if id.strip().isdigit()]
                if selected_ids:
                    original_count = len(df)
                    df = df[df['response_id'].isin(selected_ids)]
                    logger.info(f"Filtered by selected_surveys. Reduced from {original_count} to {len(df)} records.")
            
            # Drop clean_text column and convert to records
            payload = df.drop(columns=['clean_text'], errors='ignore').to_dict(orient='records')
            logger.info(f"Returning {len(payload)} text analytics results")
            return jsonify({'success': True, 'results': payload}), 200
            
        except ImportError as ie:
            logger.warning(f"Text analytics module not available: {str(ie)}")
            return jsonify({
                'success': False, 
                'error': 'Text analytics module not available',
                'results': []
            }), 503
            
    except Exception as e:
        logger.error(f"Error generating text analytics: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to generate text analytics: {str(e)}', 'success': False}), 500


def extract_section_from_answer_key(answer_key):
    """Extract section name from answer key - this depends on your answer structure."""
    # Try to extract section from the key format
    # Common formats: "section_name.question_1", "1.2", "personal_info.name"
    if '.' in str(answer_key):
        parts = str(answer_key).split('.')
        return parts[0]
    return "General"
