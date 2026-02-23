"""
Question-related database models.
"""
from sqlalchemy.dialects.mysql import JSON
from ..config.database import db


class QuestionType(db.Model):
    """Question type definitions (multiple choice, rating, etc.)."""
    __tablename__ = 'question_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    display_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=True)
    config_schema = db.Column(JSON, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    
    def __repr__(self):
        return f'<QuestionType {self.name}>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'display_name': self.display_name,
            'description': self.description,
            'category': self.category,
            'config_schema': self.config_schema,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Question(db.Model):
    """Survey questions."""
    __tablename__ = 'questions'
    
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('survey_templates.id'), nullable=False)
    type_id = db.Column(db.Integer, db.ForeignKey('question_types.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_required = db.Column(db.Boolean, default=False)
    config = db.Column(JSON, nullable=True)  # For type-specific configuration
    section = db.Column(db.String(100), nullable=True)  # Section name for grouping
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    
    # Relationships
    template = db.relationship('SurveyTemplate', backref=db.backref('question_list', lazy=True))
    type = db.relationship('QuestionType')
    
    def __repr__(self):
        return f'<Question {self.id}: {self.question_text[:50]}>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'template_id': self.template_id,
            'type_id': self.type_id,
            'question_text': self.question_text,
            'sort_order': self.sort_order,
            'is_required': self.is_required,
            'config': self.config,
            'section': self.section,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class QuestionOption(db.Model):
    """Options for multiple choice questions."""
    __tablename__ = 'question_options'
    
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    option_text = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False)
    
    # Relationship
    question = db.relationship('Question', backref=db.backref('options', lazy=True))
    
    def __repr__(self):
        return f'<QuestionOption {self.id}: {self.option_text}>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'question_id': self.question_id,
            'option_text': self.option_text,
            'sort_order': self.sort_order
        }
