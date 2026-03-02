"""
User-related database models.
"""
from sqlalchemy import UniqueConstraint
from ..config.database import db


class Title(db.Model):
    """Title definitions (e.g., Pastor, President, Coach)."""
    __tablename__ = 'titles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    
    def __repr__(self):
        return f'<Title {self.name}>'


# Association table for User-Role (Many-to-Many)
user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True)
)

# Association table for User-Title (Many-to-Many, global titles)
user_titles_association = db.Table('user_titles_association',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('title_id', db.Integer, db.ForeignKey('titles.id'), primary_key=True)
)


class User(db.Model):
    """User entity for all platform users."""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=True)
    # Role is now strictly for permissions/access level
    role = db.Column(db.Enum('admin', 'user', 'manager', 'other', 'primary_contact', 'secondary_contact', 'head', 'root'), 
                     nullable=True, default='user')
    firstname = db.Column(db.String(100), nullable=True)
    lastname = db.Column(db.String(100), nullable=True)
    avatar_url = db.Column(db.String(500), nullable=True)
    survey_code = db.Column(db.String(100), nullable=True)
    geo_location_id = db.Column(db.Integer, db.ForeignKey('geo_locations.id'), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    # Password reset fields
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    
    # Primary Title (associated with organization_id)
    title_id = db.Column(db.Integer, db.ForeignKey('titles.id'), nullable=True)
    
    # Relationships
    organization = db.relationship('Organization', foreign_keys=[organization_id], 
                                   backref=db.backref('users', lazy=True))
    geo_location = db.relationship('GeoLocation', foreign_keys=[geo_location_id])
    title = db.relationship('Title', foreign_keys=[title_id])
    
    # Many-to-Many Relationships
    roles = db.relationship('Role', secondary=user_roles, lazy='subquery',
        backref=db.backref('users', lazy=True))
    titles = db.relationship('Title', secondary=user_titles_association, lazy='subquery',
        backref=db.backref('users_with_title', lazy=True))
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    def to_dict(self):
        """Convert user to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'roles': [r.name for r in self.roles],
            'firstname': self.firstname,
            'lastname': self.lastname,
            'avatar_url': self.avatar_url,
            'survey_code': self.survey_code,
            'geo_location_id': self.geo_location_id,
            'title': self.title.name if self.title else None,
            'titles': [t.name for t in self.titles],
            'title_id': self.title_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class UserDetails(db.Model):
    """Additional user details and form data."""
    __tablename__ = 'user_details'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    form_data = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(20), default='draft')
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    
    # Relationships
    user = db.relationship('User', backref=db.backref('user_details', lazy=True))
    organization = db.relationship('Organization', backref=db.backref('user_details', lazy=True))
    
    def __repr__(self):
        return f'<UserDetails for User {self.user_id}>'


class Role(db.Model):
    """Role definitions (deprecated/legacy usage)."""
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    
    def __repr__(self):
        return f'<Role {self.name}>'


class UserOrganizationTitle(db.Model):
    """Junction table for user-organization-title relationships."""
    __tablename__ = 'user_organization_titles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    title_id = db.Column(db.Integer, db.ForeignKey('titles.id'), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    
    # Relationships
    user = db.relationship('User', backref=db.backref('organization_titles', lazy=True))
    organization = db.relationship('Organization', backref=db.backref('user_titles', lazy=True))
    title = db.relationship('Title', backref=db.backref('user_organization_assignments', lazy=True))
    
    # Unique constraint
    __table_args__ = (UniqueConstraint('user_id', 'organization_id'),)

    def __repr__(self):
        return f'<UserOrganizationTitle User {self.user_id} - Org {self.organization_id} - Title {self.title_id}>'


class UserProfile(db.Model):
    """Onboarding profile data for respondent users (issue #49)."""
    __tablename__ = 'user_profiles'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'),
                        nullable=False, unique=True)

    # Step 1 — Basic Info
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(50), nullable=True)
    marital_status = db.Column(db.String(50), nullable=True)
    education_level = db.Column(db.String(100), nullable=True)
    employment_status = db.Column(db.String(100), nullable=True)
    geo_location_id = db.Column(db.Integer,
                                db.ForeignKey('geo_locations.id', ondelete='SET NULL', onupdate='CASCADE'),
                                nullable=True)

    # Step 3 — Institutional Role (conditional)
    institutional_role = db.Column(db.String(50), nullable=True)
    institutional_status = db.Column(db.String(20), nullable=True)
    grade_level = db.Column(db.String(50), nullable=True)
    program_enrolled = db.Column(db.String(100), nullable=True)
    department = db.Column(db.String(100), nullable=True)
    graduation_year = db.Column(db.String(4), nullable=True)

    # Step 4 — Church/Faith Profile (conditional)
    church_member_status = db.Column(db.String(50), nullable=True)
    church_role = db.Column(db.String(50), nullable=True)
    years_affiliated = db.Column(db.String(50), nullable=True)
    baptized = db.Column(db.String(20), nullable=True)
    small_group_participation = db.Column(db.SmallInteger, nullable=True)

    # Step 5 — Data Sharing
    share_survey_responses = db.Column(db.SmallInteger, nullable=False, default=0)
    share_profile_data = db.Column(db.SmallInteger, nullable=False, default=0)
    comm_pref_email = db.Column(db.SmallInteger, nullable=False, default=1)
    comm_pref_sms = db.Column(db.SmallInteger, nullable=False, default=0)
    comm_pref_announcements = db.Column(db.SmallInteger, nullable=False, default=1)

    # Tracking
    onboarding_step = db.Column(db.Integer, nullable=False, default=1)
    onboarding_complete = db.Column(db.SmallInteger, nullable=False, default=0)

    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())

    user = db.relationship('User', backref=db.backref('profile', uselist=False, lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<UserProfile user_id={self.user_id}>'


class UserOrgAffiliation(db.Model):
    """Organizational affiliations collected during onboarding Step 2."""
    __tablename__ = 'user_org_affiliations'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    affiliation_type = db.Column(
        db.Enum('primary', 'secondary', 'association', 'denomination'), nullable=False
    )
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())

    user = db.relationship('User', backref=db.backref('org_affiliations', lazy=True))
    organization = db.relationship('Organization', backref=db.backref('user_affiliations', lazy=True))

    def __repr__(self):
        return f'<UserOrgAffiliation user_id={self.user_id} org_id={self.organization_id} type={self.affiliation_type}>'
