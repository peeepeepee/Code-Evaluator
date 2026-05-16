import re
import html
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

def sanitize_problem_statement(problem_statement: str) -> str:
    """
    Sanitize the problem statement
    
    Args:
        problem_statement: Raw problem statement
        
    Returns:
        Sanitized problem statement
    """
    # Basic HTML escaping
    sanitized = html.escape(problem_statement)
    
    # Remove any markdown or formatting that could interfere with prompt
    sanitized = re.sub(r'```(?:.|\n)*?```', '[CODE BLOCK]', sanitized)
    
    return sanitized


def sanitize_rubric(rubric: str) -> str:
    """
    Sanitize the rubric text
    
    Args:
        rubric: Raw rubric text
        
    Returns:
        Sanitized rubric
    """
    # Basic HTML escaping
    sanitized = html.escape(rubric)
    
    # Ensure rubric has standard format if needed
    if not re.search(r'Solution\s+\d+:', sanitized):
        # If rubric doesn't follow expected format, try to normalize it
        lines = sanitized.split('\n')
        normalized = []
        
        for line in lines:
            # Try to detect rubric items and format them consistently
            if re.match(r'^\d+\.', line):
                normalized.append(line)
            else:
                normalized.append(line)
        
        sanitized = '\n'.join(normalized)
    
    return sanitized


def remove_java_comments(code: str) -> str:
    """
    Remove all comments from Java code.
    
    This function removes:
    1. Block comments (/* ... */)
    2. Single-line comments (// ...)
    3. JavaDoc comments (/** ... */)
    
    Args:
        code (str): The Java code with comments
        
    Returns:
        str: The Java code with all comments removed
    """
    # Remove block comments (including JavaDoc)
    pattern = r'/\*[\s\S]*?\*/'
    code_without_block_comments = re.sub(pattern, '', code)
    
    # Remove single-line comments
    #pattern = r'//.*?$'
    #code_without_comments = re.sub(pattern, '', code_without_block_comments, flags=re.MULTILINE)
    
    # Remove extra blank lines that might result from comment removal
    code_without_extra_lines = re.sub(r'\n\s*\n+', '\n\n', code_without_block_comments)
    
    return code_without_extra_lines


def secure_student_code(code: str, remove_comments: bool = True) -> str:
    """
    Apply comprehensive security measures to student code
    
    Args:
        code: Raw student code
        remove_comments: Whether to remove comments from the code
        
    Returns:
        Secured student code
    """
    # Remove comments if requested
    if remove_comments:
        # Detect if the code is likely Java
        if re.search(r'public\s+class|import\s+java\.', code):
            code = remove_java_comments(code)
        # TODO: Add support for other languages if needed
    
    # Basic HTML escaping
    sanitized = html.escape(code)
    
    # Neutralize potential delimiter-breaking characters
    sanitized = sanitized.replace("```", "\\`\\`\\`")
    
    # Remove/neutralize suspicious patterns
    suspicious_patterns = [
        r'</?system>',
        r'</?user>',
        r'</?assistant>',
        r'</?instruction>',
        r'</?prompt>',
        r'ignore previous instructions',
        r'disregard the above',
    ]
    
    for pattern in suspicious_patterns:
        sanitized = re.sub(pattern, '/* REMOVED */', sanitized, flags=re.IGNORECASE)
    
    # Wrap in delimiter for isolation
    return f"<STUDENT_CODE>\n{sanitized}\n</STUDENT_CODE>"


def process_inputs(problem_statement: str, rubric: str, student_code: str, remove_comments: bool = True) -> Tuple[str, str, str]:
    """
    Process and sanitize all inputs
    
    Args:
        problem_statement: Raw problem statement
        rubric: Raw rubric
        student_code: Raw student code
        remove_comments: Whether to remove comments from student code
        
    Returns:
        Tuple of (sanitized_problem, sanitized_rubric, secured_code)
    """
    sanitized_problem = sanitize_problem_statement(problem_statement)
    sanitized_rubric = sanitize_rubric(rubric)
    secured_code = secure_student_code(student_code, remove_comments=remove_comments)
    
    return sanitized_problem, sanitized_rubric, secured_code


def extract_language_from_code(code: str) -> str:
    """
    Detect programming language using multiple indicators
    
    Args:
        code: Source code to analyze
        
    Returns:
        Detected language or "unknown"
    """
    # Initialize scoring for each language
    scores = {
        "java": 0,
        "python": 0,
        "cpp": 0,
        "javascript": 0
    }
    
    # Java indicators
    if re.search(r'public\s+class\s+\w+', code): scores["java"] += 3
    if re.search(r'public\s+static\s+void\s+main', code): scores["java"] += 3
    if re.search(r'import\s+java\.', code): scores["java"] += 2
    if re.search(r'System\.(out|in|err)\.', code): scores["java"] += 2
    if re.search(r'private|protected|public\s+\w+[\s\w]+\(', code): scores["java"] += 1
    
    # Python indicators
    if re.search(r'def\s+\w+\s*\([^)]*\)\s*:', code): scores["python"] += 3
    if re.search(r'import\s+(\w+|\w+\s+as\s+\w+)', code): scores["python"] += 2
    if re.search(r'from\s+\w+\s+import', code): scores["python"] += 2
    if re.search(r'if\s+__name__\s*==\s*[\'"]__main__[\'"]:', code): scores["python"] += 3
    if re.search(r'print\s*\(', code): scores["python"] += 1
    
    # C++ indicators
    if re.search(r'#include\s*<[^>]+>', code): scores["cpp"] += 3
    if re.search(r'using\s+namespace\s+std\s*;', code): scores["cpp"] += 2
    if re.search(r'std::', code): scores["cpp"] += 2
    if re.search(r'int\s+main\s*\([^)]*\)', code): scores["cpp"] += 3
    if re.search(r'cout\s*<<|cin\s*>>', code): scores["cpp"] += 2
    
    # JavaScript indicators
    if re.search(r'const|let|var\s+\w+\s*=', code): scores["javascript"] += 2
    if re.search(r'function\s+\w+\s*\([^)]*\)', code): scores["javascript"] += 2
    if re.search(r'console\.(log|error|warn)', code): scores["javascript"] += 2
    if re.search(r'document\.|window\.|addEventListener', code): scores["javascript"] += 3
    if re.search(r'=>', code): scores["javascript"] += 1
    
    # Get language with highest score
    max_score = max(scores.values())
    detected = max(scores.items(), key=lambda x: x[1])[0]
    
    # Return unknown if score is too low
    
    return detected if max_score >= 3 else "unknown"