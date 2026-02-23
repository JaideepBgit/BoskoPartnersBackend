"""
KPI Dashboard routes — aggregated metrics for the executive-view dashboard.
"""
from flask import Blueprint, request, jsonify
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy import func, extract, and_

from ..config.database import db
from ..models.user import User
from ..models.organization import Organization, OrganizationType
from ..models.survey import SurveyTemplate, SurveyResponse
from ..models.survey_v2 import SurveyV2, SurveyResponseV2, SurveyOrganization
from ..models.geo_location import GeoLocation

logger = logging.getLogger(__name__)

kpi_dashboard_bp = Blueprint('kpi_dashboard', __name__)


def _get_scoped_org_ids(role, organization_id):
    """Return a list of organization IDs the caller is allowed to see, or None for all."""
    if role in ('admin', 'root'):
        return None  # no filter — see everything

    if role == 'manager':
        return [organization_id] if organization_id else []

    if role == 'association':
        if not organization_id:
            return []
        # Association sees orgs whose parent_organization points to their org
        child_orgs = Organization.query.filter_by(parent_organization=organization_id).all()
        return [o.id for o in child_orgs]

    return []


def _build_survey_lifecycle(org_ids):
    """Survey lifecycle metrics from V2 surveys."""
    q = SurveyV2.query
    if org_ids is not None:
        # Filter V2 surveys attached to any of the scoped orgs
        survey_ids = db.session.query(SurveyOrganization.survey_id).filter(
            SurveyOrganization.organization_id.in_(org_ids)
        ).distinct().subquery()
        q = q.filter(SurveyV2.id.in_(survey_ids))

    total = q.count()
    draft = q.filter(SurveyV2.status == 'draft').count()
    open_count = q.filter(SurveyV2.status == 'open').count()
    closed = q.filter(SurveyV2.status == 'closed').count()

    # Also count V1 templates
    v1_q = SurveyTemplate.query
    total += v1_q.count()

    # Avg days to completion from V2 responses with both start and end dates
    resp_q = SurveyResponseV2.query.filter(
        SurveyResponseV2.start_date.isnot(None),
        SurveyResponseV2.end_date.isnot(None),
        SurveyResponseV2.status.in_(['submitted', 'analyzed'])
    )
    if org_ids is not None:
        resp_q = resp_q.filter(SurveyResponseV2.organization_id.in_(org_ids))

    avg_result = db.session.query(
        func.avg(func.datediff(SurveyResponseV2.end_date, SurveyResponseV2.start_date))
    ).filter(
        SurveyResponseV2.start_date.isnot(None),
        SurveyResponseV2.end_date.isnot(None),
        SurveyResponseV2.status.in_(['submitted', 'analyzed'])
    )
    if org_ids is not None:
        avg_result = avg_result.filter(SurveyResponseV2.organization_id.in_(org_ids))
    avg_days = avg_result.scalar()

    return {
        'total_surveys': total,
        'surveys_draft': draft,
        'surveys_open': open_count,
        'surveys_closed': closed,
        'avg_days_to_completion': round(float(avg_days), 1) if avg_days else 0
    }


def _build_participation(org_ids):
    """Participation & invitation metrics."""
    # V2 responses = invitations
    v2_q = SurveyResponseV2.query
    if org_ids is not None:
        v2_q = v2_q.filter(SurveyResponseV2.organization_id.in_(org_ids))

    total_v2 = v2_q.count()
    accepted_v2 = v2_q.filter(SurveyResponseV2.start_date.isnot(None)).count()
    responded_v2 = v2_q.filter(
        SurveyResponseV2.status.in_(['submitted', 'analyzed'])
    ).count()

    # V1 responses
    v1_q = SurveyResponse.query
    if org_ids is not None:
        user_ids_sub = db.session.query(User.id).filter(
            User.organization_id.in_(org_ids)
        ).subquery()
        v1_q = v1_q.filter(SurveyResponse.user_id.in_(user_ids_sub))

    total_v1 = v1_q.count()
    accepted_v1 = v1_q.filter(SurveyResponse.start_date.isnot(None)).count()
    responded_v1 = v1_q.filter(
        SurveyResponse.status.in_(['submitted', 'analyzed'])
    ).count()

    total_invited = total_v2 + total_v1
    total_accepted = accepted_v2 + accepted_v1
    total_responded = responded_v2 + responded_v1

    return {
        'total_invited': total_invited,
        'total_accepted': total_accepted,
        'acceptance_rate': round(total_accepted / total_invited * 100, 1) if total_invited > 0 else 0,
        'total_responded': total_responded,
        'response_rate': round(total_responded / total_invited * 100, 1) if total_invited > 0 else 0
    }


