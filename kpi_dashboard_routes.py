# ============================================================================
# KPI DASHBOARD ROUTES — standalone file for the monolithic app.py
# ============================================================================
# Aggregated metrics for the executive-view KPI dashboard.
# ============================================================================

from flask import jsonify, request
from sqlalchemy import func

from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


def register_kpi_dashboard_routes(app, db):
    """Register all KPI dashboard routes with the Flask app."""

    # Import models from the running app module (loaded as __main__) to avoid
    # re-importing app.py which would create a second SQLAlchemy instance.
    import sys
    app_module = sys.modules.get('__main__')
    if not app_module or not hasattr(app_module, 'SurveyV2'):
        app_module = sys.modules.get('app')
    if not app_module or not hasattr(app_module, 'SurveyV2'):
        raise RuntimeError("app module not found")

    User = app_module.User
    Organization = app_module.Organization
    OrganizationType = app_module.OrganizationType
    GeoLocation = app_module.GeoLocation
    SurveyTemplate = app_module.SurveyTemplate
    SurveyResponse = app_module.SurveyResponse
    Role = app_module.Role
    SurveyV2 = app_module.SurveyV2
    SurveyOrganization = app_module.SurveyOrganization
    SurveyResponseV2 = app_module.SurveyResponseV2

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_scoped_org_ids(role, organization_id):
        """Return a list of organization IDs the caller can see, or None for all."""
        if role in ('admin', 'root'):
            return None

        if role == 'manager':
            return [organization_id] if organization_id else []

        if role == 'association':
            if not organization_id:
                return []
            child_orgs = db.session.query(Organization).filter_by(
                parent_organization=organization_id
            ).all()
            return [o.id for o in child_orgs]

        return []

    def _build_survey_lifecycle(org_ids):
        """Survey lifecycle metrics."""
        q = db.session.query(SurveyV2)
        if org_ids is not None:
            survey_ids_sub = db.session.query(SurveyOrganization.survey_id).filter(
                SurveyOrganization.organization_id.in_(org_ids)
            ).distinct().subquery()
            q = q.filter(SurveyV2.id.in_(survey_ids_sub))

        total = q.count()
        draft = q.filter(SurveyV2.status == 'draft').count()
        open_count = q.filter(SurveyV2.status == 'open').count()
        closed = q.filter(SurveyV2.status == 'closed').count()

        # Also count V1 templates
        total += db.session.query(SurveyTemplate).count()

        # Avg days to completion from V2 responses
        avg_q = db.session.query(
            func.avg(func.datediff(SurveyResponseV2.end_date, SurveyResponseV2.start_date))
        ).filter(
            SurveyResponseV2.start_date.isnot(None),
            SurveyResponseV2.end_date.isnot(None),
            SurveyResponseV2.status.in_(['submitted', 'analyzed'])
        )
        if org_ids is not None:
            avg_q = avg_q.filter(SurveyResponseV2.organization_id.in_(org_ids))
        avg_days = avg_q.scalar()

        # Also factor V1 responses avg
        avg_v1 = db.session.query(
            func.avg(func.datediff(SurveyResponse.end_date, SurveyResponse.start_date))
        ).filter(
            SurveyResponse.start_date.isnot(None),
            SurveyResponse.end_date.isnot(None),
            SurveyResponse.status == 'completed'
        )
        if org_ids is not None:
            user_ids_sub = db.session.query(User.id).filter(
                User.organization_id.in_(org_ids)
            ).subquery()
            avg_v1 = avg_v1.filter(SurveyResponse.user_id.in_(user_ids_sub))
        avg_days_v1 = avg_v1.scalar()

        # Combine averages
        if avg_days and avg_days_v1:
            combined_avg = (float(avg_days) + float(avg_days_v1)) / 2
        elif avg_days:
            combined_avg = float(avg_days)
        elif avg_days_v1:
            combined_avg = float(avg_days_v1)
        else:
            combined_avg = 0

        return {
            'total_surveys': total,
            'surveys_draft': draft,
            'surveys_open': open_count,
            'surveys_closed': closed,
            'avg_days_to_completion': round(combined_avg, 1)
        }

    def _build_participation(org_ids):
        """Participation & invitation metrics based on unique individual users."""
        # V2 users
        v2_q = db.session.query(SurveyResponseV2.user_id).filter(SurveyResponseV2.user_id.isnot(None))
        if org_ids is not None:
            v2_q = v2_q.filter(SurveyResponseV2.organization_id.in_(org_ids))

        v2_invited = v2_q
        v2_accepted = v2_q.filter(SurveyResponseV2.start_date.isnot(None))
        v2_responded = v2_q.filter(SurveyResponseV2.status.in_(['submitted', 'analyzed']))

        # V1 users
        v1_q = db.session.query(SurveyResponse.user_id).filter(SurveyResponse.user_id.isnot(None))
        if org_ids is not None:
            user_ids_sub = db.session.query(User.id).filter(
                User.organization_id.in_(org_ids)
            ).subquery()
            v1_q = v1_q.filter(SurveyResponse.user_id.in_(user_ids_sub))

        v1_invited = v1_q
        v1_accepted = v1_q.filter(SurveyResponse.status.in_(['in_progress', 'completed']))
        v1_responded = v1_q.filter(SurveyResponse.status == 'completed')

        logger.info(f"V1 Users invited list count: {v1_invited.count()} | First elements: {[r[0] for r in v1_invited.all()][:5]}")
        logger.info(f"V2 Users invited list count: {v2_invited.count()} | First elements: {[r[0] for r in v2_invited.all()][:5]}")

        total_invited = len(set(r[0] for r in v2_invited.all() + v1_invited.all()))
        logger.info(f"Unique total_invited computed in Python: {total_invited}")
        total_accepted = len(set(r[0] for r in v2_accepted.all() + v1_accepted.all()))
        total_responded = len(set(r[0] for r in v2_responded.all() + v1_responded.all()))

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
        v2_q = db.session.query(SurveyResponseV2)
        if org_ids is not None:
            v2_q = v2_q.filter(SurveyResponseV2.organization_id.in_(org_ids))

        v2_total = v2_q.count()
        v2_submitted = v2_q.filter(
            SurveyResponseV2.status.in_(['submitted', 'analyzed'])
        ).count()
        v2_draft = v2_q.filter(SurveyResponseV2.status == 'draft').count()

        # V1 (pending/in_progress/completed)
        v1_q = db.session.query(SurveyResponse)
        if org_ids is not None:
            user_ids_sub = db.session.query(User.id).filter(
                User.organization_id.in_(org_ids)
            ).subquery()
            v1_q = v1_q.filter(SurveyResponse.user_id.in_(user_ids_sub))

        v1_total = v1_q.count()
        v1_submitted = v1_q.filter(SurveyResponse.status == 'completed').count()
        v1_draft = v1_q.filter(SurveyResponse.status.in_(['pending', 'in_progress'])).count()

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
        """Geographic distribution of users."""
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
        """Overall completion status — 3 totals: completed, in_progress, pending.
        Responses with empty answers ({}) are counted as pending regardless of status.
        """
        # Fetch all V2 responses
        v2_q = db.session.query(SurveyResponseV2)
        if org_ids is not None:
            v2_q = v2_q.filter(SurveyResponseV2.organization_id.in_(org_ids))
        v2_rows = v2_q.all()

        # Fetch all V1 responses
        v1_q = db.session.query(SurveyResponse)
        if org_ids is not None:
            user_ids_sub = db.session.query(User.id).filter(
                User.organization_id.in_(org_ids)
            ).subquery()
            v1_q = v1_q.filter(SurveyResponse.user_id.in_(user_ids_sub))
        v1_rows = v1_q.all()

        totals = {'completed': 0, 'in_progress': 0, 'pending': 0}

        def _classify(status, answers):
            if not answers or answers == {} or str(answers) == '{}':
                return 'pending'
            if status in ('submitted', 'analyzed', 'completed'):
                return 'completed'
            if status == 'in_progress':
                return 'in_progress'
            return 'pending'

        for r in v2_rows:
            totals[_classify(r.status, r.answers)] += 1
        for r in v1_rows:
            totals[_classify(r.status, r.answers)] += 1

        return totals

    def _build_org_breakdown(org_ids):
        """Per-organization breakdown. Only Church, Institution, Non-formal orgs."""
        # Only show concrete org types (exclude associations/denominations/etc.)
        allowed_types = db.session.query(OrganizationType).filter(
            OrganizationType.type.in_(['church', 'Institution', 'Non_formal_organizations'])
        ).all()
        allowed_type_ids = [t.id for t in allowed_types]

        query = db.session.query(Organization).filter(Organization.type.in_(allowed_type_ids))
        if org_ids is not None:
            query = query.filter(Organization.id.in_(org_ids))
        orgs = query.all()

        breakdown = []
        for org in orgs:
            user_count = db.session.query(User).filter_by(organization_id=org.id).count()

            # V2 responses
            v2_total = db.session.query(SurveyResponseV2).filter_by(organization_id=org.id).count()
            v2_submitted = db.session.query(SurveyResponseV2).filter(
                SurveyResponseV2.organization_id == org.id,
                SurveyResponseV2.status.in_(['submitted', 'analyzed'])
            ).count()

            # V1 responses
            user_ids = [u.id for u in db.session.query(User).filter_by(organization_id=org.id).all()]
            v1_total = 0
            v1_submitted = 0
            if user_ids:
                v1_total = db.session.query(SurveyResponse).filter(
                    SurveyResponse.user_id.in_(user_ids)
                ).count()
                v1_submitted = db.session.query(SurveyResponse).filter(
                    SurveyResponse.user_id.in_(user_ids),
                    SurveyResponse.status == 'completed'
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

    # ------------------------------------------------------------------
    # Route
    # ------------------------------------------------------------------

    @app.route('/api/kpi/dashboard', methods=['GET'])
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
            import traceback
            logger.error(traceback.format_exc())
            return jsonify({'error': str(e)}), 500
