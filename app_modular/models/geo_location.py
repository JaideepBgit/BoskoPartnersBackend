"""
Geographic location database model.
"""
from ..config.database import db


class GeoLocation(db.Model):
    """Geographic location data for users and organizations."""
    __tablename__ = 'geo_locations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    which = db.Column(db.Enum('user', 'organization'), nullable=True)
    continent = db.Column(db.String(255), nullable=True)
    region = db.Column(db.String(255), nullable=True)
    province = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(255), nullable=True)
    town = db.Column(db.String(255), nullable=True)
    address_line1 = db.Column(db.String(255), nullable=True)
    address_line2 = db.Column(db.String(255), nullable=True)
    country = db.Column(db.String(255), nullable=True)
    postal_code = db.Column(db.String(50), nullable=True)
    latitude = db.Column(db.Numeric(10, 8), nullable=False, server_default='0')
    longitude = db.Column(db.Numeric(11, 8), nullable=False, server_default='0')
    
    def __repr__(self):
        return f'<GeoLocation {self.id} - {self.city}, {self.country}>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'organization_id': self.organization_id,
            'which': self.which,
            'continent': self.continent,
            'region': self.region,
            'province': self.province,
            'city': self.city,
            'town': self.town,
            'address_line1': self.address_line1,
            'address_line2': self.address_line2,
            'country': self.country,
            'postal_code': self.postal_code,
            'latitude': float(self.latitude) if self.latitude else 0,
            'longitude': float(self.longitude) if self.longitude else 0
        }