def _build_completion(org_ids):
    """Completion metrics."""
    # V2
    v2_q = SurveyResponseV2.query
    if org_ids is not None:
        v2_q = v2_q.filter(SurveyResponseV2.organization_id.in_(org_ids))

    v2_total = v2_q.count()
    v2_submitted = v2_q.filter(
        SurveyResponseV2.status.in_(['submitted', 'analyzed'])
    ).count()
    v2_draft = v2_q.filter(SurveyResponseV2.status == 'draft').count()

    # V1
    v1_q = SurveyResponse.query
    if org_ids is not None:
        user_ids_sub = db.session.query(User.id).filter(
            User.organization_id.in_(org_ids)
        ).subquery()
        v1_q = v1_q.filter(SurveyResponse.user_id.in_(user_ids_sub))

    v1_total = v1_q.count()
    v1_submitted = v1_q.filter(
        SurveyResponse.status.in_(['submitted', 'analyzed'])
    ).count()
    v1_draft = v1_q.filter(SurveyResponse.status == 'draft').count()

    total = v2_total + v1_total
    submitted = v2_submitted + v1_submitted
    draft = v2_draft + v1_draft

    return {
        'total_responses': total,
        'total_submitted': submitted,
        'total_draft': draft,
        'completion_rate': round(submitted / total * 100, 1) if total > 0 else 0,
        'partial_count': draft,
        'full_count': submitted
    }


def _build_geographic(org_ids):
    """Geographic distribution of responding users."""
    q = db.session.query(
        GeoLocation.country,
        GeoLocation.city,
        func.count(GeoLocation.id).label('cnt')
    ).filter(
        GeoLocation.which == 'user',
        GeoLocation.country.isnot(None),
        GeoLocation.country != ''
    )

    if org_ids is not None:
        q = q.filter(GeoLocation.user_id.in_(
            db.session.query(User.id).filter(User.organization_id.in_(org_ids))
        ))

    rows = q.group_by(GeoLocation.country, GeoLocation.city).all()

    countries = defaultdict(lambda: {'count': 0, 'cities': []})
    for country, city, cnt in rows:
        countries[country]['count'] += cnt
        if city and city not in countries[country]['cities']:
            countries[country]['cities'].append(city)

    return {'countries': dict(countries)}


def _build_completion_trend(org_ids):
    """Monthly completion trend for the last 12 months - shows when responses were completed vs still in draft."""
    twelve_months_ago = datetime.utcnow() - timedelta(days=365)

    # V2 completed responses (by submission date)
    v2_completed_q = db.session.query(
        func.date_format(SurveyResponseV2.updated_at, '%Y-%m').label('month'),
        func.count(SurveyResponseV2.id).label('cnt')
    ).filter(
        SurveyResponseV2.updated_at >= twelve_months_ago,
        SurveyResponseV2.status.in_(['submitted', 'analyzed'])
    )
    if org_ids is not None:
        v2_completed_q = v2_completed_q.filter(SurveyResponseV2.organization_id.in_(org_ids))
    v2_completed_rows = v2_completed_q.group_by('month').all()

    # V2 draft responses (by creation date)
    v2_draft_q = db.session.query(
        func.date_format(SurveyResponseV2.created_at, '%Y-%m').label('month'),
        func.count(SurveyResponseV2.id).label('cnt')
    ).filter(
        SurveyResponseV2.created_at >= twelve_months_ago,
        SurveyResponseV2.status == 'draft'
    )
    if org_ids is not None:
        v2_draft_q = v2_draft_q.filter(SurveyResponseV2.organization_id.in_(org_ids))
    v2_draft_rows = v2_draft_q.group_by('month').all()

    # V1 completed responses (by submission date)
    v1_completed_q = db.session.query(
        func.date_format(SurveyResponse.updated_at, '%Y-%m').label('month'),
        func.count(SurveyResponse.id).label('cnt')
    ).filter(
        SurveyResponse.updated_at >= twelve_months_ago,
        SurveyResponse.status.in_(['submitted', 'analyzed'])
    )
    if org_ids is not None:
        user_ids_sub = db.session.query(User.id).filter(
            User.organization_id.in_(org_ids)
        ).subquery()
        v1_completed_q = v1_completed_q.filter(SurveyResponse.user_id.in_(user_ids_sub))
    v1_completed_rows = v1_completed_q.group_by('month').all()

    # V1 draft responses (by creation date)
    v1_draft_q = db.session.query(
        func.date_format(SurveyResponse.created_at, '%Y-%m').label('month'),
        func.count(SurveyResponse.id).label('cnt')
    ).filter(
        SurveyResponse.created_at >= twelve_months_ago,
        SurveyResponse.status == 'draft'
    )
    if org_ids is not None:
        user_ids_sub = db.session.query(User.id).filter(
            User.organization_id.in_(org_ids)
        ).subquery()
        v1_draft_q = v1_draft_q.filter(SurveyResponse.user_id.in_(user_ids_sub))
    v1_draft_rows = v1_draft_q.group_by('month').all()

    monthly = defaultdict(lambda: {'submitted': 0, 'draft': 0})
    
    # Add completed counts
    for month, cnt in list(v2_completed_rows) + list(v1_completed_rows):
        monthly[month]['submitted'] += cnt
    
    # Add draft counts
    for month, cnt in list(v2_draft_rows) + list(v1_draft_rows):
        monthly[month]['draft'] += cnt

    trend = [
        {'month': m, 'submitted': d['submitted'], 'draft': d['draft']}
        for m, d in sorted(monthly.items())
    ]
    
    # Ensure at least 5 months of data for a complete graph
    if len(trend) < 5:
        from calendar import monthrange
        
        # Get current month and last 4 months
        now = datetime.utcnow()
        months_to_show = []
        
        for i in range(4, -1, -1):  # 4 months ago to current month
            # Calculate month offset
            target_month = now.month - i
            target_year = now.year
            
            # Handle year rollover
            while target_month <= 0:
                target_month += 12
                target_year -= 1
            
            month_str = f"{target_year}-{target_month:02d}"
            months_to_show.append(month_str)
        
        # Create a dict from existing trend data
        existing_data = {item['month']: item for item in trend}
        
        # Build complete trend with all 5 months
        trend = [
            existing_data.get(month, {'month': month, 'submitted': 0, 'draft': 0})
            for month in months_to_show
        ]
    
    completed_total = sum(d['submitted'] for d in trend)
    in_progress_total = sum(d['draft'] for d in trend)

    return {
        'trend': trend,
        'completed': completed_total,
        'in_progress': in_progress_total,
        'pending': 0,
    }


