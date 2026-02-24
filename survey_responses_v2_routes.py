# ============================================================================
# SURVEY RESPONSES V2 ROUTES — standalone file for the monolithic app.py
# ============================================================================
# Mirrors app_modular/routes/survey_responses_v2.py but uses the monolithic
# db/models so there are no cross-package import conflicts.
# ============================================================================

from flask import jsonify, request
from datetime import datetime
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def register_survey_responses_v2_routes(app, db):
    """Register all survey-responses-v2 routes with the Flask app."""

    # Import models from the running app module (loaded as __main__) to avoid
    # re-importing app.py which would create a second SQLAlchemy instance.
    import sys
    app_module = sys.modules.get('__main__')
    if not app_module or not hasattr(app_module, 'SurveyResponseV2'):
        app_module = sys.modules.get('app')
    if not app_module or not hasattr(app_module, 'SurveyResponseV2'):
        raise RuntimeError("app module not found")

    User = app_module.User
    SurveyV2 = app_module.SurveyV2
    SurveyResponseV2 = app_module.SurveyResponseV2

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.route('/api/v2/responses', methods=['GET'])
    def get_v2_responses():
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
                if r.user:
                    data['user_name'] = f"{r.user.firstname or ''} {r.user.lastname or ''}".strip() or r.user.username
                    data['user_email'] = r.user.email
                if r.organization:
                    data['organization_name'] = r.organization.name
                if r.answers and r.survey and r.survey.questions:
                    total_questions = len(r.survey.questions) if isinstance(r.survey.questions, list) else 0
                    answered = len(r.answers) if isinstance(r.answers, dict) else 0
                    data['progress'] = round((answered / total_questions) * 100) if total_questions > 0 else 0
                else:
                    data['progress'] = 100 if r.status == 'completed' else 0
                if r.status == 'completed':
                    data['submitted_at'] = r.updated_at.isoformat() if r.updated_at else None
                result.append(data)

            return jsonify(result), 200

        except Exception as e:
            logger.error(f"Error getting v2 responses: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/v2/responses/<int:response_id>', methods=['GET'])
    def get_v2_response(response_id):
        """Get a specific survey response."""
        response = SurveyResponseV2.query.get_or_404(response_id)
        return jsonify(response.to_dict()), 200

    @app.route('/api/v2/surveys/<int:survey_id>/responses', methods=['POST'])
    def add_v2_response(survey_id):
        """Create or update a survey response."""
        data = request.json
        user_id = data.get('user_id')

        survey = SurveyV2.query.get_or_404(survey_id)

        try:
            existing = SurveyResponseV2.query.filter_by(
                survey_id=survey_id,
                user_id=user_id
            ).first()

            if existing:
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

    @app.route('/api/v2/responses/<int:response_id>', methods=['PUT'])
    def update_v2_response(response_id):
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

    @app.route('/api/v2/responses/<int:response_id>/dates', methods=['PUT'])
    def update_v2_response_dates(response_id):
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

    @app.route('/api/v2/users/<int:user_id>/surveys/<int:survey_id>/response', methods=['GET'])
    def get_user_survey_v2_response(user_id, survey_id):
        """Get existing survey response for a specific user and survey."""
        response = SurveyResponseV2.query.filter_by(
            user_id=user_id,
            survey_id=survey_id
        ).first()

        if not response:
            return jsonify({"message": "No response found"}), 404

        return jsonify(response.to_dict()), 200

    @app.route('/api/v2/users/<int:user_id>/responses', methods=['GET'])
    def get_user_v2_responses(user_id):
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

    # ------------------------------------------------------------------
    # Self-join via shareable link / QR code
    # ------------------------------------------------------------------

    @app.route('/api/v2/surveys/<int:survey_id>/join', methods=['POST'])
    def join_v2_survey(survey_id):
        """Self-assign a user to a survey via shareable link / QR code.

        Idempotent: returns the existing response if the user already has one.
        """
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

    # ------------------------------------------------------------------
    # Bulk invite
    # ------------------------------------------------------------------

    def _send_v2_invite_email(to_email, firstname, survey_name, assigned_by):
        """Send a survey-v2 invitation email via SES SMTP."""
        try:
            smtp_username = os.getenv('SES_SMTP_USERNAME')
            smtp_password = os.getenv('SES_SMTP_PASSWORD')
            smtp_host = os.getenv('SES_SMTP_HOST', 'email-smtp.us-east-1.amazonaws.com')
            smtp_port = int(os.getenv('SES_SMTP_PORT', '587'))
            source_email = os.getenv('SES_VERIFIED_EMAIL', 'noreply@saurara.org')

            if not smtp_username or not smtp_password:
                return {'success': False, 'error': 'SMTP credentials not configured'}

            greeting = f"Dear {firstname}" if firstname else "Dear Participant"
            assigned_text = f" by {assigned_by}" if assigned_by else ""
            survey_title = survey_name or "Survey"

            subject = f"You're invited to participate: {survey_title}"

            body_text = (
                f"{greeting},\n\n"
                f"You have been invited{assigned_text} to participate in \"{survey_title}\" "
                f"on the Saurara Platform.\n\n"
                f"Please log in to your account at www.saurara.org to access the survey.\n\n"
                f"Thank you for your participation!\n\n"
                f"Best regards,\nThe Saurara Research Team"
            )

            body_html = f"""
            <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333;">
              <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #633394 0%, #967CB2 100%); color: white; padding: 30px 20px; text-align: center; border-radius: 10px 10px 0 0;">
                  <h1 style="margin: 0; font-size: 24px;">Survey Invitation</h1>
                  <p style="margin: 10px 0 0 0; font-size: 14px; opacity: 0.9;">Saurara Research Platform</p>
                </div>
                <div style="background: #ffffff; padding: 30px; border: 1px solid #e0e0e0;">
                  <p style="font-size: 18px;">{greeting},</p>
                  <p>You have been invited{assigned_text} to participate in an important research survey on the Saurara Platform.</p>
                  <div style="background: #f3eef8; padding: 15px; border-left: 4px solid #633394; margin: 20px 0;">
                    <p style="margin: 0;"><strong>Survey:</strong> {survey_title}</p>
                  </div>
                  <p>Please log in to your account to access the survey:</p>
                  <p style="text-align: center;">
                    <a href="https://www.saurara.org" style="display: inline-block; background: #633394; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">Access Survey</a>
                  </p>
                  <p style="color: #757575; font-size: 14px;">If you have questions, contact us at info@saurara.org.</p>
                </div>
                <div style="background: #f8f9fa; padding: 15px; border-radius: 0 0 10px 10px; text-align: center; font-size: 12px; color: #999;">
                  Saurara Research Platform &bull; www.saurara.org
                </div>
              </div>
            </body>
            </html>"""

            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = source_email
            msg['To'] = to_email
            msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
            msg.attach(MIMEText(body_html, 'html', 'utf-8'))

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.sendmail(source_email, [to_email], msg.as_string())

            return {'success': True}
        except Exception as e:
            logger.error(f"Error sending v2 invite email to {to_email}: {str(e)}")
            return {'success': False, 'error': str(e)}

    @app.route('/api/v2/surveys/<int:survey_id>/invite', methods=['POST'])
    def invite_users_to_v2_survey(survey_id):
        """Bulk-invite users to a survey-v2.

        Expects JSON: { user_ids: [int], admin_id: int (optional) }
        Creates SurveyResponseV2 records with status='pending' and sends
        invitation emails.
        """
        data = request.json or {}
        user_ids = data.get('user_ids', [])
        admin_id = data.get('admin_id')

        if not user_ids:
            return jsonify({'error': 'user_ids is required'}), 400

        survey = SurveyV2.query.get(survey_id)
        if not survey:
            return jsonify({'error': 'Survey not found'}), 404

        # Resolve admin name for the email
        admin_name = None
        if admin_id:
            admin_user = User.query.get(admin_id)
            if admin_user:
                admin_name = f"{admin_user.firstname or ''} {admin_user.lastname or ''}".strip() or admin_user.username

        results = {
            'total': len(user_ids),
            'invited': 0,
            'skipped': 0,
            'email_sent': 0,
            'email_failed': 0,
            'details': [],
        }

        for uid in user_ids:
            detail = {'user_id': uid, 'invited': False, 'email_sent': False, 'error': None}

            user = User.query.get(uid)
            if not user:
                detail['error'] = 'User not found'
                results['skipped'] += 1
                results['details'].append(detail)
                continue

            # Check for existing invitation
            existing = SurveyResponseV2.query.filter_by(
                survey_id=survey_id,
                user_id=uid,
            ).first()
            if existing:
                detail['error'] = 'Already invited'
                results['skipped'] += 1
                results['details'].append(detail)
                continue

            try:
                response = SurveyResponseV2(
                    survey_id=survey_id,
                    user_id=uid,
                    organization_id=user.organization_id,
                    answers={},
                    status='pending',
                    start_date=datetime.utcnow(),
                )
                db.session.add(response)
                db.session.flush()
                detail['invited'] = True
                results['invited'] += 1
            except Exception as e:
                db.session.rollback()
                detail['error'] = str(e)
                results['skipped'] += 1
                results['details'].append(detail)
                continue

            # Send email
            email_result = _send_v2_invite_email(
                to_email=user.email,
                firstname=user.firstname,
                survey_name=survey.name,
                assigned_by=admin_name,
            )
            if email_result.get('success'):
                detail['email_sent'] = True
                results['email_sent'] += 1
            else:
                detail['email_error'] = email_result.get('error')
                results['email_failed'] += 1

            results['details'].append(detail)

        # Commit all new invitations
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error committing v2 invitations: {str(e)}")
            return jsonify({'error': f'Failed to save invitations: {str(e)}'}), 500

        return jsonify({
            'message': f"Invited {results['invited']}/{results['total']} users ({results['skipped']} skipped, {results['email_sent']} emails sent)",
            'results': results,
        }), 200

    logger.info("Survey Responses V2 routes registered successfully")
