"""
Email template database model.
"""
from ..config.database import db


class EmailTemplate(db.Model):
    """Email templates for welcome, reminder, and other emails."""
    __tablename__ = 'email_templates'
    
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(255), nullable=True)
    html_body = db.Column(db.Text, nullable=True)
    text_body = db.Column(db.Text, nullable=True)
    template_type = db.Column(db.Enum('welcome', 'reminder', 'survey_assignment', 'password_reset', 'custom'),
                               nullable=False, default='custom')
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    
    # Constraints and indexes
    __table_args__ = (
        db.UniqueConstraint('organization_id', 'name', name='uq_org_name'),
        db.Index('idx_email_templates_org', 'organization_id'),
    )
    
    def __repr__(self):
        return f'<EmailTemplate {self.id}: {self.name}>'
    
    def to_dict(self):
        """Convert EmailTemplate to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'name': self.name,
            'subject': self.subject,
            'html_body': self.html_body,
            'text_body': self.text_body,
            'template_type': self.template_type,
            'is_default': self.is_default,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
