"""
Organization-related database models.
"""
from ..config.database import db


class OrganizationType(db.Model):
    """Organization type categorization (church, institution, non-formal)."""
    __tablename__ = 'organization_types'
    
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False, unique=True)
    
    def __repr__(self):
        return f'<OrganizationType {self.type}>'


class Organization(db.Model):
    """Organization entity representing churches, institutions, etc."""
    __tablename__ = 'organizations'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.Integer, db.ForeignKey('organization_types.id'), nullable=True)
    # Link to parent organization
    parent_organization = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    head = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    geo_location_id = db.Column(db.Integer, db.ForeignKey('geo_locations.id'), nullable=True)
    email = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    
    # Relationships
    organization_type = db.relationship('OrganizationType', foreign_keys=[type])
    geo_location = db.relationship('GeoLocation', foreign_keys=[geo_location_id])
    head_user = db.relationship('User', foreign_keys=[head], post_update=True)
    parent = db.relationship('Organization', remote_side=[id], foreign_keys=[parent_organization])
    
    def __repr__(self):
        return f'<Organization {self.name}>'
    
    def to_dict(self):
        """Convert organization to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'parent_organization': self.parent_organization,
            'head': self.head,
            'geo_location_id': self.geo_location_id,
            'email': self.email,
            'phone': self.phone,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
