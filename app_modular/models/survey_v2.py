"""
Surveys V2 models — standalone surveys with many-to-many organization attachment.
Questions are stored as JSON (same pattern as survey_templates).
These tables are independent from the existing survey_templates / survey_template_versions tables.
"""
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from ..config.database import db


class SurveyV2(db.Model):
    """A survey definition (template) — not tied to any single organization."""
    __tablename__ = 'surveys_v2'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    title_id = db.Column(db.Integer, db.ForeignKey('titles.id'), nullable=True)
    sections = db.Column(JSON, nullable=True)
    questions = db.Column(JSON, nullable=False)
    status = db.Column(db.String(20), default='draft')  # draft, open, closed
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())

    # Relationships
    title = db.relationship('Title', backref=db.backref('surveys_v2', lazy=True))
    organizations = db.relationship(
        'SurveyOrganization', backref='survey', lazy=True, cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<SurveyV2 {self.name}>'


class SurveyOrganization(db.Model):
    """Junction table: which organizations have which surveys."""
    __tablename__ = 'survey_organizations'

    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey('surveys_v2.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    __table_args__ = (
        UniqueConstraint('survey_id', 'organization_id', name='uq_survey_organization'),
    )

    organization = db.relationship('Organization', backref=db.backref('survey_links', lazy=True))

    def __repr__(self):
        return f'<SurveyOrganization survey={self.survey_id} org={self.organization_id}>'


class SurveyResponseV2(db.Model):
    """Survey response submissions linked to surveys_v2."""
    __tablename__ = 'survey_responses_v2'

    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey('surveys_v2.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    answers = db.Column(JSON, nullable=True)
    status = db.Column(db.String(20), default='draft')  # draft, submitted, analyzed
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())

    # Relationships
    survey = db.relationship('SurveyV2', backref=db.backref('responses', lazy=True))
    organization = db.relationship('Organization', backref=db.backref('survey_responses_v2', lazy=True))
    user = db.relationship('User', backref=db.backref('survey_responses_v2', lazy=True))

    def __repr__(self):
        return f'<SurveyResponseV2 {self.id} for survey {self.survey_id}>'

    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'survey_id': self.survey_id,
            'organization_id': self.organization_id,
            'user_id': self.user_id,
            'answers': self.answers,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None
        }
