"""
Survey-related database models.
"""
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from ..config.database import db


class SurveyTemplateVersion(db.Model):
    """Version container for survey templates."""
    __tablename__ = 'survey_template_versions'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    
    # Relationship
    organization = db.relationship('Organization', backref=db.backref('template_versions', lazy=True))
    
    def __repr__(self):
        return f'<SurveyTemplateVersion {self.name}>'


class SurveyTemplate(db.Model):
    """Survey template containing questions."""
    __tablename__ = 'survey_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, db.ForeignKey('survey_template_versions.id'), nullable=False)
    title_id = db.Column(db.Integer, db.ForeignKey('titles.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    sections = db.Column(JSON, nullable=True)  # For section structure
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    
    # Relationships
    version = db.relationship('SurveyTemplateVersion', backref=db.backref('templates', lazy=True))
    title = db.relationship('Title', backref=db.backref('survey_templates', lazy=True))
    
    def __repr__(self):
        return f'<SurveyTemplate {self.name}>'


class SurveyVersion(db.Model):
    """Survey version tracking."""
    __tablename__ = 'survey_versions'
    
    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey('survey_templates.id'), nullable=False)
    version_number = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    
    # Unique constraint
    __table_args__ = (UniqueConstraint('survey_id', 'version_number'),)
    
    # Relationship
    survey = db.relationship('SurveyTemplate', backref=db.backref('versions', lazy=True))
    
    def __repr__(self):
        return f'<SurveyVersion {self.survey_id} v{self.version_number}>'


class Survey(db.Model):
    """Survey instances."""
    __tablename__ = 'surveys'
    
    id = db.Column(db.Integer, primary_key=True)
    survey_code = db.Column(db.String(100), nullable=False, unique=True)
    questions = db.Column(JSON, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    
    def __repr__(self):
        return f'<Survey {self.survey_code}>'


class SurveyResponse(db.Model):
    """Survey response submissions."""
    __tablename__ = 'survey_responses'
    
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('survey_templates.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    answers = db.Column(JSON, nullable=True)
    status = db.Column(db.String(20), default='draft')  # draft, submitted, analyzed
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    template = db.relationship('SurveyTemplate', backref=db.backref('responses', lazy=True))
    user = db.relationship('User', backref=db.backref('survey_responses', lazy=True))
    
    def __repr__(self):
        return f'<SurveyResponse {self.id} for template {self.template_id}>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'template_id': self.template_id,
            'user_id': self.user_id,
            'answers': self.answers,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None
        }
