"""
Survey reminder settings and execution routes.
"""
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
import logging

from ..config.database import db
from ..models.reminder import SurveyReminderSetting, SurveyReminderLog
from ..models.survey import SurveyTemplate, SurveyResponse
from ..models.user import User
from ..services.email_service import email_service

logger = logging.getLogger(__name__)

reminders_bp = Blueprint('reminders', __name__)


def _compute_next_run(frequency, cron_expression):
    """Compute the next run time based on frequency."""
    now = datetime.utcnow()
    if frequency == 'daily':
        return now + timedelta(days=1)
    elif frequency == 'weekly':
        return now + timedelta(weeks=1)
    elif frequency == 'biweekly':
        return now + timedelta(weeks=2)
    elif frequency == 'monthly':
        return now + timedelta(days=30)
    else:
        # custom – default to weekly
        return now + timedelta(weeks=1)


# ── CRUD ──────────────────────────────────────────────────────────────────────

@reminders_bp.route('/templates/<int:template_id>/reminder-settings', methods=['GET'])
def get_reminder_settings(template_id):
    """Get reminder settings for a survey template."""
    try:
        setting = SurveyReminderSetting.query.filter_by(template_id=template_id).first()
        if not setting:
            return jsonify(None), 200
        return jsonify(setting.to_dict()), 200
    except Exception as e:
        logger.error(f"Error getting reminder settings: {e}")
        return jsonify({"error": str(e)}), 500


@reminders_bp.route('/templates/<int:template_id>/reminder-settings', methods=['POST'])
def create_reminder_settings(template_id):
    """Create or update reminder settings for a survey template."""
    data = request.json
    SurveyTemplate.query.get_or_404(template_id)

    try:
        setting = SurveyReminderSetting.query.filter_by(template_id=template_id).first()

        frequency = data.get('frequency', 'weekly')
        cron_expression = data.get('cron_expression', '0 9 * * 1')

        if setting:
            setting.frequency = frequency
            setting.cron_expression = cron_expression
            setting.target_audience = data.get('target_audience', setting.target_audience)
            setting.max_reminders = data.get('max_reminders', setting.max_reminders)
            setting.is_active = data.get('is_active', setting.is_active)
            setting.next_run_at = _compute_next_run(frequency, cron_expression)
        else:
            setting = SurveyReminderSetting(
                template_id=template_id,
                frequency=frequency,
                cron_expression=cron_expression,
                target_audience=data.get('target_audience', 'all_pending'),
                max_reminders=data.get('max_reminders', 3),
                is_active=data.get('is_active', True),
                next_run_at=_compute_next_run(frequency, cron_expression),
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


@reminders_bp.route('/templates/<int:template_id>/reminder-settings', methods=['DELETE'])
def delete_reminder_settings(template_id):
    """Delete reminder settings for a survey template."""
    try:
        setting = SurveyReminderSetting.query.filter_by(template_id=template_id).first()
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


@reminders_bp.route('/templates/<int:template_id>/reminder-logs', methods=['GET'])
def get_reminder_logs(template_id):
    """Get reminder logs for a survey template."""
    try:
        setting = SurveyReminderSetting.query.filter_by(template_id=template_id).first()
        if not setting:
            return jsonify([]), 200

        logs = SurveyReminderLog.query.filter_by(
            reminder_setting_id=setting.id
        ).order_by(SurveyReminderLog.sent_at.desc()).limit(100).all()

        return jsonify([l.to_dict() for l in logs]), 200

    except Exception as e:
        logger.error(f"Error getting reminder logs: {e}")
        return jsonify({"error": str(e)}), 500


# ── Execution ─────────────────────────────────────────────────────────────────

@reminders_bp.route('/templates/<int:template_id>/send-reminders', methods=['POST'])
def send_reminders_now(template_id):
    """Manually trigger reminders for a survey template."""
    try:
        setting = SurveyReminderSetting.query.filter_by(template_id=template_id).first()
        if not setting:
            return jsonify({"error": "No reminder settings configured for this survey"}), 404

        result = _execute_reminders(setting)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error sending reminders: {e}")
        return jsonify({"error": str(e)}), 500


@reminders_bp.route('/process-due-reminders', methods=['POST'])
def process_due_reminders():
    """Called by the scheduler – find all due reminder settings and send emails."""
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
                "template_id": setting.template_id,
                **result
            })

        return jsonify({
            "message": f"Processed {len(due_settings)} due reminder settings",
            "results": results
        }), 200

    except Exception as e:
        logger.error(f"Error processing due reminders: {e}")
        return jsonify({"error": str(e)}), 500


def _execute_reminders(setting):
    """Core logic: send reminder emails for a single SurveyReminderSetting."""
    template = SurveyTemplate.query.get(setting.template_id)
    if not template:
        return {"sent": 0, "errors": ["Template not found"]}

    # Determine which statuses to target
    target = setting.target_audience
    if target == 'not_started':
        target_statuses = ['assigned']
    elif target == 'in_progress':
        target_statuses = ['draft']
    else:  # all_pending
        target_statuses = ['assigned', 'draft']

    responses = SurveyResponse.query.filter(
        SurveyResponse.template_id == setting.template_id,
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
            user_id=user.id,
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
            result = email_service.send_reminder_email(
                to_email=user.email,
                username=user.username,
                survey_code=user.survey_code,
                firstname=user.firstname,
                organization_name=user.organization.name if hasattr(user, 'organization') and user.organization else None,
                days_remaining=days_remaining,
                password=user.password,
            )

            log_status = 'sent' if result.get('success') else 'failed'
            log = SurveyReminderLog(
                reminder_setting_id=setting.id,
                template_id=setting.template_id,
                user_id=user.id,
                respondent_email=user.email,
                status=log_status,
                error_message=result.get('error') if not result.get('success') else None,
            )
            db.session.add(log)

            if result.get('success'):
                sent.append(user.email)
            else:
                errors.append(f"Failed: {user.email} – {result.get('error')}")

        except Exception as exc:
            log = SurveyReminderLog(
                reminder_setting_id=setting.id,
                template_id=setting.template_id,
                user_id=user.id,
                respondent_email=user.email,
                status='failed',
                error_message=str(exc),
            )
            db.session.add(log)
            errors.append(f"Error: {user.email} – {str(exc)}")

    # Update setting timestamps
    setting.last_run_at = datetime.utcnow()
    setting.next_run_at = _compute_next_run(setting.frequency, setting.cron_expression)
    db.session.commit()

    return {"sent": len(sent), "errors": errors}
