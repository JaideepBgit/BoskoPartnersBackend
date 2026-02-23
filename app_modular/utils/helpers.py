"""
Utility helper functions.
"""
import re


def validate_user_role(role):
    """
    Validate user role against enum values.
    
    Args:
        role: Role string to validate
    
    Returns:
        str: Valid role or 'other' if invalid
    """
    valid_roles = ['root', 'admin', 'coach', 'manager', 'head', 'user', 'observer', 'participant', 'other', 'primary_contact', 'secondary_contact']
    if role and role.lower() in valid_roles:
        return role.lower()
    return 'other'


def render_email_template(template_content, **kwargs):
    """
    Render email template with provided variables using safe substitution.
    
    Args:
        template_content: Template string with {variable} placeholders
        **kwargs: Variables to substitute
    
    Returns:
        str: Rendered template
    """
    if not template_content:
        return ''
    
    try:
        # Use format_map with a default dict for missing keys
        class SafeDict(dict):
            def __missing__(self, key):
                return f'{{{key}}}'  # Return the placeholder if key not found
        
        return template_content.format_map(SafeDict(**kwargs))
    except Exception:
        # Fallback: simple string replacement
        result = template_content
        for key, value in kwargs.items():
            result = result.replace(f'{{{key}}}', str(value) if value else '')
        return result


def generate_survey_code(prefix='SUR'):
    """
    Generate a unique survey code.
    
    Args:
        prefix: Code prefix (default: 'SUR')
    
    Returns:
        str: Unique survey code
    """
    import uuid
    unique_id = str(uuid.uuid4())[:8].upper()
    return f"{prefix}-{unique_id}"


def generate_password(length=12):
    """
    Generate a secure random password.
    
    Args:
        length: Password length (default: 12)
    
    Returns:
        str: Random password
    """
    import secrets
    import string
    
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return password


def sanitize_filename(filename):
    """
    Sanitize a filename for safe file system usage.
    
    Args:
        filename: Original filename
    
    Returns:
        str: Sanitized filename
    """
    # Remove any path components
    filename = filename.replace('\\', '/').split('/')[-1]
    # Remove any potentially dangerous characters
    filename = re.sub(r'[^\w\s.-]', '', filename)
    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:250] + ('.' + ext if ext else '')
    return filename


def parse_date(date_string):
    """
    Parse a date string to datetime object.
    
    Args:
        date_string: Date string in various formats
    
    Returns:
        datetime: Parsed datetime or None
    """
    from datetime import datetime
    
    formats = [
        '%Y-%m-%d',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S.%fZ',
        '%d/%m/%Y',
        '%m/%d/%Y',
    ]
    
    if not date_string:
        return None
    
    for fmt in formats:
        try:
            return datetime.strptime(date_string, fmt)
        except ValueError:
            continue
    
    return None


def safe_int(value, default=0):
    """
    Safely convert a value to integer.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
    
    Returns:
        int: Converted integer or default
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default=0.0):
    """
    Safely convert a value to float.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
    
    Returns:
        float: Converted float or default
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