def _build_org_breakdown(org_ids):
    """Per-organization breakdown of users and completion.
    Only includes Church, Institution, and Non-formal organization types.
    """
    # Only show concrete org types (exclude associations/denominations/etc.)
    allowed_types = OrganizationType.query.filter(
        OrganizationType.type.in_(['church', 'Institution', 'Non_formal_organizations'])
    ).all()
    allowed_type_ids = [t.id for t in allowed_types]

    query = Organization.query.filter(Organization.type.in_(allowed_type_ids))
    if org_ids is not None:
        query = query.filter(Organization.id.in_(org_ids))
    orgs = query.all()

    breakdown = []
    for org in orgs:
        user_count = User.query.filter_by(organization_id=org.id).count()

        # V2 responses for this org
        v2_total = SurveyResponseV2.query.filter_by(organization_id=org.id).count()
        v2_submitted = SurveyResponseV2.query.filter(
            SurveyResponseV2.organization_id == org.id,
            SurveyResponseV2.status.in_(['submitted', 'analyzed'])
        ).count()

        # V1 responses for users in this org
        user_ids = [u.id for u in User.query.filter_by(organization_id=org.id).all()]
        v1_total = 0
        v1_submitted = 0
        if user_ids:
            v1_total = SurveyResponse.query.filter(
                SurveyResponse.user_id.in_(user_ids)
            ).count()
            v1_submitted = SurveyResponse.query.filter(
                SurveyResponse.user_id.in_(user_ids),
                SurveyResponse.status.in_(['submitted', 'analyzed'])
            ).count()

        total = v2_total + v1_total
        submitted = v2_submitted + v1_submitted

        breakdown.append({
            'name': org.name,
            'total_users': user_count,
            'total_responses': total,
            'submitted': submitted,
            'completion_rate': round(submitted / total * 100, 1) if total > 0 else 0
        })

    return breakdown


@kpi_dashboard_bp.route('/kpi/dashboard', methods=['GET'])
def get_kpi_dashboard():
    """Aggregated KPI data for the executive dashboard."""
    try:
        role = request.args.get('role', 'admin')
        organization_id = request.args.get('organization_id', type=int)

        org_ids = _get_scoped_org_ids(role, organization_id)

        return jsonify({
            'survey_lifecycle': _build_survey_lifecycle(org_ids),
            'participation': _build_participation(org_ids),
            'completion': _build_completion(org_ids),
            'geographic': _build_geographic(org_ids),
            'completion_trend': _build_completion_trend(org_ids),
            'organization_breakdown': _build_org_breakdown(org_ids),
        }), 200

    except Exception as e:
        logger.error(f"Error getting KPI dashboard data: {str(e)}")
        return jsonify({'error': str(e)}), 500
