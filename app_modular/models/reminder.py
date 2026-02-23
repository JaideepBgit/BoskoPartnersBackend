"""
Survey reminder settings and logs models.
"""
from ..config.database import db


class SurveyReminderSetting(db.Model):
    """Configuration for automated survey reminders."""
    __tablename__ = 'survey_reminder_settings'

    id = db.Column(db.Integer, primary_key=True)
    # DB column is 'survey_id' (from original migration), exposed as template_id in Python
    template_id = db.Column('survey_id', db.Integer, db.ForeignKey('survey_templates.id', ondelete='CASCADE'), nullable=False)
    frequency = db.Column(db.String(20), nullable=False, default='weekly')  # daily, weekly, custom
    cron_expression = db.Column(db.String(50), nullable=False, default='0 9 * * 1')
    target_audience = db.Column(db.String(20), nullable=False, default='all_pending')  # all_pending, not_started, in_progress
    max_reminders = db.Column(db.Integer, nullable=False, default=3)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_run_at = db.Column(db.DateTime, nullable=True)
    next_run_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())

    # Relationship
    template = db.relationship('SurveyTemplate', backref=db.backref('reminder_settings', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'template_id': self.template_id,
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
    """Log of every reminder email sent."""
    __tablename__ = 'survey_reminder_logs'

    id = db.Column(db.Integer, primary_key=True)
    reminder_setting_id = db.Column(db.Integer, db.ForeignKey('survey_reminder_settings.id', ondelete='CASCADE'), nullable=False)
    # DB column is 'survey_id' (from original migration), exposed as template_id in Python
    template_id = db.Column('survey_id', db.Integer, nullable=False)
    # DB column is 'invitation_id' (from original migration), exposed as user_id in Python
    user_id = db.Column('invitation_id', db.Integer, nullable=False)
    respondent_email = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='sent')  # sent, failed, bounced
    sent_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    error_message = db.Column(db.Text, nullable=True)

    # Relationship
    reminder_setting = db.relationship('SurveyReminderSetting', backref=db.backref('logs', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'reminder_setting_id': self.reminder_setting_id,
            'template_id': self.template_id,
            'user_id': self.user_id,
            'respondent_email': self.respondent_email,
            'status': self.status,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'error_message': self.error_message,
        }
