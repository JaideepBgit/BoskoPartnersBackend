"""
Signup & Onboarding routes (issue #49).

Endpoints:
  POST /api/auth/check-email         — check if email already registered
  POST /api/auth/signup              — create new personal account
  GET  /api/user-profiles/<user_id>  — get profile (resume support)
  POST /api/user-profiles/save       — upsert profile step data
  POST /api/user-profiles/affiliations — replace org affiliations
  POST /api/user-profiles/complete   — mark onboarding done
"""
import logging
from datetime import datetime
from uuid import uuid4

from flask import Blueprint, request, jsonify

from ..config.database import db
from ..models.user import User, UserProfile, UserOrgAffiliation
from ..models.geo_location import GeoLocation

logger = logging.getLogger(__name__)

onboarding_bp = Blueprint('onboarding', __name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_or_create_profile(user_id):
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.session.add(profile)
    return profile


# ── check-email ───────────────────────────────────────────────────────────────

@onboarding_bp.route('/auth/check-email', methods=['POST'])
def check_email():
    """Return whether an email already has an account."""
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({"error": "Email is required"}), 400
    exists = User.query.filter(db.func.lower(User.email) == email).first() is not None
    return jsonify({"exists": exists}), 200


# ── signup ────────────────────────────────────────────────────────────────────

@onboarding_bp.route('/auth/signup', methods=['POST'])
def signup():
    """
    Create a new personal (respondent) account.
    Expects JSON { "email": "<email>", "password": "<password>" }
    """
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    if User.query.filter(db.func.lower(User.email) == email).first():
        return jsonify({"error": "An account with this email already exists"}), 409

    # Derive a unique username from the email local part
    base_username = email.split('@')[0][:48]
    username = base_username
    suffix = 1
    while User.query.filter_by(username=username).first():
        username = f"{base_username}{suffix}"
        suffix += 1

    survey_code = str(uuid4())

    try:
        from ..models.user import Role
        user_roles_table = db.Table('user_roles', db.metadata, autoload_with=db.engine)

        new_user = User(
            username=username,
            email=email,
            password=password,   # NOTE: hash before storing in production
            survey_code=survey_code,
        )
        db.session.add(new_user)
        db.session.flush()

        role_obj = Role.query.filter_by(name='user').first()
        if role_obj:
            db.session.execute(
                user_roles_table.insert().values(
                    user_id=new_user.id,
                    role_id=role_obj.id,
                    organization_id=None,
                )
            )

        db.session.commit()

        return jsonify({
            "message": "Account created successfully",
            "id": new_user.id,
            "username": new_user.username,
            "email": new_user.email,
            "role": "user",
            "survey_code": survey_code,
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Signup error: {e}")
        return jsonify({"error": str(e)}), 500


# ── get profile ───────────────────────────────────────────────────────────────

@onboarding_bp.route('/user-profiles/<int:user_id>', methods=['GET'])
def get_user_profile(user_id):
    """Get existing onboarding profile (for resume support)."""
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        return jsonify({}), 200

    geo = None
    if profile.geo_location_id:
        geo = GeoLocation.query.get(profile.geo_location_id)

    return jsonify({
        "id": profile.id,
        "user_id": profile.user_id,
        "date_of_birth": profile.date_of_birth.isoformat() if profile.date_of_birth else None,
        "gender": profile.gender,
        "marital_status": profile.marital_status,
        "education_level": profile.education_level,
        "employment_status": profile.employment_status,
        "country": geo.country if geo else None,
        "state_province": geo.province if geo else None,
        "city": geo.city if geo else None,
        "institutional_role": profile.institutional_role,
        "institutional_status": profile.institutional_status,
        "grade_level": profile.grade_level,
        "program_enrolled": profile.program_enrolled,
        "department": profile.department,
        "graduation_year": profile.graduation_year,
        "church_member_status": profile.church_member_status,
        "church_role": profile.church_role,
        "years_affiliated": profile.years_affiliated,
        "baptized": profile.baptized,
        "small_group_participation": profile.small_group_participation,
        "share_survey_responses": profile.share_survey_responses,
        "share_profile_data": profile.share_profile_data,
        "comm_pref_email": profile.comm_pref_email,
        "comm_pref_sms": profile.comm_pref_sms,
        "comm_pref_announcements": profile.comm_pref_announcements,
        "onboarding_step": profile.onboarding_step,
        "onboarding_complete": profile.onboarding_complete,
    }), 200


# ── save step data ────────────────────────────────────────────────────────────

@onboarding_bp.route('/user-profiles/save', methods=['POST'])
def save_user_profile():
    """Upsert profile fields for the current onboarding step."""
    data = request.get_json() or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    try:
        profile = _get_or_create_profile(user_id)

        # Advance step counter
        incoming_step = data.get('onboarding_step')
        if incoming_step and (profile.onboarding_step is None or incoming_step > profile.onboarding_step):
            profile.onboarding_step = incoming_step

        # Step 1 — date of birth
        if 'date_of_birth' in data:
            dob_str = data['date_of_birth']
            if dob_str:
                try:
                    profile.date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            else:
                profile.date_of_birth = None

        # Step 1 — demographics
        for field in ('gender', 'marital_status', 'education_level', 'employment_status'):
            if field in data:
                setattr(profile, field, data[field])

        # Step 1 — location
        location_fields = ('country', 'state_province', 'city')
        if any(f in data for f in location_fields):
            geo = None
            if profile.geo_location_id:
                geo = GeoLocation.query.get(profile.geo_location_id)
            if not geo:
                geo = GeoLocation(which='user', user_id=user_id)
                db.session.add(geo)
                db.session.flush()

            if 'country' in data:
                geo.country = data['country']
            if 'state_province' in data:
                geo.province = data['state_province']
            if 'city' in data:
                geo.city = data['city']

            profile.geo_location_id = geo.id

            user = User.query.get(user_id)
            if user:
                user.geo_location_id = geo.id

        # Step 3 — institutional role
        for field in ('institutional_role', 'institutional_status',
                      'grade_level', 'program_enrolled', 'department', 'graduation_year'):
            if field in data:
                setattr(profile, field, data[field])

        # Step 4 — church/faith
        for field in ('church_member_status', 'church_role',
                      'years_affiliated', 'baptized', 'small_group_participation'):
            if field in data:
                setattr(profile, field, data[field])

        # Step 5 — data sharing
        for field in ('share_survey_responses', 'share_profile_data',
                      'comm_pref_email', 'comm_pref_sms', 'comm_pref_announcements'):
            if field in data:
                setattr(profile, field, int(bool(data[field])))

        db.session.commit()
        return jsonify({"message": "Profile saved", "onboarding_step": profile.onboarding_step}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"save_user_profile error: {e}")
        return jsonify({"error": str(e)}), 500


# ── org affiliations ──────────────────────────────────────────────────────────

@onboarding_bp.route('/user-profiles/affiliations', methods=['POST'])
def save_user_affiliations():
    """
    Replace all org affiliations for a user.
    Expects { "user_id": <int>, "affiliations": [{ "organization_id": <int>, "affiliation_type": "<str>" }] }
    """
    data = request.get_json() or {}
    user_id = data.get('user_id')
    affiliations = data.get('affiliations', [])

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    try:
        UserOrgAffiliation.query.filter_by(user_id=user_id).delete()

        for aff in affiliations:
            org_id = aff.get('organization_id')
            aff_type = aff.get('affiliation_type')
            if org_id and aff_type:
                db.session.add(UserOrgAffiliation(
                    user_id=user_id,
                    organization_id=org_id,
                    affiliation_type=aff_type,
                ))

        db.session.commit()
        return jsonify({"message": "Affiliations saved"}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"save_user_affiliations error: {e}")
        return jsonify({"error": str(e)}), 500


# ── complete onboarding ───────────────────────────────────────────────────────

@onboarding_bp.route('/user-profiles/complete', methods=['POST'])
def complete_onboarding():
    """Mark onboarding as complete for a user."""
    data = request.get_json() or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    try:
        profile = _get_or_create_profile(user_id)
        profile.onboarding_complete = 1
        profile.onboarding_step = 5
        db.session.commit()
        return jsonify({"message": "Onboarding complete"}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"complete_onboarding error: {e}")
        return jsonify({"error": str(e)}), 500
