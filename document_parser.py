
import os
import json
import logging
import io
from pypdf import PdfReader
from docx import Document
import requests

logger = logging.getLogger(__name__)

class DocumentParserService:
    def __init__(self):
        self.api_key = os.getenv('GEMINI_API_KEY', '')
        self.model = 'gemini-2.0-flash-lite'
        self.api_endpoint = f'https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent'

    def extract_text_from_file(self, file_storage):
        """Extract text from PDF or DOCX file storage object"""
        filename = file_storage.filename.lower()
        content = file_storage.read()
        file_stream = io.BytesIO(content)
        
        text = ""
        try:
            if filename.endswith('.pdf'):
                reader = PdfReader(file_stream)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            elif filename.endswith('.docx') or filename.endswith('.doc'):
                doc = Document(file_stream)
                for para in doc.paragraphs:
                    text += para.text + "\n"
            elif filename.endswith('.txt'):
                text = content.decode('utf-8', errors='ignore')
            else:
                raise ValueError("Unsupported file format")
                
            return text.strip()
        except Exception as e:
            logger.error(f"Error extracting text: {e}")
            raise

    def parse_questions_from_text(self, text):
        """Use LLM to parse extracted text into structured JSON questions"""
        if not self.api_key:
            logger.error("GEMINI_API_KEY not found")
            return []

        prompt = """
        You are an expert survey designer. Convert the following survey text into a structured JSON array of questions.
        
        The output must be a valid JSON array of objects. Each object should have:
        - "question_text": The text of the question.
        - "question_type_id": A guessed integer ID based on the map below (default to 1 'short_text' if unsure).
        - "section": A inferred section name (e.g., "Demographics", "Main", "Feedback").
        - "is_required": boolean (true if it looks mandatory, else false).
        - "config": An object containing "options" (array of {label, value}) for choice questions, or relevant config.
        
        Question Type Map (use these IDs):
        1: Short Text
        2: Paragraph
        3: Single Choice (Radio)
        4: Multiple Selection (Checkbox)
        5: Dropdown
        6: Yes/No
        7: Date
        8: Rating/Likert
        9: Numeric
        
        For Single/Multiple choice, extract options into config.options.
        
        Input Text:
        {text}
        
        Output JSON only:
        """
        
        formatted_prompt = prompt.replace("{text}", text[:30000]) # Limit context window usage

        try:
            payload = {
                'contents': [{'parts': [{'text': formatted_prompt}]}],
                'generationConfig': {
                    'temperature': 0.2, # Low temperature for structured output
                    'responseMimeType': 'application/json'
                }
            }
            
            response = requests.post(
                f"{self.api_endpoint}?key={self.api_key}",
                headers={'Content-Type': 'application/json'},
                json=payload,
                timeout=60
            )
            
            if not response.ok:
                logger.error(f"Gemini API Error: {response.text}")
                return []
                
            result = response.json()
            generated_text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            
            # Clean markdown code blocks if present (though responseMimeType should handle it)
            if generated_text.startswith('```json'):
                generated_text = generated_text.replace('```json', '').replace('```', '')
            
            questions = json.loads(generated_text)
            return questions
            
        except Exception as e:
            logger.error(f"Error parsing questions with LLM: {e}")
            # Fallback: simple text split if LLM fails? strict requirement for complex parsing.
            return []
