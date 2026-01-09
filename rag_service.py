"""
RAG (Retrieval-Augmented Generation) Service for Survey Analytics
Uses Gemini 2.0 Flash Lite to answer questions about survey data with grounding
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import requests
from sqlalchemy import text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class SurveyRAGService:
    """
    RAG Service that retrieves survey data from database and generates
    grounded responses using Gemini 2.0 Flash Lite
    """
    
    def __init__(self, db_connection):
        """
        Initialize RAG service
        
        Args:
            db_connection: SQLAlchemy database connection
        """
        self.db = db_connection
        self.api_key = os.getenv('GEMINI_API_KEY', '')
        # Using Gemini 2.0 Flash Lite as requested
        self.model = 'gemini-2.0-flash-lite'
        self.api_endpoint = f'https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent'
        
        if not self.api_key:
            logger.warning("⚠️ GEMINI_API_KEY not found in environment variables")
    
    def retrieve_survey_data(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """
        Retrieve relevant survey data from database based on query
        
        Args:
            query: User's question
            limit: Maximum number of records to retrieve
            
        Returns:
            Dictionary containing survey data and metadata
        """
        try:
            # Analyze query to determine what data to retrieve
            query_lower = query.lower()
            
            # Build dynamic SQL query based on user question
            sql_query = self._build_query_from_question(query_lower, limit)
            
            # Execute query
            result = self.db.session.execute(text(sql_query))
            rows = result.fetchall()
            columns = result.keys()
            
            # Convert to list of dictionaries
            data = [dict(zip(columns, row)) for row in rows]
            
            # Get metadata about the data
            metadata = self._extract_metadata(data)
            
            return {
                'data': data,
                'metadata': metadata,
                'count': len(data),
                'query_type': self._classify_query(query_lower)
            }
            
        except Exception as e:
            logger.error(f"Error retrieving survey data: {e}")
            return {
                'data': [],
                'metadata': {},
                'count': 0,
                'error': str(e)
            }
    
    def _build_query_from_question(self, query: str, limit: int) -> str:
        """
        Build SQL query based on user's question
        
        Args:
            query: User's question (lowercase)
            limit: Maximum records to return
            
        Returns:
            SQL query string
        """
        # Base query with all important fields
        base_query = """
        SELECT 
            sr.id as response_id,
            sr.created_at as response_date,
            sr.status as response_status,
            sr.answers,
            u.id as user_id,
            u.username,
            u.email,
            u.firstname,
            u.lastname,
            u.role as user_role,
            o.id as organization_id,
            o.name as organization_name,
            o.type as organization_type,
            st.survey_code,
            st.questions as survey_questions,
            gl.country,
            gl.province,
            gl.city,
            gl.town,
            gl.latitude,
            gl.longitude
        FROM survey_responses sr
        LEFT JOIN users u ON sr.user_id = u.id
        LEFT JOIN organizations o ON u.organization_id = o.id
        LEFT JOIN survey_templates st ON sr.template_id = st.id
        LEFT JOIN geo_locations gl ON u.id = gl.user_id
        WHERE 1=1
        """
        
        conditions = []
        
        # Add filters based on query keywords
        if 'church' in query:
            conditions.append("o.type = 'church'")
        elif 'institution' in query or 'school' in query:
            conditions.append("o.type = 'school'")
        elif 'organization' in query and 'type' not in query:
            conditions.append("o.type = 'other'")
        
        # Country filters
        if 'kenya' in query:
            conditions.append("gl.country LIKE '%Kenya%'")
        elif 'uganda' in query:
            conditions.append("gl.country LIKE '%Uganda%'")
        elif 'tanzania' in query:
            conditions.append("gl.country LIKE '%Tanzania%'")
        
        # Status filters
        if 'completed' in query:
            conditions.append("sr.status = 'completed'")
        elif 'pending' in query:
            conditions.append("sr.status = 'pending'")
        elif 'in progress' in query or 'in-progress' in query:
            conditions.append("sr.status = 'in_progress'")
        
        # Time-based filters
        if 'recent' in query or 'latest' in query:
            conditions.append("sr.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)")
        elif 'this year' in query:
            conditions.append("YEAR(sr.created_at) = YEAR(NOW())")
        elif 'last year' in query:
            conditions.append("YEAR(sr.created_at) = YEAR(NOW()) - 1")
        
        # Add conditions to query
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
        
        # Order by most recent
        base_query += " ORDER BY sr.created_at DESC"
        
        # Add limit
        base_query += f" LIMIT {limit}"
        
        return base_query
    
    def _classify_query(self, query: str) -> str:
        """
        Classify the type of query
        
        Args:
            query: User's question (lowercase)
            
        Returns:
            Query type classification
        """
        if any(word in query for word in ['compare', 'comparison', 'versus', 'vs']):
            return 'comparison'
        elif any(word in query for word in ['trend', 'over time', 'change', 'growth']):
            return 'trend'
        elif any(word in query for word in ['count', 'how many', 'number of', 'total']):
            return 'count'
        elif any(word in query for word in ['average', 'mean', 'median']):
            return 'aggregation'
        elif any(word in query for word in ['organization', 'institution', 'church']):
            return 'organization_specific'
        elif any(word in query for word in ['user', 'person', 'contact']):
            return 'user_specific'
        elif any(word in query for word in ['location', 'country', 'region', 'city']):
            return 'geographic'
        else:
            return 'general'
    
    def _extract_metadata(self, data: List[Dict]) -> Dict[str, Any]:
        """
        Extract metadata from retrieved data for grounding
        
        Args:
            data: List of survey response records
            
        Returns:
            Metadata dictionary with grounding information
        """
        if not data:
            return {}
        
        # Extract unique values for grounding
        organizations = set()
        organization_types = set()
        countries = set()
        users = set()
        survey_codes = set()
        statuses = set()
        
        for record in data:
            if record.get('organization_name'):
                organizations.add(record['organization_name'])
            if record.get('organization_type'):
                organization_types.add(record['organization_type'])
            if record.get('country'):
                countries.add(record['country'])
            if record.get('username'):
                users.add(record['username'])
            if record.get('survey_code'):
                survey_codes.add(record['survey_code'])
            if record.get('response_status'):
                statuses.add(record['response_status'])
        
        return {
            'total_responses': len(data),
            'organizations': list(organizations),
            'organization_count': len(organizations),
            'organization_types': list(organization_types),
            'countries': list(countries),
            'users': list(users),
            'user_count': len(users),
            'survey_codes': list(survey_codes),
            'statuses': list(statuses),
            'date_range': {
                'earliest': min(r.get('response_date', datetime.now()) for r in data if r.get('response_date')),
                'latest': max(r.get('response_date', datetime.now()) for r in data if r.get('response_date'))
            } if any(r.get('response_date') for r in data) else None
        }
    
    def generate_grounded_response(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate AI response using Gemini 2.0 Flash Lite with grounding
        
        Args:
            query: User's question
            context: Retrieved data and metadata
            
        Returns:
            AI-generated response with grounding information
        """
        try:
            if not self.api_key:
                return {
                    'response': 'API key not configured. Please set GEMINI_API_KEY environment variable.',
                    'grounding': [],
                    'error': 'missing_api_key'
                }
            
            # Build grounded prompt
            prompt = self._build_grounded_prompt(query, context)
            
            # Call Gemini API
            api_url = f"{self.api_endpoint}?key={self.api_key}"
            
            payload = {
                'contents': [{
                    'parts': [{
                        'text': prompt
                    }]
                }],
                'generationConfig': {
                    'temperature': 0.4,  # Lower temperature for more factual responses
                    'maxOutputTokens': 1024,
                    'topP': 0.8,
                    'topK': 40
                }
            }
            
            logger.info(f"🤖 Calling Gemini 2.0 Flash Lite API...")
            
            response = requests.post(
                api_url,
                headers={'Content-Type': 'application/json'},
                json=payload,
                timeout=30
            )
            
            if not response.ok:
                logger.error(f"Gemini API Error: {response.status_code} - {response.text}")
                return {
                    'response': f'API request failed with status {response.status_code}',
                    'grounding': [],
                    'error': 'api_error'
                }
            
            result = response.json()
            
            # Extract response text
            generated_text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            
            # Build grounding information
            grounding = self._build_grounding_info(context)
            
            logger.info(f"✅ Generated response with {len(grounding)} grounding sources")
            
            return {
                'response': generated_text,
                'grounding': grounding,
                'metadata': context.get('metadata', {}),
                'query_type': context.get('query_type', 'general'),
                'model': self.model
            }
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return {
                'response': f'Error generating response: {str(e)}',
                'grounding': [],
                'error': str(e)
            }
    
    def _build_grounded_prompt(self, query: str, context: Dict[str, Any]) -> str:
        """
        Build a grounded prompt with retrieved data
        
        Args:
            query: User's question
            context: Retrieved data and metadata
            
        Returns:
            Formatted prompt string
        """
        metadata = context.get('metadata', {})
        data = context.get('data', [])
        
        prompt = f"""You are a survey analytics assistant for the Saurara Platform. Answer the user's question based ONLY on the provided survey data. Be specific and cite the data sources.

USER QUESTION: {query}

AVAILABLE DATA SUMMARY:
- Total Survey Responses: {metadata.get('total_responses', 0)}
- Organizations: {', '.join(str(x) for x in metadata.get('organizations', [])[:5])}{'...' if len(metadata.get('organizations', [])) > 5 else ''}
- Organization Types: {', '.join(str(x) for x in metadata.get('organization_types', []))}
- Countries: {', '.join(str(x) for x in metadata.get('countries', []))}
- Survey Codes: {', '.join(str(x) for x in metadata.get('survey_codes', [])[:3])}
- Response Statuses: {', '.join(str(x) for x in metadata.get('statuses', []))}

DETAILED SURVEY DATA:
"""
        
        # Add sample of actual data (limit to avoid token overflow)
        for i, record in enumerate(data[:5], 1):
            prompt += f"\n{i}. Survey Response:"
            prompt += f"\n   - Organization: {record.get('organization_name', 'N/A')} ({record.get('organization_type', 'N/A')})"
            prompt += f"\n   - User: {record.get('firstname', '')} {record.get('lastname', '')} ({record.get('username', 'N/A')})"
            prompt += f"\n   - Location: {record.get('city', 'N/A')}, {record.get('country', 'N/A')}"
            prompt += f"\n   - Status: {record.get('response_status', 'N/A')}"
            prompt += f"\n   - Date: {record.get('response_date', 'N/A')}"
            
            # Include answer summary if available
            if record.get('answers'):
                try:
                    answers = json.loads(record['answers']) if isinstance(record['answers'], str) else record['answers']
                    prompt += f"\n   - Number of Questions Answered: {len(answers)}"
                except:
                    pass
        
        if len(data) > 5:
            prompt += f"\n\n... and {len(data) - 5} more responses with similar structure."
        
        prompt += """

INSTRUCTIONS:
1. Answer the question using ONLY the data provided above
2. Be specific and cite which organization, user, or survey you're referring to
3. If the data doesn't contain enough information to answer, say so clearly
4. Include relevant statistics (counts, percentages) when applicable
5. Format your response clearly with bullet points or sections
6. Always mention the organization name and type when discussing specific surveys

Provide your answer now:"""
        
        return prompt
    
    def _build_grounding_info(self, context: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Build grounding information showing data sources
        
        Args:
            context: Retrieved data and metadata
            
        Returns:
            List of grounding source dictionaries
        """
        grounding = []
        data = context.get('data', [])
        
        for record in data:
            source = {
                'type': 'survey_response',
                'organization': record.get('organization_name', 'Unknown'),
                'organization_type': record.get('organization_type', 'Unknown'),
                'user': f"{record.get('firstname', '')} {record.get('lastname', '')}".strip() or record.get('username', 'Unknown'),
                'location': f"{record.get('city', '')}, {record.get('country', '')}".strip(', ') or 'Unknown',
                'date': str(record.get('response_date', 'Unknown')),
                'status': record.get('response_status', 'Unknown'),
                'survey_code': record.get('survey_code', 'Unknown')
            }
            grounding.append(source)
        
        return grounding
    
    def answer_question(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """
        Main method to answer a question using RAG
        
        Args:
            query: User's question
            limit: Maximum number of records to retrieve
            
        Returns:
            Complete response with answer and grounding
        """
        logger.info(f"📝 Processing RAG query: {query}")
        
        # Step 1: Retrieve relevant data
        context = self.retrieve_survey_data(query, limit)
        
        if context.get('error'):
            return {
                'success': False,
                'error': context['error'],
                'response': 'Unable to retrieve data from database.',
                'grounding': []
            }
        
        if context['count'] == 0:
            return {
                'success': True,
                'response': 'No survey data found matching your query. Please try rephrasing your question or check if there is data available for your criteria.',
                'grounding': [],
                'metadata': {}
            }
        
        # Step 2: Generate grounded response
        result = self.generate_grounded_response(query, context)
        
        return {
            'success': True,
            **result
        }
