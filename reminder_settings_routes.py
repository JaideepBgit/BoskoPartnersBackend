# ============================================================================
# REMINDER SETTINGS ROUTES — standalone file for the monolithic app.py
# ============================================================================
# Provides API endpoints for survey reminder configuration, logs, and
# manual / scheduled reminder execution.
# ============================================================================

from flask import jsonify, request
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def register_reminder_settings_routes(app, db):
    """Register all reminder-settings routes with the Flask app."""

    # Import models from the running app module (loaded as __main__) to avoid
    # re-importing app.py which would create a second SQLAlchemy instance.
    import sys
    app_module = sys.modules.get('__main__')
    if not app_module or not hasattr(app_module, 'User'):
        app_module = sys.modules.get('app')
    if not app_module or not hasattr(app_module, 'User'):
        raise RuntimeError("app module not found")

    User = app_module.User
    SurveyResponse = app_module.SurveyResponse
    Organization = app_module.Organization
    send_reminder_email = app_module.send_reminder_email

    # ------------------------------------------------------------------
    # Models – column names match the existing DB schema exactly
    # ------------------------------------------------------------------

    class SurveyReminderSetting(db.Model):
        __tablename__ = 'survey_reminder_settings'
        __table_args__ = {'extend_existing': True}

        id = db.Column(db.Integer, primary_key=True)
        survey_id = db.Column(db.Integer, nullable=False)
        frequency = db.Column(db.String(20), nullable=False, default='weekly')
        cron_expression = db.Column(db.String(50), nullable=False, default='0 9 * * 1')
        target_audience = db.Column(db.String(20), nullable=False, default='all_pending')
        max_reminders = db.Column(db.Integer, nullable=False, default=3)
        is_active = db.Column(db.Boolean, nullable=False, default=True)
        last_run_at = db.Column(db.DateTime, nullable=True)
        next_run_at = db.Column(db.DateTime, nullable=True)
        created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
        updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                               onupdate=db.func.current_timestamp())

        def to_dict(self):
            return {
                'id': self.id,
                'template_id': self.survey_id,
                'frequency': self.frequency,
                'cron_expression': self.cron_expression,
                'target_audience': self.target_audience,
                'max_reminders': self.max_reminders,
                'is_active': self.is_active,
                'last_run_at': self.last_run_at.isoformat() if self.last_run_at else None,
                'next_run_at': self.next_run_at.isoformat() if self.next_run_at else None,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            }

    class SurveyReminderLog(db.Model):
        __tablename__ = 'survey_reminder_logs'
        __table_args__ = {'extend_existing': True}

        id = db.Column(db.Integer, primary_key=True)
        reminder_setting_id = db.Column(db.Integer, nullable=False)
        survey_id = db.Column(db.Integer, nullable=False)
        invitation_id = db.Column(db.Integer, nullable=False)
        respondent_email = db.Column(db.String(255), nullable=True)
        status = db.Column(db.String(20), nullable=False, default='sent')
        sent_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
        error_message = db.Column(db.Text, nullable=True)

        def to_dict(self):
            return {
                'id': self.id,
                'reminder_setting_id': self.reminder_setting_id,
                'template_id': self.survey_id,
                'user_id': self.invitation_id,
                'respondent_email': self.respondent_email,
                'status': self.status,
                'sent_at': self.sent_at.isoformat() if self.sent_at else None,
                'error_message': self.error_message,
            }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_next_run(frequency):
        now = datetime.utcnow()
        if frequency == 'daily':
            return now + timedelta(days=1)
        elif frequency == 'weekly':
            return now + timedelta(weeks=1)
        elif frequency == 'biweekly':
            return now + timedelta(weeks=2)
        elif frequency == 'monthly':
            return now + timedelta(days=30)
        return now + timedelta(weeks=1)

    def _execute_reminders(setting):
        """Core logic: send reminder emails for a single SurveyReminderSetting."""
        # Determine which statuses to target
        target = setting.target_audience
        if target == 'not_started':
            target_statuses = ['pending']
        elif target == 'in_progress':
            target_statuses = ['in_progress']
        else:  # all_pending
            target_statuses = ['pending', 'in_progress']

        responses = SurveyResponse.query.filter(
            SurveyResponse.template_id == setting.survey_id,
            SurveyResponse.status.in_(target_statuses),
        ).all()

        sent = []
        errors = []

        for response in responses:
            user = User.query.get(response.user_id)
            if not user or not user.email:
                continue

            # Check max_reminders cap
            already_sent = SurveyReminderLog.query.filter_by(
                reminder_setting_id=setting.id,
                invitation_id=user.id,
                status='sent',
            ).count()

            if already_sent >= setting.max_reminders:
                continue

            # Calculate days remaining
            days_remaining = None
            if response.end_date:
                delta = response.end_date - datetime.utcnow()
                days_remaining = max(0, delta.days)

            try:
                org_name = None
                if user.organization_id:
                    org = Organization.query.get(user.organization_id)
                    if org:
                        org_name = org.name

                result = send_reminder_email(
                    to_email=user.email,
                    username=user.username,
                    survey_code=getattr(user, 'survey_code', None),
                    firstname=getattr(user, 'firstname', None),
                    organization_name=org_name,
                    days_remaining=days_remaining,
                    password=user.password,
                )

                log_status = 'sent' if result.get('success') else 'failed'
                log = SurveyReminderLog(
                    reminder_setting_id=setting.id,
                    survey_id=setting.survey_id,
                    invitation_id=user.id,
                    respondent_email=user.email,
                    status=log_status,
                    error_message=result.get('error') if not result.get('success') else None,
                )
                db.session.add(log)

                if result.get('success'):
                    sent.append(user.email)
                else:
                    errors.append(f"Failed: {user.email} - {result.get('error')}")

            except Exception as exc:
                log = SurveyReminderLog(
                    reminder_setting_id=setting.id,
                    survey_id=setting.survey_id,
                    invitation_id=user.id,
                    respondent_email=user.email,
                    status='failed',
                    error_message=str(exc),
                )
                db.session.add(log)
                errors.append(f"Error: {user.email} - {str(exc)}")

        # Update setting timestamps
        setting.last_run_at = datetime.utcnow()
        setting.next_run_at = _compute_next_run(setting.frequency)
        db.session.commit()

        return {"sent": len(sent), "errors": errors}

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.route('/api/templates/<int:template_id>/reminder-settings', methods=['GET'])
    def get_reminder_settings(template_id):
        """Get reminder settings for a survey template."""
        try:
            setting = SurveyReminderSetting.query.filter_by(survey_id=template_id).first()
            if not setting:
                return jsonify(None), 200
            return jsonify(setting.to_dict()), 200
        except Exception as e:
            logger.error(f"Error getting reminder settings: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/templates/<int:template_id>/reminder-settings', methods=['POST'])
    def save_reminder_settings(template_id):
        """Create or update reminder settings for a survey template."""
        data = request.json
        try:
            setting = SurveyReminderSetting.query.filter_by(survey_id=template_id).first()

            frequency = data.get('frequency', 'weekly')

            if setting:
                setting.frequency = frequency
                setting.cron_expression = data.get('cron_expression', setting.cron_expression)
                setting.target_audience = data.get('target_audience', setting.target_audience)
                setting.max_reminders = data.get('max_reminders', setting.max_reminders)
                setting.is_active = data.get('is_active', setting.is_active)
                setting.next_run_at = _compute_next_run(frequency)
            else:
                setting = SurveyReminderSetting(
                    survey_id=template_id,
                    frequency=frequency,
                    cron_expression=data.get('cron_expression', '0 9 * * 1'),
                    target_audience=data.get('target_audience', 'all_pending'),
                    max_reminders=data.get('max_reminders', 3),
                    is_active=data.get('is_active', True),
                    next_run_at=_compute_next_run(frequency),
                )
                db.session.add(setting)

            db.session.commit()

            return jsonify({
                "message": "Reminder settings saved",
                "setting": setting.to_dict()
            }), 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error saving reminder settings: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/templates/<int:template_id>/reminder-settings', methods=['DELETE'])
    def delete_reminder_settings(template_id):
        """Delete reminder settings for a survey template."""
        try:
            setting = SurveyReminderSetting.query.filter_by(survey_id=template_id).first()
            if not setting:
                return jsonify({"error": "No reminder settings found"}), 404

            SurveyReminderLog.query.filter_by(reminder_setting_id=setting.id).delete()
            db.session.delete(setting)
            db.session.commit()
            return jsonify({"message": "Reminder settings deleted"}), 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting reminder settings: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/templates/<int:template_id>/reminder-logs', methods=['GET'])
    def get_reminder_logs(template_id):
        """Get reminder logs for a survey template."""
        try:
            setting = SurveyReminderSetting.query.filter_by(survey_id=template_id).first()
            if not setting:
                return jsonify([]), 200

            logs = SurveyReminderLog.query.filter_by(
                reminder_setting_id=setting.id
            ).order_by(SurveyReminderLog.sent_at.desc()).limit(100).all()

            return jsonify([log.to_dict() for log in logs]), 200

        except Exception as e:
            logger.error(f"Error getting reminder logs: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/templates/<int:template_id>/send-reminders', methods=['POST'])
    def send_reminders_now(template_id):
        """Manually trigger reminders for a survey template."""
        try:
            setting = SurveyReminderSetting.query.filter_by(survey_id=template_id).first()
            if not setting:
                return jsonify({"error": "No reminder settings configured for this survey"}), 404

            result = _execute_reminders(setting)
            return jsonify(result), 200

        except Exception as e:
            logger.error(f"Error sending reminders: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/process-due-reminders', methods=['POST'])
    def process_due_reminders():
        """Called by the scheduler - find all due reminder settings and send emails."""
        try:
            now = datetime.utcnow()
            due_settings = SurveyReminderSetting.query.filter(
                SurveyReminderSetting.is_active == True,
                SurveyReminderSetting.next_run_at <= now,
            ).all()

            results = []
            for setting in due_settings:
                result = _execute_reminders(setting)
                results.append({
                    "template_id": setting.survey_id,
                    **result
                })

            return jsonify({
                "message": f"Processed {len(due_settings)} due reminder settings",
                "results": results
            }), 200

        except Exception as e:
            logger.error(f"Error processing due reminders: {e}")
            return jsonify({"error": str(e)}), 500

    # Create tables if they don't exist
    with app.app_context():
        try:
            SurveyReminderSetting.__table__.create(db.engine, checkfirst=True)
            SurveyReminderLog.__table__.create(db.engine, checkfirst=True)
            logger.info("Reminder settings tables verified/created")
        except Exception as e:
            logger.warning(f"Could not create reminder tables (may already exist): {e}")
